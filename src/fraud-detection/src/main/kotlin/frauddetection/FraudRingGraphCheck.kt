/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package frauddetection

import io.opentelemetry.api.trace.Span
import org.apache.logging.log4j.LogManager
import org.apache.logging.log4j.Logger
import kotlin.system.measureTimeMillis

/**
 * Fraud Ring Graph — DBMon guardian demo.
 *
 * Same business intent, two implementations. Both count distinct
 * OrderLogs whose shipping_street matches the seed order's, within
 * the last 30 days.
 *
 * fast(): indexed equality join on shipping_street. Uses idx_shipping_street
 *   → index seek → milliseconds.
 *
 * slow(): the "developer mistake" version. Wraps both sides of the
 *   join predicate in UPPER() to be case-insensitive. UPPER() on both
 *   sides is non-sargable — the optimizer cannot use idx_shipping_street
 *   and falls back to a full-scan nested-loop join. Same result, but
 *   O(N²) work.
 *
 * DBMon story: both queries appear in top-query lists. Comparing plans
 * shows Index Seek vs Table Scan; comparing wall time / logical reads
 * shows the cost of function-on-column. The fix (drop the UPPER, or
 * store a normalized column with a function-based index) is the
 * teaching moment.
 *
 * No amplifier, no timeout, no circuit breaker — the query is naturally
 * bounded by the row count in OrderLogs. To make the slow path visible
 * on any deployment we seed OrderLogs to SEED_TARGET_ROWS on startup
 * (see [seedIfEmpty]) so the slow path lands in the ~4–10 s range.
 */
class FraudRingGraphCheck {
    private val logger: Logger = LogManager.getLogger(FraudRingGraphCheck::class.java)

    /**
     * @param mode "fast" | "slow" — anything else is a no-op.
     */
    fun analyze(orderId: String, mode: String): FraudAlert? {
        return when (mode.lowercase()) {
            "fast" -> runQuery(orderId, "fast", FAST_SQL)
            "slow" -> runQuery(orderId, "slow", SLOW_SQL)
            else -> null
        }
    }

    private fun runQuery(orderId: String, mode: String, sql: String): FraudAlert? {
        val span = Span.current()
        var alert: FraudAlert? = null
        try {
            val wall = measureTimeMillis {
                DatabaseConfig.getConnection().use { conn ->
                    conn.prepareStatement(sql).use { stmt ->
                        stmt.setString(1, orderId)
                        stmt.executeQuery().use { rs ->
                            if (rs.next()) {
                                val related = rs.getInt("related_orders")
                                span.setAttribute("app.fraud.ring_graph.related_orders", related.toLong())
                                if (related >= ALERT_THRESHOLD) {
                                    val risk = (related / 200.0).coerceAtMost(0.90)
                                    alert = FraudAlert(
                                        orderId = orderId,
                                        alertType = "RING_GRAPH_${mode.uppercase()}",
                                        severity = FraudAnalytics.SEVERITY_HIGH,
                                        reason = "$mode ring graph: related=$related",
                                        riskScore = risk,
                                    )
                                }
                            }
                        }
                    }
                }
            }
            span.setAttribute("app.fraud.ring_graph.mode", mode)
            span.setAttribute("app.fraud.ring_graph.wall_ms", wall)
            logger.info("🕸️ Ring graph ${mode.uppercase()}: orderId=$orderId wall=${wall}ms alert=${alert != null}")
        } catch (e: Exception) {
            logger.warn("Ring graph $mode failed for order $orderId: ${e.message}")
        }
        return alert
    }

