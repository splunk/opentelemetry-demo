/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package frauddetection

import io.opentelemetry.api.trace.Span
import org.apache.logging.log4j.LogManager
import org.apache.logging.log4j.Logger
import java.util.concurrent.atomic.AtomicLong
import kotlin.system.measureTimeMillis

/**
 * Fraud Ring Graph — DBMon guardian demo.
 *
 * Two implementations of the *same business intent*: from a seed order,
 * find related orders via shipping-address matches and compute a
 * hop-weighted risk score from any FraudAlerts on those orders.
 *
 * fast(): indexed 1-hop join, TOP-capped, RECOMPILE. Milliseconds.
 * slow(): recursive CTE (5 hops) with fuzzy LIKE predicates, cross-joined
 *   with a tunable sys.all_columns amplifier that adaptively targets
 *   ~8s wall time. Real work — the amplifier drives real logical reads
 *   and CPU, not fake sleeps.
 *
 * The slow path self-calibrates on first use and re-adjusts mid-flight
 * whenever a run falls outside the [3s, 12s] deadband.
 */
class FraudRingGraphCheck {
    private val logger: Logger = LogManager.getLogger(FraudRingGraphCheck::class.java)
    private val calibrator = RingGraphCalibrator()

    /**
     * @param mode "fast" | "slow" — anything else is a no-op.
     */
    fun analyze(orderId: String, mode: String): FraudAlert? {
        val span = Span.current()
        return when (mode.lowercase()) {
            "fast" -> runFast(orderId, span)
            "slow" -> runSlow(orderId, span)
            else -> null
        }
    }

    // ----- Fast path -------------------------------------------------------

    private fun runFast(orderId: String, span: Span): FraudAlert? {
        var alert: FraudAlert? = null
        val wall = measureTimeMillis {
            DatabaseConfig.getConnection().use { conn ->
                conn.prepareStatement(FAST_SQL).use { stmt ->
                    stmt.setString(1, orderId)
                    stmt.executeQuery().use { rs ->
                        if (rs.next()) {
                            val ringSize = rs.getInt("ring_size")
                            val weighted = rs.getDouble("weighted_risk")
                            span.setAttribute("app.fraud.ring_graph.ring_size", ringSize.toLong())
                            span.setAttribute("app.fraud.ring_graph.weighted_risk", weighted)
                            if (weighted >= FAST_ALERT_THRESHOLD) {
                                val risk = (weighted / 20.0).coerceAtMost(0.95)
                                alert = FraudAlert(
                                    orderId = orderId,
                                    alertType = "RING_GRAPH_FAST",
                                    severity = FraudAnalytics.SEVERITY_HIGH,
                                    reason = "Fast ring graph: size=$ringSize weight=$weighted",
                                    riskScore = risk,
                                )
                            }
                        }
                    }
                }
            }
        }
        span.setAttribute("app.fraud.ring_graph.mode", "fast")
        span.setAttribute("app.fraud.ring_graph.wall_ms", wall)
        logger.info("🕸️ Ring graph FAST: orderId=$orderId wall=${wall}ms alert=${alert != null}")
        return alert
    }

    // ----- Slow path (guardian) -------------------------------------------

