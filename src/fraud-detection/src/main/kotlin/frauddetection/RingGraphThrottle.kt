/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package frauddetection

import org.apache.logging.log4j.LogManager
import org.apache.logging.log4j.Logger
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

/**
 * Adaptive backpressure for the ring-graph check.
 *
 * Decides, per Kafka message, whether the ring-graph query should run.
 * When consumer lag (measured as wall clock − record.timestamp()) exceeds
 * LAG_HI_MS the throttle tightens: it starts skipping every 2nd message,
 * then every 3rd, then every 4th, and so on. When lag drops below
 * LAG_LO_MS it relaxes one step per message.
 *
 * A 4-second deadband between LAG_HI and LAG_LO prevents oscillation.
 *
 * Skip pattern given skipCount = N:
 *   - N = 0  → run every message              (no throttling)
 *   - N = 1  → run 1 of every 2 messages
 *   - N = 5  → run 1 of every 6 messages
 *   - N = 99 → run 1 of every 100 messages    (near-full mute, still visible)
 *
 * State is in-memory only. Pod restart resets to 0. No persistence needed —
 * the throttle re-converges within seconds under load.
 */
class RingGraphThrottle {
    private val logger: Logger = LogManager.getLogger(RingGraphThrottle::class.java)
    private val skipCount = AtomicInteger(0)
    private val msgCounter = AtomicLong(0)

    /** Current skip level (mostly for logging / commented span attributes). */
    fun skipCount(): Int = skipCount.get()

    /**
     * Decide whether to skip the ring-graph check for the current message.
     * Updates internal state based on lag before deciding. Logs at INFO
     * only when the skip level actually changes, to avoid per-message spam.
     */
    fun shouldSkip(msgAgeMs: Long): Boolean {
        val before = skipCount.get()
        val next = when {
            msgAgeMs > LAG_HI_MS -> (before + 1).coerceAtMost(MAX_SKIP)
            msgAgeMs < LAG_LO_MS -> (before - 1).coerceAtLeast(0)
            else -> before
        }
        if (next != before) {
            skipCount.set(next)
            logger.info(
                "🚦 Ring graph throttle: lag=${msgAgeMs}ms " +
                    "skip_count ${before} → ${next} " +
                    "(deadband=${LAG_LO_MS}..${LAG_HI_MS}ms, cap=$MAX_SKIP)"
            )
        }

        val n = msgCounter.incrementAndGet()
        // skipCount=0 → (skipCount+1)=1 → n % 1 == 0 always → runs every msg
        // skipCount=k → runs every (k+1)-th message, skips k in between
        return (n % (next + 1L)) != 0L
    }

    companion object {
        // Lag thresholds — same signal Splunk APM shows on the kafka →
        // fraud-detection edge (producer span end → consumer span start).
        private const val LAG_HI_MS = 15_000L   // start throttling above this
        private const val LAG_LO_MS = 11_000L   // relax below this
        // Cap so counter doesn't grow unbounded under sustained backpressure.
        // 100 means 1 in 101 messages fire — still enough to keep DBMon
        // populated with the slow query.
        private const val MAX_SKIP = 100
    }
}
