/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package frauddetection

import org.apache.logging.log4j.LogManager
import org.apache.logging.log4j.Logger
import java.sql.Connection
import java.sql.SQLException
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

data class CleanupResult(val orderLogsDeleted: Int, val fraudAlertsDeleted: Int) {
    val total: Int get() = orderLogsDeleted + fraudAlertsDeleted
}

class DatabaseCleanup {
    private val logger: Logger = LogManager.getLogger(DatabaseCleanup::class.java)
    private val scheduler = Executors.newSingleThreadScheduledExecutor { r ->
        Thread(r, "db-cleanup").apply {
            isDaemon = true
            // Low priority so Kafka consume loop preempts under contention.
            priority = Thread.MIN_PRIORITY
        }
    }

    fun startCleanupScheduler(retentionDays: Int = 4, intervalHours: Long = 6) {
        val firstFireAt = Instant.now().plus(intervalHours, ChronoUnit.HOURS)
        logger.info(
            "Database cleanup scheduler started: retentionDays=$retentionDays, " +
                "intervalHours=$intervalHours, firstFireAt=$firstFireAt " +
                "(batched DELETE TOP($BATCH_SIZE), lockTimeout=${LOCK_TIMEOUT_MS}ms)"
        )

        scheduler.scheduleAtFixedRate({
            try {
                cleanupOldRecords(retentionDays)
            } catch (e: Exception) {
                logger.error("Error during scheduled cleanup", e)
            }
        }, intervalHours, intervalHours, TimeUnit.HOURS)
    }

    fun cleanupOldRecords(retentionDays: Int): CleanupResult {
        val orderLogsDeleted = deleteOlderThan("OrderLogs", "consumed_at", retentionDays)
        val fraudAlertsDeleted = deleteOlderThan("FraudAlerts", "created_at", retentionDays)
        // Cap OrderLogs at MAX_ORDER_LOGS_ROWS. Time-based cleanup only
        // keeps rows within retentionDays, but if Kafka bursts push the
        // count above the cap within that window, the ring-graph slow
        // query duration grows unbounded (O(N) full scan on ol2). The
        // cap keeps demo timings stable.
        val excessDeleted = deleteExcessRows("OrderLogs", "consumed_at", MAX_ORDER_LOGS_ROWS)
        logger.info(
            "Cleanup run complete: OrderLogs deleted=${orderLogsDeleted + excessDeleted} " +
                "(old=$orderLogsDeleted, excess=$excessDeleted, cap=$MAX_ORDER_LOGS_ROWS), " +
                "FraudAlerts deleted=$fraudAlertsDeleted, retentionDays=$retentionDays"
        )
        return CleanupResult(orderLogsDeleted + excessDeleted, fraudAlertsDeleted)
    }

    /**
     * Cap-based pruner: if the table has more than maxRows, delete the
     * oldest rows in batches until back at (or below) the cap. Safe to
     * call on tables that are already under the cap (returns 0).
     */
    private fun deleteExcessRows(table: String, timestampCol: String, maxRows: Long): Int {
        var total = 0
        try {
            DatabaseConfig.getConnection().use { conn ->
                val current = countRows(conn, table).toLong()
                if (current <= maxRows) return 0
                val toDelete = current - maxRows
                logger.info("$table over cap: current=$current cap=$maxRows deleting=$toDelete")
                conn.createStatement().use { it.execute("SET LOCK_TIMEOUT $LOCK_TIMEOUT_MS") }

                // Delete the oldest BATCH_SIZE rows per iteration until
                // total deleted hits toDelete.
                val sql = "DELETE FROM $table WHERE id IN " +
                    "(SELECT TOP ($BATCH_SIZE) id FROM $table ORDER BY $timestampCol ASC)"

                while (total < toDelete) {
                    val rows = try {
                        conn.createStatement().use { it.executeUpdate(sql) }
                    } catch (e: SQLException) {
                        logger.warn(
                            "$table excess-cleanup hit lock timeout (deleted=$total so far) — " +
                                "will retry next interval. ${e.message}"
                        )
                        return total
                    }
                    total += rows
                    if (rows == 0) break
                    Thread.sleep(SLEEP_BETWEEN_BATCHES_MS)
                }
            }
        } catch (e: Exception) {
            logger.error("Failed excess-cleanup on $table (deleted $total before error)", e)
        }
        return total
    }

    private fun deleteOlderThan(table: String, timestampCol: String, retentionDays: Int): Int {
        var total = 0
        try {
            DatabaseConfig.getConnection().use { conn ->
                conn.createStatement().use { it.execute("SET LOCK_TIMEOUT $LOCK_TIMEOUT_MS") }

                val sql = "DELETE TOP ($BATCH_SIZE) FROM $table " +
                    "WHERE $timestampCol < DATEADD(DAY, -?, GETDATE())"

                while (true) {
                    val rows = try {
                        conn.prepareStatement(sql).use { stmt ->
                            stmt.setInt(1, retentionDays)
                            stmt.executeUpdate()
                        }
                    } catch (e: SQLException) {
                        // SQL Server lock timeout = error 1222. Abandon batch,
                        // retry next interval to avoid blocking the consume loop.
                        logger.warn(
                            "$table cleanup hit lock timeout (deleted=$total so far) — " +
                                "will retry next interval. ${e.message}"
                        )
                        return total
                    }
                    total += rows
                    if (rows < BATCH_SIZE) break
                    Thread.sleep(SLEEP_BETWEEN_BATCHES_MS)
                }
            }
        } catch (e: Exception) {
            logger.error("Failed cleanup on $table (deleted $total before error)", e)
        }
        return total
    }

    fun cleanupAllRecords(): Int {
        return try {
            DatabaseConfig.getConnection().use { conn ->
                val orderCount = countRows(conn, "OrderLogs")
                val alertCount = countRows(conn, "FraudAlerts")

                conn.createStatement().use { stmt ->
                    stmt.execute("TRUNCATE TABLE OrderLogs")
                    stmt.execute("TRUNCATE TABLE FraudAlerts")
                }

                val total = orderCount + alertCount
                logger.info("Truncated OrderLogs ($orderCount rows) and FraudAlerts ($alertCount rows)")
                total
            }
        } catch (e: Exception) {
            logger.error("Failed to truncate tables", e)
            0
        }
    }

    private fun countRows(conn: Connection, table: String): Int {
        conn.createStatement().use { stmt ->
            val rs = stmt.executeQuery("SELECT COUNT(*) FROM $table")
            return if (rs.next()) rs.getInt(1) else 0
        }
    }

    fun stop() {
        logger.info("Stopping database cleanup scheduler")
        scheduler.shutdown()
        try {
            if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                scheduler.shutdownNow()
            }
        } catch (e: InterruptedException) {
            scheduler.shutdownNow()
        }
    }

    companion object {
        private const val BATCH_SIZE = 500
        private const val SLEEP_BETWEEN_BATCHES_MS = 200L
        private const val LOCK_TIMEOUT_MS = 5000
        // Hard ceiling on OrderLogs row count. Sized ~30 % above the
        // ring-graph seed target (300k) so Kafka growth has headroom
        // but the slow query never blows past its target 4-10 s band.
        private const val MAX_ORDER_LOGS_ROWS = 400_000L
    }
}
