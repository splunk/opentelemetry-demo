/*
 * Copyright The OpenTelemetry Authors
 * SPDX-License-Identifier: Apache-2.0
 */

package frauddetection

import org.apache.kafka.clients.consumer.ConsumerConfig.*
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
import dev.openfeature.sdk.Client
import dev.openfeature.sdk.EvaluationContext
import dev.openfeature.sdk.ImmutableContext
import dev.openfeature.sdk.Value
import dev.openfeature.sdk.OpenFeatureAPI

const val topic = "orders"
const val groupID = "fraud-detection"

private val logger: Logger = LogManager.getLogger(groupID)

fun main() {
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

    consumer.use {
        while (true) {
            totalCount = consumer
                .poll(ofMillis(100))
                .fold(totalCount) { accumulator, record ->
                    val newCount = accumulator + 1
                    if (getFeatureFlagValue("kafkaQueueProblems") > 0) {
                        logger.info("FeatureFlag 'kafkaQueueProblems' is enabled, sleeping 1 second")
                        Thread.sleep(1000)
                    }
                    var orders = OrderResult.parseFrom(record.value())

                    // Mutate orders to trigger fraud alerts if feature flag enabled
                    if (getFeatureFlagValue("fraudDetectionEnabled") > 0) {
                        val mutationPercentage = getFeatureFlagValue("mutateFraudOrders")
                        if (mutationPercentage > 0) {
                            orders = orderMutator.mutateOrder(orders, mutationPercentage)
                        }
                    }

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
                    }

                    // Fraud detection (controlled by feature flag)
                    if (getFeatureFlagValue("fraudDetectionEnabled") > 0) {
                        try {
                            val alert = fraudAnalytics.analyzeOrder(orders)
                            if (alert != null) {
                                fraudAlertCount++
                                logger.warn("🚨 FRAUD ALERT #$fraudAlertCount: orderId=${alert.orderId}, severity=${alert.severity}, score=${alert.riskScore}, reason=${alert.reason}")

                                // Log stats periodically
                                if (fraudAlertCount % 10L == 0L) {
                                    val stats = fraudAnalytics.getAlertStats(24)
                                    logger.info("Fraud stats (24h): $stats")
                                }
                            }
                        } catch (e: Exception) {
                            logger.error("Error during fraud analysis for order ${orders.orderId}", e)
                        }
                    }

                    // Execute bad query patterns for monitoring demo (controlled by feature flag)
                    val badQueryPercentage = getFeatureFlagValue("executeBadQueries")
                    if (badQueryPercentage > 0) {
                        try {
                            val executed = badQueryPatterns.maybeExecuteBadQuery(badQueryPercentage)
                            if (executed) {
                                logger.info("Executed bad query pattern for monitoring demo")
                            }
                        } catch (e: Exception) {
                            logger.error("Error executing bad query pattern", e)
                        }
                    }

                    newCount
                }
        }
    }
}

/**
* Retrieves the status of a feature flag from the Feature Flag service.
*
* @param ff The name of the feature flag to retrieve.
* @return `true` if the feature flag is enabled, `false` otherwise or in case of errors.
*/
fun getFeatureFlagValue(ff: String): Int {
    val client = OpenFeatureAPI.getInstance().client
    // TODO: Plumb the actual session ID from the frontend via baggage?
    val uuid = UUID.randomUUID()

    val clientAttrs = mutableMapOf<String, Value>()
    clientAttrs["session"] = Value(uuid.toString())
    client.evaluationContext = ImmutableContext(clientAttrs)
    val intValue = client.getIntegerValue(ff, 0)
    return intValue
}
