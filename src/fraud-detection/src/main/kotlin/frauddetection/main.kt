/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package frauddetection

import org.apache.kafka.clients.consumer.ConsumerConfig.*
import org.apache.kafka.clients.consumer.ConsumerRecord
import org.apache.kafka.clients.consumer.KafkaConsumer
import org.apache.kafka.common.serialization.ByteArrayDeserializer
import org.apache.kafka.common.serialization.StringDeserializer
import org.apache.logging.log4j.LogManager
import org.apache.logging.log4j.Logger
import oteldemo.Demo.*
import java.time.Duration.ofMillis
import java.util.*
import kotlin.system.exitProcess
import dev.openfeature.contrib.providers.flagd.FlagdOptions
import dev.openfeature.contrib.providers.flagd.FlagdProvider
import dev.openfeature.sdk.ImmutableContext
import dev.openfeature.sdk.Value
import dev.openfeature.sdk.OpenFeatureAPI
import io.opentelemetry.api.GlobalOpenTelemetry
import io.opentelemetry.api.trace.Span
import io.opentelemetry.api.trace.SpanKind
import io.opentelemetry.api.trace.StatusCode
import io.opentelemetry.context.Context
import io.opentelemetry.context.propagation.TextMapGetter

const val topic = "orders"
const val groupID = "fraud-detection"

private val logger: Logger = LogManager.getLogger(groupID)

/**
 * TextMapGetter implementation for extracting trace context from Kafka record headers.
 * This enables distributed tracing by propagating the parent trace context from Kafka producers.
 */
object KafkaHeadersGetter : TextMapGetter<ConsumerRecord<String, ByteArray>> {
    override fun keys(carrier: ConsumerRecord<String, ByteArray>): Iterable<String> {
        return carrier.headers().map { it.key() }
    }

    override fun get(carrier: ConsumerRecord<String, ByteArray>?, key: String): String? {
        if (carrier == null) return null
        val header = carrier.headers().lastHeader(key)
        return if (header != null) String(header.value()) else null
    }
}