    /**
     * Ensure OrderLogs has at least SEED_TARGET_ROWS synthetic rows so
     * the slow path lands in a reasonable wall-time band. Idempotent:
     * if the table already has enough rows, returns immediately.
     *
     * Synthetic rows draw from a small pool of shipping streets and
     * cities so many rows share the same street — the join in the
     * ring-graph queries then has real matches to count.
     */
    fun seedIfEmpty() {
        val current = countOrderLogs()
        if (current >= SEED_TARGET_ROWS) {
            logger.info("Ring graph seed: OrderLogs has $current rows (≥ $SEED_TARGET_ROWS target) — skipping seed")
            return
        }
        val toInsert = SEED_TARGET_ROWS - current
        logger.info("Ring graph seed: OrderLogs has $current rows, inserting $toInsert synthetic rows to reach $SEED_TARGET_ROWS")
        try {
            DatabaseConfig.getConnection().use { conn ->
                conn.autoCommit = false
                conn.prepareStatement(SEED_INSERT_SQL).use { stmt ->
                    val batchSize = 1000
                    var inserted = 0
                    while (inserted < toInsert) {
                        val batchEnd = minOf(inserted + batchSize, toInsert.toInt())
                        for (i in inserted until batchEnd) {
                            val streetIdx = i % SEED_STREETS.size
                            val cityIdx = i % SEED_CITIES.size
                            val daysBack = i % 30
                            stmt.setString(1, "seed-${System.currentTimeMillis()}-$i")
                            stmt.setString(2, SEED_STREETS[streetIdx])
                            stmt.setString(3, SEED_CITIES[cityIdx])
                            stmt.setInt(4, -daysBack)
                            stmt.addBatch()
                        }
                        stmt.executeBatch()
                        conn.commit()
                        inserted = batchEnd
                        if (inserted % 10_000 == 0) {
                            logger.info("Ring graph seed: inserted $inserted / $toInsert")
                        }
                    }
                }
                conn.autoCommit = true
            }
            logger.info("Ring graph seed: complete, inserted $toInsert synthetic rows")
        } catch (e: Exception) {
            logger.warn("Ring graph seed failed: ${e.message}", e)
        }
    }

    private fun countOrderLogs(): Long {
        return try {
            DatabaseConfig.getConnection().use { conn ->
                conn.createStatement().use { stmt ->
                    stmt.executeQuery("SELECT COUNT_BIG(*) AS n FROM OrderLogs").use { rs ->
                        if (rs.next()) rs.getLong("n") else 0L
                    }
                }
            }
        } catch (e: Exception) {
            logger.warn("Ring graph seed: count failed, assuming empty: ${e.message}")
            0L
        }
    }

    companion object {
        private const val ALERT_THRESHOLD = 20
        private const val SEED_TARGET_ROWS = 100_000L

        // Fast — indexed equality join. Uses idx_shipping_street → Index Seek.
        private val FAST_SQL = """
            SELECT COUNT(DISTINCT ol2.order_id) AS related_orders
            FROM OrderLogs ol1
            INNER JOIN OrderLogs ol2
                ON ol2.shipping_street = ol1.shipping_street
            WHERE ol1.order_id = ?
              AND ol2.consumed_at >= DATEADD(DAY, -30, GETDATE());
        """.trimIndent()

        // Slow — the "developer mistake". UPPER() on both sides of the
        // join predicate makes it non-sargable: optimizer cannot use
        // idx_shipping_street, falls back to full scan + nested loop.
        // Same result set as FAST_SQL.
        private val SLOW_SQL = """
            SELECT COUNT(DISTINCT ol2.order_id) AS related_orders
            FROM OrderLogs ol1
            INNER JOIN OrderLogs ol2
                ON UPPER(ol2.shipping_street) = UPPER(ol1.shipping_street)
            WHERE ol1.order_id = ?
              AND ol2.consumed_at >= DATEADD(DAY, -30, GETDATE());
        """.trimIndent()

        // Synthetic row insert. Uses a small street/city pool so many
        // rows share addresses → the join has real matches to count.
        private val SEED_INSERT_SQL = """
            INSERT INTO OrderLogs (order_id, shipping_street, shipping_city, items_count, consumed_at)
            VALUES (?, ?, ?, 1, DATEADD(DAY, ?, GETDATE()))
        """.trimIndent()

        private val SEED_STREETS = listOf(
            "123 Main St", "456 Oak Ave", "789 Pine Rd", "12 Elm Way", "34 Maple Dr",
            "56 Cedar Ln", "78 Birch Ct", "90 Willow Blvd", "111 Spruce St", "222 Ash Ave",
            "333 Poplar Rd", "444 Cherry Way", "555 Walnut Dr", "666 Chestnut Ln", "777 Hickory Ct",
            "888 Sycamore Blvd", "999 Dogwood St", "101 Redwood Ave", "202 Sequoia Rd", "303 Fir Way",
        )
        private val SEED_CITIES = listOf(
            "Springfield", "Riverside", "Franklin", "Greenville", "Bristol",
            "Clinton", "Fairview", "Salem", "Georgetown", "Madison",
        )
    }
}
