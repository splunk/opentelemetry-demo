# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Per-order processing logic for Planning_Process_Lambda.

Owns the per-order work that used to live in Planning_Init_Lambda:
  - enrich each order with region + priority
  - open an `orders.process_single` span stamped with the per-invocation env
  - increment the `orders.processed` counter (env attribute attached)
  - emit an INFO log line via the OTLP-wired logger

All three signals carry `deployment.environment = "<env>-lambda"`, so the
gateway routing connector fans them out to the same Splunk Observability
+ HEC org as the originating cluster.
"""

from typing import Any, Dict, List, Optional

from opentelemetry import metrics as otel_metrics
from opentelemetry.trace import SpanKind

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.tracing import create_span
from shared.logging import get_logger
from shared import otel_metrics as otel_metrics_helper
from shared.env import STAMPED_ATTR, UNKNOWN_ENV, LAMBDA_SUFFIX

logger = get_logger("Planning_Process_Lambda.processor")

_counter: Optional[otel_metrics.Counter] = None


def _get_counter() -> otel_metrics.Counter:
    """Lazy-create the per-cold-start counter instrument."""
    global _counter
    if _counter is None:
        meter = otel_metrics_helper.init_meter("Planning_Process_Lambda")
        _counter = meter.create_counter(
            name="orders.processed",
            unit="1",
            description="Orders processed by Planning_Process_Lambda",
        )
    return _counter


def determine_region(address: Dict[str, Any]) -> str:
    """Map a shipping address country to a fulfillment region."""
    country = address.get("country", "").upper()
    region_mapping = {
        "US": "na", "CA": "na", "MX": "na",
        "GB": "eu", "DE": "eu", "FR": "eu",
        "JP": "apac", "AU": "apac", "CN": "apac",
    }
    return region_mapping.get(country, "global")


def calculate_priority(order: Dict[str, Any]) -> str:
    """Compute order priority from items_count + shipping_cost."""
    items_count = order.get("items_count", 0)
    shipping_cost = order.get("shipping_cost", {})
    cost_units = shipping_cost.get("units", 0)

    if cost_units > 50:
        return "high"
    if items_count > 5:
        return "medium"
    return "normal"


def _enrich(order: Dict[str, Any]) -> Dict[str, Any]:
    """Apply the per-order enrichment that was previously done in Init."""
    shipping_address = order.get("shipping_address", {}) or {}
    shipping_cost = order.get("shipping_cost", {}) or {}
    return {
        "order_id": order.get("order_id", "unknown"),
        "status": "processed",
        "shipping_tracking_id": order.get("shipping_tracking_id"),
        "items_count": order.get("items_count", 0),
        "shipping_cost_units": shipping_cost.get("units", 0),
        "shipping_cost_currency": shipping_cost.get("currency_code", "USD"),
        "region": determine_region(shipping_address),
        "priority": calculate_priority(order),
        "processed_at": order.get("processed_at"),
    }


def process_orders(
    orders: List[Dict[str, Any]],
    env_tagged: str = f"{UNKNOWN_ENV}{LAMBDA_SUFFIX}",
) -> List[Dict[str, Any]]:
    """Process a batch of orders. Returns a parallel list of enriched results."""
    counter = _get_counter()
    results: List[Dict[str, Any]] = []

    with create_span("Planning_Process_Lambda.batch", kind=SpanKind.INTERNAL) as batch_span:
        batch_span.set_attribute(STAMPED_ATTR, env_tagged)
        batch_span.set_attribute("orders.batch_size", len(orders))

        for order in orders:
            enriched = _enrich(order)
            order_id = enriched["order_id"]

            with create_span("orders.process_single", kind=SpanKind.INTERNAL) as span:
                span.set_attribute(STAMPED_ATTR, env_tagged)
                span.set_attribute("order.id", order_id)
                span.set_attribute("order.items_count", enriched["items_count"])
                span.set_attribute("order.region", enriched["region"])
                span.set_attribute("order.priority", enriched["priority"])

                counter.add(1, attributes=otel_metrics_helper.env_attrs({
                    "order.priority": enriched["priority"],
                    "order.region": enriched["region"],
                }))

                logger.info(
                    f"Processed order {order_id}",
                    extra={
                        "order_id": order_id,
                        "region": enriched["region"],
                        "priority": enriched["priority"],
                        "env_tagged": env_tagged,
                    },
                )

                results.append(enriched)

    return results
