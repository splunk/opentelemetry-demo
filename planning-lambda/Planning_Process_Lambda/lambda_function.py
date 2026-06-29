# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Planning_Process_Lambda function

Invoked synchronously by Planning_Init_Lambda via boto3 lambda.invoke
(RequestResponse). Receives a payload of pre-processed orders forwarded
from Init, processes each, and emits traces, metrics, and logs over OTLP
to the gateway collector with the per-invocation `deployment.environment`
attribute stamped on every signal.
"""

import json
import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.tracing import init_tracer, create_span, force_flush, extract_context_from_invoke
from shared.logging import get_logger
from shared.env import extract_env, stamp as stamp_env, set_current as set_current_env
from shared import otel_logs, otel_metrics
from opentelemetry.trace import SpanKind

from Planning_Process_Lambda.processor import process_orders

logger = get_logger("Planning_Process_Lambda")
tracer = init_tracer("Planning_Process_Lambda")
otel_metrics.init_meter("Planning_Process_Lambda")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Handle an invocation from Planning_Init_Lambda.

    The event is the JSON payload Init forwarded (already a dict when
    delivered via lambda.invoke). Env arrives in three possible places,
    in priority order: event["env"] (body field), ClientContext.custom["env"],
    or HTTP-header-style headers["x-demo-env"] (not used here but
    supported by `extract_env`).
    """
    env_raw = extract_env(event, context)
    set_current_env(env_raw)

    # Stitch this invocation onto the caller's trace by extracting the
    # propagated W3C context from the invoke payload / ClientContext.
    parent_ctx = extract_context_from_invoke(event, context)

    span_attributes = {
        "faas.trigger": "other",
        "cloud.provider": "aws",
        "cloud.platform": "aws_lambda",
        "faas.name": context.function_name if context else "Planning_Process_Lambda",
    }

    with create_span(
        "Planning_Process_Lambda.handler",
        kind=SpanKind.SERVER,
        attributes=span_attributes,
        parent_context=parent_ctx,
    ) as span:
        env_tagged = stamp_env(span, env_raw)

        try:
            source = event.get("source", "unknown")
            orders = event.get("orders", []) or []
            original_timestamp = event.get("original_timestamp")

            span.set_attribute("source", source)
            span.set_attribute("orders.count", len(orders))

            logger.info(
                f"Received {len(orders)} orders from {source}",
                extra={
                    "source": source,
                    "orders_count": len(orders),
                    "original_timestamp": original_timestamp,
                },
            )

            results = process_orders(orders, env_tagged=env_tagged)

            response = {
                "statusCode": 200,
                "status": "success",
                "env": env_raw,
                "processed_count": len(results),
                "lambda": {
                    "function_name": context.function_name if context else "Planning_Process_Lambda",
                    "deployment.environment": env_tagged,
                },
                "results_summary": results[:10],
            }

            logger.info(
                f"Processed {len(results)} orders",
                extra={"processed_count": len(results)},
            )

            force_flush()
            otel_logs.force_flush()
            otel_metrics.force_flush()
            return response

        except Exception as e:
            logger.error(f"Handler error: {e}", exc_info=True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))

            force_flush()
            otel_logs.force_flush()
            otel_metrics.force_flush()
            return {
                "statusCode": 500,
                "status": "error",
                "error": str(e),
            }
