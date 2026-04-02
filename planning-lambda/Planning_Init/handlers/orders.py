# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Orders handler - processes incoming orders from the planning service."""

import json
import os
from typing import Any, Dict, List

from opentelemetry.trace import SpanKind, Tracer

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from shared.tracing import create_span, get_current_trace_id, get_current_span_id
from shared.logging import get_logger
from shared.lambda_client import invoke_lambda

logger = get_logger("Planning_Init.orders")

# Environment config
DOWNSTREAM_LAMBDA_ARN = os.getenv("DOWNSTREAM_LAMBDA_ARN", "")


def handle(body: Dict[str, Any], context: Any, tracer: Tracer) -> Dict[str, Any]:
    """
    Handle incoming orders from the K8s planning service.

    Args:
        body: Request body containing orders data.
        context: Lambda context.
        tracer: OpenTelemetry tracer.

    Returns:
        API Gateway response dict.
    """
    with create_span("orders.handle", kind=SpanKind.INTERNAL) as span:
        # Extract order data
        service = body.get("service", "unknown")
        timestamp = body.get("timestamp", "")
        orders_count = body.get("orders_count", 0)
        orders: List[Dict] = body.get("orders", [])

        span.set_attribute("orders.count", orders_count)
        span.set_attribute("orders.source_service", service)

        logger.info(
            f"Processing {orders_count} orders from {service}",
            extra={
                "service": service,
                "timestamp": timestamp,
                "orders_count": orders_count
            }
        )

        # Process orders
        processed = []
        for order in orders:
            order_result = process_order(order, tracer)
            processed.append(order_result)

        span.set_attribute("orders.processed", len(processed))

        # If downstream Lambda is configured, forward orders
        if DOWNSTREAM_LAMBDA_ARN:
            with create_span("orders.forward_downstream", kind=SpanKind.CLIENT) as fwd_span:
                fwd_span.set_attribute("downstream.function", DOWNSTREAM_LAMBDA_ARN)
                try:
                    downstream_payload = {
                        "source": "Planning_Init",
                        "orders": processed,
                        "original_timestamp": timestamp
                    }
                    result = invoke_lambda(DOWNSTREAM_LAMBDA_ARN, downstream_payload)
                    logger.info(
                        "Forwarded orders to downstream Lambda",
                        extra={"downstream_arn": DOWNSTREAM_LAMBDA_ARN}
                    )
                except Exception as e:
                    logger.error(f"Failed to forward to downstream: {e}")
                    fwd_span.set_attribute("error.message", str(e))

        # Build response with Lambda identity for handshake confirmation
        function_name = context.function_name if context else "Planning_Init"
        response_body = {
            "status": "success",
            "message": f"Processed {len(processed)} orders",
            "processed_count": len(processed),
            "source_service": service,
            "downstream_forwarded": bool(DOWNSTREAM_LAMBDA_ARN),
            "lambda": {
                "function_name": function_name,
                "trace_id": get_current_trace_id(),
                "span_id": get_current_span_id(),
            },
            "orders_summary": [
                {
                    "order_id": o.get("order_id"),
                    "status": o.get("status")
                }
                for o in processed[:10]  # Limit summary to first 10
            ]
        }

        return {
            "statusCode": 200,
            "body": json.dumps(response_body)
        }


def process_order(order: Dict[str, Any], tracer: Tracer) -> Dict[str, Any]:
    """
    Process a single order.

    Args:
        order: Order data dict.
        tracer: OpenTelemetry tracer.

    Returns:
        Processed order result.
    """
    order_id = order.get("order_id", "unknown")

    with create_span(f"orders.process_single", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("order.id", order_id)

        logger.info(f"Processing order: {order_id}")

        # Extract and validate order fields
        shipping_address = order.get("shipping_address", {})
        shipping_cost = order.get("shipping_cost", {})
        items_count = order.get("items_count", 0)

        span.set_attribute("order.items_count", items_count)
        span.set_attribute("order.shipping_country", shipping_address.get("country", "unknown"))

        # Perform planning logic (placeholder for actual business logic)
        planning_result = {
            "order_id": order_id,
            "status": "processed",
            "shipping_tracking_id": order.get("shipping_tracking_id"),
            "items_count": items_count,
            "shipping_cost_units": shipping_cost.get("units", 0),
            "shipping_cost_currency": shipping_cost.get("currency_code", "USD"),
            "region": determine_region(shipping_address),
            "priority": calculate_priority(order),
            "processed_at": order.get("processed_at"),
        }

        logger.info(
            f"Order {order_id} processed",
            extra={
                "order_id": order_id,
                "region": planning_result["region"],
                "priority": planning_result["priority"]
            }
        )

        return planning_result


def determine_region(address: Dict[str, Any]) -> str:
    """Determine fulfillment region based on shipping address."""
    country = address.get("country", "").upper()

    region_mapping = {
        "US": "na",
        "CA": "na",
        "MX": "na",
        "GB": "eu",
        "DE": "eu",
        "FR": "eu",
        "JP": "apac",
        "AU": "apac",
        "CN": "apac",
    }

    return region_mapping.get(country, "global")


def calculate_priority(order: Dict[str, Any]) -> str:
    """Calculate order priority based on order attributes."""
    items_count = order.get("items_count", 0)
    shipping_cost = order.get("shipping_cost", {})
    cost_units = shipping_cost.get("units", 0)

    # Simple priority logic
    if cost_units > 50:
        return "high"
    elif items_count > 5:
        return "medium"
    else:
        return "normal"