    private fun runSlow(orderId: String, span: Span): FraudAlert? {
        calibrator.ensureBootstrapped()
        val amp = calibrator.current()
        var alert: FraudAlert? = null
        val wall = measureTimeMillis {
            DatabaseConfig.getConnection().use { conn ->
                conn.prepareStatement(SLOW_SQL).use { stmt ->
                    stmt.setLong(1, amp)
                    stmt.setString(2, orderId)
                    stmt.executeQuery().use { rs ->
                        if (rs.next()) {
                            val ringSize = rs.getInt("ring_size")
                            val weighted = rs.getDouble("weighted_risk")
                            span.setAttribute("app.fraud.ring_graph.ring_size", ringSize.toLong())
                            span.setAttribute("app.fraud.ring_graph.weighted_risk", weighted)
                            if (weighted >= SLOW_ALERT_THRESHOLD) {
                                val risk = (weighted / 20.0).coerceAtMost(0.95)
                                alert = FraudAlert(
                                    orderId = orderId,
                                    alertType = "RING_GRAPH_SLOW",
                                    severity = FraudAnalytics.SEVERITY_HIGH,
                                    reason = "Slow ring graph: size=$ringSize weight=$weighted",
                                    riskScore = risk,
                                )
                            }
                        }
                    }
                }
            }
        }
        span.setAttribute("app.fraud.ring_graph.mode", "slow")
        span.setAttribute("app.fraud.ring_graph.wall_ms", wall)
        span.setAttribute("app.fraud.ring_graph.amplifier", amp)
        logger.info("🕸️ Ring graph SLOW: orderId=$orderId amp=$amp wall=${wall}ms alert=${alert != null}")
        calibrator.observe(wall)
        return alert
    }

    /**
     * Adaptive amplifier for the slow path.
     *
     * Initial calibration: probes with amplifier=1000, sets amplifier so
     * one execution should land near TARGET_MS.
     *
     * Feedback loop: after every execution, if wall time falls outside
     * [LOW_BAND, HIGH_BAND] the amplifier is scaled proportionally toward
     * TARGET_MS. Values inside the deadband leave the amplifier untouched
     * so single-run jitter doesn't oscillate the knob.
     *
     * Env override: FRAUD_RING_SLOW_AMPLIFIER pins a fixed value and
     * disables calibration entirely — useful for A/B testing.
     */
    class RingGraphCalibrator {
        private val logger: Logger = LogManager.getLogger(RingGraphCalibrator::class.java)
        private val amplifier = AtomicLong(1000L)
        private val bootstrapped = AtomicLong(0L)
        private val fixedOverride: Long? =
            System.getenv("FRAUD_RING_SLOW_AMPLIFIER")?.toLongOrNull()

        fun current(): Long = amplifier.get()

        fun ensureBootstrapped() {
            if (bootstrapped.get() == 1L) return
            synchronized(this) {
                if (bootstrapped.get() == 1L) return
                if (fixedOverride != null) {
                    val pinned = fixedOverride.coerceIn(MIN_AMP, MAX_AMP)
                    amplifier.set(pinned)
                    logger.info("🎯 Ring graph amplifier pinned via FRAUD_RING_SLOW_AMPLIFIER=$pinned")
                } else {
                    calibrate()
                }
                bootstrapped.set(1L)
            }
        }

        fun observe(wallMs: Long) {
            if (fixedOverride != null) return
            if (wallMs in LOW_BAND..HIGH_BAND) return
            val safeWall = wallMs.coerceAtLeast(1)
            val cur = amplifier.get()
            val next = (cur * TARGET_MS / safeWall).coerceIn(MIN_AMP, MAX_AMP)
            if (next != cur) {
                amplifier.set(next)
                logger.warn(
                    "🎯 Ring graph amplifier recalibrated: wall=${wallMs}ms cur_amp=$cur → new_amp=$next " +
                        "(target=${TARGET_MS}ms, deadband=${LOW_BAND}..${HIGH_BAND}ms)"
                )
            }
        }

        private fun calibrate() {
            val probeAmp = 1000L
            try {
                DatabaseConfig.getConnection().use { conn ->
                    val t = measureTimeMillis {
                        conn.prepareStatement(SLOW_SQL).use { stmt ->
                            stmt.setLong(1, probeAmp)
                            stmt.setString(2, "__calibration_probe__")
                            stmt.executeQuery().use { it.next() }
                        }
                    }.coerceAtLeast(1)
                    val calibrated = (probeAmp * TARGET_MS / t).coerceIn(MIN_AMP, MAX_AMP)
                    amplifier.set(calibrated)
                    logger.info(
                        "🎯 Ring graph amplifier calibrated: probe(amp=$probeAmp)=${t}ms → " +
                            "amp=$calibrated (target=${TARGET_MS}ms)"
                    )
                }
            } catch (e: Exception) {
                logger.warn("Ring graph calibration probe failed — using default amp=${amplifier.get()}", e)
            }
        }

