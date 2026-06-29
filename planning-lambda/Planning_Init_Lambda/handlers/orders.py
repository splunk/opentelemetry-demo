# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Orders handler - receives orders from the K8s planning service and
forwards them to Planning_Process_Lambda for per-order work.

Init no longer iterates per-order spans -- that was duplicating work
the downstream Process Lambda already does. Init now records a single
summary span (`orders.handle`) plus the outgoing invoke (`orders.forward_downstream`
-> `Lambda.Invoke...`). Per-order spans, metrics, and logs live in
Process.
"""

import json
import os
from typing import Any, Dict, List

from opentelemetry.trace import SpanKind, Tracer

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))

from shared.tracing import create_span, get_current_trace_id, get_current_span_id
from shared.logging import get_logger
from shared.lambda_client import invoke_lambda
from shared.env import STAMPED_ATTR, BARE_ENV_KEY, UNKNOWN_ENV, LAMBDA_SUFFIX

logger = get_logger("Planning_Init_Lambda.orders")

# Environment config
DOWNSTREAM_LAMBDA_ARN = os.getenv("DOWNSTREAM_LAMBDA_ARN", "")


def handle(body: Dict[str, Any], context: Any, tracer: Tracer, env_tagged: str = f"{UNKNOWN_ENV}{LAMBDA_SUFFIX}") -> Dict[str, Any]:
    """
    Receive orders from the K8s planning service, forward them to
    Planning_Process_Lambda, and return a summary response.
    """
    env_raw = env_tagged[:-len(LAMBDA_SUFFIX)] if env_tagged.endswith(LAMBDA_SUFFIX) else env_tagged

    with create_span("orders.handle", kind=SpanKind.INTERNAL) as span:
        span.set_attribute(STAMPED_ATTR, env_tagged)

        service = body.get("service", "unknown")
        timestamp = body.get("timestamp", "")
        orders_count = body.get("orders_count", 0)
        orders: List[Dict] = body.get("orders", [])

        span.set_attribute("orders.count", orders_count)
        span.set_attribute("orders.received", len(orders))
        span.set_attribute("orders.source_service", service)

        logger.info(
            f"Received {len(orders)} orders from {service}, forwarding to Process",
            extra={
                "service": service,
                "timestamp": timestamp,
                "orders_count": orders_count,
            },
        )

        downstream_status = "skipped"
        downstream_processed = 0

        if DOWNSTREAM_LAMBDA_ARN and orders:
            with create_span("orders.forward_downstream", kind=SpanKind.CLIENT) as fwd_span:
                fwd_span.set_attribute("downstream.function", DOWNSTREAM_LAMBDA_ARN)
                fwd_span.set_attribute(STAMPED_ATTR, env_tagged)
                try:
                    downstream_payload = {
                        "source": "Planning_Init_Lambda",
                        BARE_ENV_KEY: env_raw,
                        "orders": orders,
                        "original_timestamp": timestamp,
                    }
                    result = invoke_lambda(
                        DOWNSTREAM_LAMBDA_ARN,
                        downstream_payload,
                        env_raw=env_raw,
                        peer_service="Planning_Process_Lambda",
                    )
                    if isinstance(result, dict):
                        downstream_processed = int(result.get("processed_count", 0))
                        downstream_status = result.get("status", "unknown")
                    logger.info(
                        "Forwarded orders to downstream Lambda",
                        extra={
                            "downstream_arn": DOWNSTREAM_LAMBDA_ARN,
                            "env": env_raw,
                            "downstream_processed": downstream_processed,
                        },
                    )
                except Exception as e:
                    downstream_status = "error"
                    logger.error(f"Failed to forward to downstream: {e}")
                    fwd_span.set_attribute("error.message", str(e))

        function_name = context.function_name if context else "Planning_Init_Lambda"
        response_body = {
            "status": "success",
            "message": f"Forwarded {len(orders)} orders",
            "orders_received": len(orders),
            "source_service": service,
            BARE_ENV_KEY: env_raw,
            "downstream_forwarded": bool(DOWNSTREAM_LAMBDA_ARN and orders),
            "downstream_status": downstream_status,
            "downstream_processed": downstream_processed,
            "lambda": {
                "function_name": function_name,
                "trace_id": get_current_trace_id(),
                "span_id": get_current_span_id(),
                STAMPED_ATTR: env_tagged,
            },
        }

        return {
            "statusCode": 200,
            "body": json.dumps(response_body),
        }
