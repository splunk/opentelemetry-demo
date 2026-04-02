#!/usr/bin/env python
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Planning Service

Consumes orders from Kafka and periodically calls an AWS Lambda service.
Uses span links to connect to the original checkout trace context.
"""

import os
import sys
import signal
import threading
import time
from collections import deque
from datetime import datetime

import requests
from confluent_kafka import Consumer, KafkaException
from opentelemetry import trace, metrics
from opentelemetry.trace import SpanKind, Link, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from apscheduler.schedulers.background import BackgroundScheduler

# Import protobuf generated classes
import demo_pb2

from logger import getJSONLogger

# Configuration from environment
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "planning")
KAFKA_ADDR = os.getenv("KAFKA_ADDR", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "orders")
KAFKA_GROUP_ID = os.getenv("KAFKA_GROUP_ID", "planning")
LAMBDA_ENDPOINT = os.getenv("LAMBDA_ENDPOINT", "")
LAMBDA_CALL_INTERVAL_MINUTES = int(os.getenv("LAMBDA_CALL_INTERVAL_MINUTES", "5"))

# Initialize logger
logger = getJSONLogger(SERVICE_NAME)

# OpenTelemetry tracer and meter
tracer = trace.get_tracer(SERVICE_NAME)
meter = metrics.get_meter(SERVICE_NAME)

# Metrics
orders_consumed_counter = meter.create_counter(
    name="planning.orders_consumed",
    description="Number of orders consumed from Kafka",
    unit="1"
)
lambda_calls_counter = meter.create_counter(
    name="planning.lambda_calls",
    description="Number of Lambda service calls",
    unit="1"
)

# Propagator for extracting trace context
propagator = TraceContextTextMapPropagator()

# Thread-safe queue for collected orders
orders_lock = threading.Lock()
collected_orders = deque(maxlen=1000)  # Keep last 1000 orders

# Shutdown flag
shutdown_event = threading.Event()


def extract_span_link(record):
    """
    Extract trace context from Kafka headers and create a span link.
    This links the planning service span to the original checkout trace.
    """
    try:
        headers = record.headers() or []
        carrier = {}
        for key, value in headers:
            if value is not None:
                carrier[key] = value.decode('utf-8') if isinstance(value, bytes) else value

        ctx = propagator.extract(carrier)
        span = trace.get_current_span(ctx)
        span_context = span.get_span_context()

        if span_context.is_valid:
            return Link(
                span_context,
                attributes={"messaging.source": "kafka", "messaging.destination": KAFKA_TOPIC}
            )
    except Exception as e:
        logger.warning(f"Failed to extract span link: {e}")

    return None


def process_order(record):
    """Process a single order from Kafka."""
    try:
        # Extract span link from Kafka headers
        link = extract_span_link(record)
        links = [link] if link else []

        # Create span with link to original trace
        with tracer.start_as_current_span(
            "planning.process_order",
            kind=SpanKind.CONSUMER,
            links=links
        ) as span:
            # Parse the order
            order = demo_pb2.OrderResult()
            order.ParseFromString(record.value())

            # Set span attributes
            span.set_attribute("order.id", order.order_id)
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", KAFKA_TOPIC)
            span.set_attribute("messaging.kafka.partition", record.partition())
            span.set_attribute("messaging.kafka.offset", record.offset())

            # Extract order details for Lambda
            order_data = {
                "order_id": order.order_id,
                "shipping_tracking_id": order.shipping_tracking_id,
                "shipping_cost": {
                    "currency_code": order.shipping_cost.currency_code,
                    "units": order.shipping_cost.units,
                    "nanos": order.shipping_cost.nanos
                },
                "shipping_address": {
                    "street_address": order.shipping_address.street_address,
                    "city": order.shipping_address.city,
                    "state": order.shipping_address.state,
                    "country": order.shipping_address.country,
                    "zip_code": order.shipping_address.zip_code
                },
                "items_count": len(order.items),
                "processed_at": datetime.utcnow().isoformat()
            }

            # Add to collected orders (thread-safe)
            with orders_lock:
                collected_orders.append(order_data)

            span.set_attribute("planning.orders_collected", len(collected_orders))
            orders_consumed_counter.add(1, {"kafka.topic": KAFKA_TOPIC})

            logger.info(f"Processed order {order.order_id}, total collected: {len(collected_orders)}")

    except Exception as e:
        logger.error(f"Error processing order: {e}")
        raise


def call_lambda():
    """Call Lambda service with collected order data."""
    if not LAMBDA_ENDPOINT:
        logger.warning("LAMBDA_ENDPOINT not configured, skipping Lambda call")
        return

    with tracer.start_as_current_span(
        "planning.call_lambda",
        kind=SpanKind.CLIENT
    ) as span:
        try:
            # Get orders to send (thread-safe copy)
            with orders_lock:
                orders_to_send = list(collected_orders)

            if not orders_to_send:
                logger.info("No orders to send to Lambda")
                span.set_attribute("planning.orders_sent", 0)
                return

            span.set_attribute("http.method", "POST")
            span.set_attribute("http.url", LAMBDA_ENDPOINT)
            span.set_attribute("planning.orders_count", len(orders_to_send))

            # Prepare payload
            payload = {
                "service": SERVICE_NAME,
                "timestamp": datetime.utcnow().isoformat(),
                "orders_count": len(orders_to_send),
                "orders": orders_to_send
            }

            # Inject trace context into headers for distributed tracing
            headers = {"Content-Type": "application/json"}
            propagator.inject(headers)

            logger.info(f"Calling Lambda with {len(orders_to_send)} orders")

            response = requests.post(
                LAMBDA_ENDPOINT,
                json=payload,
                headers=headers,
                timeout=30
            )

            span.set_attribute("http.status_code", response.status_code)

            if response.ok:
                span.set_status(StatusCode.OK)
                lambda_calls_counter.add(1, {"status": "success"})
                logger.info(f"Lambda call successful: {response.status_code}")

                # Clear sent orders
                with orders_lock:
                    collected_orders.clear()
            else:
                span.set_status(StatusCode.ERROR, f"HTTP {response.status_code}")
                lambda_calls_counter.add(1, {"status": "error"})
                logger.error(f"Lambda call failed: {response.status_code} - {response.text}")

        except requests.exceptions.Timeout:
            span.set_status(StatusCode.ERROR, "Timeout")
            span.record_exception(Exception("Lambda call timed out"))
            lambda_calls_counter.add(1, {"status": "timeout"})
            logger.error("Lambda call timed out")
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.record_exception(e)
            lambda_calls_counter.add(1, {"status": "error"})
            logger.error(f"Lambda call error: {e}")


def kafka_consumer_loop():
    """Main Kafka consumer loop."""
    consumer_config = {
        'bootstrap.servers': KAFKA_ADDR,
        'group.id': KAFKA_GROUP_ID,
        'auto.offset.reset': 'earliest',
        'enable.auto.commit': True,
        'session.timeout.ms': 10000,
        'heartbeat.interval.ms': 3000,
    }

    consumer = Consumer(consumer_config)
    consumer.subscribe([KAFKA_TOPIC])

    logger.info(f"Kafka consumer started, subscribing to '{KAFKA_TOPIC}'")

    initial_call_done = False

    try:
        while not shutdown_event.is_set():
            msg = consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                logger.error(f"Kafka error: {msg.error()}")
                continue

            process_order(msg)

            # Call Lambda immediately after first order so a restart produces a trace
            if not initial_call_done and len(collected_orders) > 0:
                initial_call_done = True
                logger.info("First order received, calling Lambda immediately")
                call_lambda()

    except KafkaException as e:
        logger.error(f"Kafka exception: {e}")
    finally:
        consumer.close()
        logger.info("Kafka consumer closed")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    shutdown_event.set()


def main():
    """Main entry point."""
    logger.info(f"Starting {SERVICE_NAME} service")
    logger.info(f"Kafka: {KAFKA_ADDR}, Topic: {KAFKA_TOPIC}")
    logger.info(f"Lambda endpoint: {LAMBDA_ENDPOINT or 'NOT CONFIGURED'}")
    logger.info(f"Lambda call interval: {LAMBDA_CALL_INTERVAL_MINUTES} minutes")

    # Setup signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Setup scheduler for periodic Lambda calls
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        call_lambda,
        'interval',
        minutes=LAMBDA_CALL_INTERVAL_MINUTES,
        id='lambda_caller',
    )
    scheduler.start()
    logger.info(f"Scheduler started, Lambda will be called every {LAMBDA_CALL_INTERVAL_MINUTES} minutes")

    try:
        # Run Kafka consumer (blocking)
        kafka_consumer_loop()
    finally:
        scheduler.shutdown()
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
