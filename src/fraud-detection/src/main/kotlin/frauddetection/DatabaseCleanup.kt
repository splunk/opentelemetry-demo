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
        logger.info(
            "Cleanup run complete: OrderLogs deleted=$orderLogsDeleted, " +
                "FraudAlerts deleted=$fraudAlertsDeleted, retentionDays=$retentionDays"
        )
        return CleanupResult(orderLogsDeleted, fraudAlertsDeleted)
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
    }
}