fun main() {
    // Initialize flagd for Kafka experiment support
    val options = FlagdOptions.builder()
        .withGlobalTelemetry(true)
        .build()
    val flagdProvider = FlagdProvider(options)
    OpenFeatureAPI.getInstance().setProvider(flagdProvider)

    // Initialize database connection
    try {
        DatabaseConfig.initialize()
        logger.info("Database initialized successfully")
    } catch (e: Exception) {
        logger.error("Failed to initialize database", e)
        exitProcess(1)
    }

    val props = Properties()
    props[KEY_DESERIALIZER_CLASS_CONFIG] = StringDeserializer::class.java.name
    props[VALUE_DESERIALIZER_CLASS_CONFIG] = ByteArrayDeserializer::class.java.name
    props[GROUP_ID_CONFIG] = groupID
    val bootstrapServers = System.getenv("KAFKA_ADDR")
    if (bootstrapServers == null) {
        println("KAFKA_ADDR is not supplied")
        exitProcess(1)
    }
    props[BOOTSTRAP_SERVERS_CONFIG] = bootstrapServers
    val consumer = KafkaConsumer<String, ByteArray>(props).apply {
        subscribe(listOf(topic))
    }

    // Initialize repository and analytics
    val orderLogRepository = OrderLogRepository()
    val fraudAnalytics = FraudAnalytics()
    val databaseCleanup = DatabaseCleanup()
    val orderMutator = OrderMutator()
    val badQueryPatterns = BadQueryPatterns()

    // Read configuration from environment variables
    val cleanupRetentionDays = System.getenv("CLEANUP_RETENTION_DAYS")?.toIntOrNull() ?: 7
    val cleanupIntervalHours = System.getenv("CLEANUP_INTERVAL_HOURS")?.toLongOrNull() ?: 24

    // Fraud mutation percentage (5-90%)
    val fraudMutationPercentage = System.getenv("FRAUD_MUTATION_PERCENTAGE")?.toIntOrNull()?.coerceIn(5, 90) ?: 20
    logger.info("Fraud mutation percentage set to: $fraudMutationPercentage%")

    // Bad query execution percentage (disabled by default)
    val badQueryPercentage = System.getenv("BAD_QUERY_PERCENTAGE")?.toIntOrNull()?.coerceIn(0, 100) ?: 0

    // Start cleanup scheduler
    databaseCleanup.startCleanupScheduler(cleanupRetentionDays, cleanupIntervalHours)
    logger.info("Cleanup scheduler started: retentionDays=$cleanupRetentionDays, intervalHours=$cleanupIntervalHours")

    var totalCount = 0L
    var fraudAlertCount = 0L

    // Add shutdown hook to close database connection
    Runtime.getRuntime().addShutdownHook(Thread {
        logger.info("Shutting down...")
        databaseCleanup.stop()
        DatabaseConfig.close()
    })

    // Get the tracer and propagator for distributed tracing
    val tracer = GlobalOpenTelemetry.getTracer("fraud-detection")
    val propagator = GlobalOpenTelemetry.getPropagators().textMapPropagator

    consumer.use {
        while (true) {
            totalCount = consumer
                .poll(ofMillis(100))
                .fold(totalCount) { accumulator, record ->
                    val newCount = accumulator + 1

                    // Extract parent trace context from Kafka message headers
                    val parentContext = propagator.extract(Context.current(), record, KafkaHeadersGetter)

                    // Create a span for processing this message, with parent relationship to continue the trace
                    val span = tracer.spanBuilder("fraud-detection.process")
                        .setParent(parentContext)
                        .setSpanKind(SpanKind.CONSUMER)
                        .setAttribute("messaging.system", "kafka")
                        .setAttribute("messaging.destination", topic)
                        .setAttribute("messaging.operation", "process")
                        .setAttribute("messaging.kafka.partition", record.partition().toLong())
                        .setAttribute("messaging.kafka.offset", record.offset())
                        .startSpan()

                    try {
                        // Make the span current for the processing context
                        span.makeCurrent().use {
                            // Kafka experiment: Simulate consumer-side delay for lag spike demo
                            if (getFeatureFlagValue("kafkaQueueProblems") > 0) {
                                logger.info("FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second")
                                Thread.sleep(1000)
                            }

                            var orders = OrderResult.parseFrom(record.value())
                            span.setAttribute("order.id", orders.orderId)

                            // Mutate orders to trigger fraud alerts based on configured percentage
                            orders = orderMutator.mutateOrder(orders, fraudMutationPercentage)

                            logger.info("Consumed record with orderId: ${orders.orderId}, and updated total count to: $newCount")

                            // Save to database
                            try {
                                val saved = orderLogRepository.saveOrder(orders)
                                if (saved) {
                                    logger.info("Order ${orders.orderId} logged to database")
                                } else {
                                    logger.warn("Failed to log order ${orders.orderId} to database")
                                }
                            } catch (e: Exception) {
                                logger.error("Exception while logging order ${orders.orderId} to database", e)
                                span.recordException(e)
                            }

                            // Fraud detection (always enabled)
                            try {
                                val alert = fraudAnalytics.analyzeOrder(orders)
                                if (alert != null) {
                                    fraudAlertCount++
                                    span.setAttribute("fraud.detected", true)
                                    span.setAttribute("fraud.severity", alert.severity.toString())
                                    span.setAttribute("fraud.risk_score", alert.riskScore.toDouble())
                                    logger.warn("🚨 FRAUD ALERT #$fraudAlertCount: orderId=${alert.orderId}, severity=${alert.severity}, score=${alert.riskScore}, reason=${alert.reason}")

                                    // Log stats periodically
                                    if (fraudAlertCount % 10L == 0L) {
                                        val stats = fraudAnalytics.getAlertStats(24)
                                        logger.info("Fraud stats (24h): $stats")
                                    }
                                } else {
                                    span.setAttribute("fraud.detected", false)
                                }
                            } catch (e: Exception) {
                                logger.error("Error during fraud analysis for order ${orders.orderId}", e)
                                span.recordException(e)
                            }

                            // Execute bad query patterns for monitoring demo (optional)
                            if (badQueryPercentage > 0) {
                                try {
                                    val executed = badQueryPatterns.maybeExecuteBadQuery(badQueryPercentage)
                                    if (executed) {
                                        logger.info("Executed bad query pattern for monitoring demo")
                                    }
                                } catch (e: Exception) {
                                    logger.error("Error executing bad query pattern", e)
                                    span.recordException(e)
                                }
                            }

                            span.setStatus(StatusCode.OK)
                        }
                    } catch (e: Exception) {
                        span.setStatus(StatusCode.ERROR, "Failed to process message")
                        span.recordException(e)
                        logger.error("Failed to process Kafka message", e)
                    } finally {
                        span.end()
                    }

                    newCount
                }
        }
    }
}

/**
 * Retrieves the status of a feature flag from the Feature Flag service.
 * Used for Kafka queue problems experiment only.
 *
 * @param ff The name of the feature flag to retrieve.
 * @return The integer value of the feature flag, or 0 if not found or in case of errors.
 */
fun getFeatureFlagValue(ff: String): Int {
    val client = OpenFeatureAPI.getInstance().client
    val uuid = UUID.randomUUID()

    val clientAttrs = mutableMapOf<String, Value>()
    clientAttrs["session"] = Value(uuid.toString())
    client.evaluationContext = ImmutableContext(clientAttrs)
    val intValue = client.getIntegerValue(ff, 0)
    return intValue
}
