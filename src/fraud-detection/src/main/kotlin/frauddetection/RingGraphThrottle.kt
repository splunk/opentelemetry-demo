/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package frauddetection

import org.apache.kafka.clients.consumer.ConsumerRecord
import org.apache.kafka.clients.consumer.KafkaConsumer
import org.apache.logging.log4j.LogManager
import org.apache.logging.log4j.Logger
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/**
 * Adaptive backpressure for the ring-graph check.
 *
 * Decides, per Kafka message, whether the ring-graph query should run.
 * When consumer lag exceeds LAG_HI_MS the throttle tightens: it starts
 * skipping every 2nd message, then every 3rd, etc. When lag drops below
 * LAG_LO_MS it relaxes one step per message. 4-second deadband between
 * LAG_HI and LAG_LO prevents oscillation.
 *
 * Skip pattern given skipCount = N:
 *   - N = 0  → run every message              (no throttling)
 *   - N = 1  → run 1 of every 2 messages
 *   - N = 5  → run 1 of every 6 messages
 *   - N = 99 → run 1 of every 100 messages    (near-full mute, DBMon still fed)
 *
 * Lag signal (best-available):
 *   1. x-produce-time header (Long epoch ms, set by producer) — most
 *      accurate, immune to broker timestamp policy (LogAppendTime vs
 *      CreateTime). Set by checkout as of the guardian-demo release.
 *   2. records-lag-max consumer metric — offset gap between last-
 *      consumed and log-end, converted to a time estimate using the
 *      AVG_MS_PER_MSG assumption (~1 msg/sec at demo load rates).
 *   3. record.timestamp() — Kafka's per-record timestamp. Reflects
 *      broker append time when topic uses LogAppendTime, not producer
 *      wall-clock, so this is the least reliable of the three.
 *
 * Preference order guarantees the throttle always has *some* signal
 * even during rolling upgrades where the producer hasn't been rebuilt
 * yet.
 *
 * State is in-memory only. Pod restart resets to 0. No persistence
 * needed — the throttle re-converges within seconds under load.
 */
class RingGraphThrottle {
    private val logger: Logger = LogManager.getLogger(RingGraphThrottle::class.java)
    private val skipCount = AtomicInteger(0)
    private val msgCounter = AtomicLong(0)

    /** Current skip level. */
    fun skipCount(): Int = skipCount.get()

    /**
     * Estimate lag (ms) for a single record using the best signal
     * available. See class doc for source-of-truth ordering.
     */
    fun estimateLagMs(
        record: ConsumerRecord<*, *>,
        consumer: KafkaConsumer<*, *>,
    ): Long {
        // 1. x-produce-time header — most accurate.
        val header = record.headers().lastHeader(PRODUCE_TIME_HEADER)
        if (header != null) {
            val produceTime = header.value().toString(Charsets.UTF_8).toLongOrNull()
            if (produceTime != null && produceTime > 0) {
                return System.currentTimeMillis() - produceTime
            }
        }
        // 2. Kafka consumer metric records-lag-max (offset units) →
        // multiply by an assumed inter-message interval to get a
        // rough time estimate. Only good when production is roughly
        // steady, which matches the astronomy-loadgen demo shape.
        val lagOffsets = readRecordsLagMax(consumer)
        if (lagOffsets != null && lagOffsets >= 0) {
            return lagOffsets * AVG_MS_PER_MSG
        }
        // 3. Kafka record.timestamp() — least reliable (see class doc).
        return System.currentTimeMillis() - record.timestamp()
    }

    private fun readRecordsLagMax(consumer: KafkaConsumer<*, *>): Long? {
        return try {
            val metric = consumer.metrics().entries.firstOrNull { it.key.name() == "records-lag-max" }
            val value = metric?.value?.metricValue() as? Double
            value?.toLong()
        } catch (e: Exception) {
            null
        }
    }

    /**
     * Decide whether to skip the ring-graph check for the current
     * message. Updates internal state based on lag before deciding.
     * Logs at INFO only when the skip level actually changes, to avoid
     * per-message spam.
     */
    fun shouldSkip(lagMs: Long): Boolean {
        val before = skipCount.get()
        val next = when {
            lagMs > LAG_HI_MS -> (before + 1).coerceAtMost(MAX_SKIP)
            lagMs < LAG_LO_MS -> (before - 1).coerceAtLeast(0)
            else -> before
        }
        if (next != before) {
            skipCount.set(next)
            logger.info(
                "🚦 Ring graph throttle: lag=${lagMs}ms " +
                    "skip_count $before → $next " +
                    "(deadband=${LAG_LO_MS}..${LAG_HI_MS}ms, cap=$MAX_SKIP)"
            )
        }

        val n = msgCounter.incrementAndGet()
        return (n % (next + 1L)) != 0L
    }

    companion object {
        private const val PRODUCE_TIME_HEADER = "x-produce-time"
        // Lag thresholds — match what Splunk APM shows on the kafka →
        // fraud-detection edge (producer span end → consumer span
        // start) when the x-produce-time header is available.
        private const val LAG_HI_MS = 15_000L   // start throttling above this
        private const val LAG_LO_MS = 11_000L   // relax below this
        // Cap so counter doesn't grow unbounded under sustained
        // backpressure. 100 means 1 in 101 messages fire — still
        // enough to keep DBMon populated with the slow query.
        private const val MAX_SKIP = 100
        // Assumed inter-message interval used to convert offset-based
        // records-lag-max into a rough time estimate when the
        // x-produce-time header is unavailable. Tuned for astronomy-
        // loadgen's ~1 order/sec cadence. Override via env if needed.
        private val AVG_MS_PER_MSG: Long =
            System.getenv("RING_GRAPH_AVG_MS_PER_MSG")?.toLongOrNull() ?: 1000L
    }
}