        companion object {
            private const val TARGET_MS = 8_000L
            private const val LOW_BAND  = 3_000L
            private const val HIGH_BAND = 12_000L
            private const val MIN_AMP   = 1_000L
            private const val MAX_AMP   = 10_000_000L
        }
    }

    companion object {
        private const val FAST_ALERT_THRESHOLD = 5.0
        private const val SLOW_ALERT_THRESHOLD = 5.0

        // Fast path — indexed 1-hop, TOP-capped, RECOMPILE.
        private val FAST_SQL = """
            WITH Seed AS (
                SELECT TOP 1 shipping_street, shipping_city
                FROM OrderLogs
                WHERE order_id = ?
            ),
            Neighbors AS (
                SELECT TOP 50 ol.order_id
                FROM OrderLogs ol
                INNER JOIN Seed s
                    ON ol.shipping_street = s.shipping_street
                    OR ol.shipping_city   = s.shipping_city
                WHERE ol.consumed_at >= DATEADD(DAY, -30, GETDATE())
            )
            SELECT COUNT(DISTINCT n.order_id) AS ring_size,
                   COALESCE(SUM(CASE fa.severity
                       WHEN 'CRITICAL' THEN 10.0
                       WHEN 'HIGH'     THEN  5.0
                       WHEN 'MEDIUM'   THEN  2.0
                       ELSE 0 END), 0) AS weighted_risk
            FROM Neighbors n
            LEFT JOIN FraudAlerts fa ON n.order_id = fa.order_id
            OPTION (RECOMPILE);
        """.trimIndent()

        // Slow path — 5-hop recursive CTE with fuzzy LIKE, cross-joined
        // with a tunable sys.all_columns amplifier. Serial + RECOMPILE
        // force real work every call; the amplifier is the primary
        // duration knob (see RingGraphCalibrator).
        private val SLOW_SQL = """
            WITH Amplifier AS (
                SELECT TOP (?) 1 AS n
                FROM sys.all_columns a CROSS JOIN sys.all_columns b
            ),
            Seed AS (
                SELECT shipping_street, shipping_city
                FROM OrderLogs
                WHERE order_id = ?
            ),
            RingHops (order_id, shipping_street, shipping_city, hop) AS (
                SELECT ol.order_id, ol.shipping_street, ol.shipping_city, 0
                FROM OrderLogs ol
                INNER JOIN Seed s
                    ON ol.shipping_street LIKE '%' + LEFT(s.shipping_street, 5) + '%'
                    OR ol.shipping_city   LIKE '%' + s.shipping_city + '%'
                WHERE ol.consumed_at >= DATEADD(DAY, -90, GETDATE())
                UNION ALL
                SELECT ol.order_id, ol.shipping_street, ol.shipping_city, rh.hop + 1
                FROM OrderLogs ol
                INNER JOIN RingHops rh
                    ON ol.shipping_street LIKE '%' + LEFT(rh.shipping_street, 5) + '%'
                    OR ol.shipping_city   LIKE '%' + rh.shipping_city + '%'
                WHERE rh.hop < 5
                    AND ol.consumed_at >= DATEADD(DAY, -90, GETDATE())
            )
            SELECT COUNT(DISTINCT rh.order_id) AS ring_size,
                   COALESCE(SUM(CASE fa.severity
                       WHEN 'CRITICAL' THEN 10.0 / (rh.hop + 1)
                       WHEN 'HIGH'     THEN  5.0 / (rh.hop + 1)
                       WHEN 'MEDIUM'   THEN  2.0 / (rh.hop + 1)
                       ELSE 0 END), 0) AS weighted_risk
            FROM RingHops rh
            LEFT JOIN FraudAlerts fa ON rh.order_id = fa.order_id
            CROSS JOIN Amplifier
            OPTION (MAXRECURSION 5, MAXDOP 1, RECOMPILE);
        """.trimIndent()
    }
}
