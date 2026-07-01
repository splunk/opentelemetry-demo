# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Planning_Init_Lambda function

Entry point Lambda that receives orders from the K8s planning service.
Routes requests to appropriate handlers based on the API Gateway path.
"""

import json
import os
import sys
from typing import Any, Dict


from shared.tracing import init_tracer, extract_context, create_span, force_flush
from shared.logging import get_logger
from shared.env import extract_env, stamp as stamp_env, set_current as set_current_env
from shared import otel_logs, otel_metrics
from opentelemetry.trace import SpanKind

# Import handlers
from Planning_Init_Lambda.handlers import orders, analytics, forecasting

# Initialize
logger = get_logger("Planning_Init_Lambda")
tracer = init_tracer("Planning_Init_Lambda")
otel_metrics.init_meter("Planning_Init_Lambda")

# Route mapping
ROUTES = {
    ("POST", "/orders"): orders.handle,
    ("POST", "/analytics"): analytics.handle,
    ("POST", "/forecast"): forecasting.handle,
    # Default route for root path
    ("POST", "/"): orders.handle,
}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler with routing and tracing.

    Args:
        event: API Gateway event (HTTP API v2 format).
        context: Lambda context.

    Returns:
        API Gateway response.
    """
    # Parse body up front so extract_env can inspect its "env" field
    # before any span/log emission that would inherit the ContextVar default.
    body = event.get("body", "{}")
    body_parse_failed = False
    if isinstance(body, str):
        try:
            body = json.loads(body) if body else {}
        except json.JSONDecodeError:
            body_parse_failed = True
            body = {"raw": body}

    # Extract per-invocation env (from body, ClientContext, SNS, or HTTP header)
    # and set the ContextVar FIRST so every subsequent log/span carries the
    # correct deployment.environment for gateway routing.
    env_raw = extract_env(body if isinstance(body, dict) else {}, context)
    if env_raw == "unknown":
        env_raw = extract_env(event, context)
    set_current_env(env_raw)

    # Extract parent trace context from incoming headers
    parent_context = extract_context(event)

    # Get request details
    request_context = event.get("requestContext", {})
    http_info = request_context.get("http", {})
    method = http_info.get("method", "POST")
    path = http_info.get("path", "/")

    # Strip the stage prefix from path (e.g., /demo/orders -> /orders)
    stage = request_context.get("stage", "")
    if stage and path.startswith(f"/{stage}"):
        path = path[len(f"/{stage}") :] or "/"

    # Create root span for this Lambda invocation
    span_attributes = {
        "faas.trigger": "http",
        "http.method": method,
        "http.route": path,
        "http.target": path,
        "cloud.provider": "aws",
        "cloud.platform": "aws_lambda",
        "faas.name": context.function_name if context else "Planning_Init_Lambda",
    }

    with create_span(
        "Planning_Init_Lambda.handler",
        kind=SpanKind.SERVER,
        attributes=span_attributes,
        parent_context=parent_context
    ) as span:
        try:
            if body_parse_failed:
                logger.warning("Failed to parse request body as JSON")

            span.set_attribute("request.body_size", len(json.dumps(body)))

            env_tagged = stamp_env(span, env_raw)

            # Log request info
            headers = event.get("headers", {}) or {}
            logger.info(
                f"Received request: {method} {path}",
                extra={
                    "method": method,
                    "path": path,
                    "request_id": request_context.get("requestId"),
                    "traceparent": headers.get("traceparent", "none"),
                }
            )

            # Log full received data at DEBUG level
            logger.debug(
                "Request data",
                extra={
                    "headers": headers,
                    "body": body,
                    "raw_event": event,
                }
            )

            # Find handler for route
            route_key = (method.upper(), path)
            handler = ROUTES.get(route_key)

            if handler is None:
                # Try without trailing slash
                path_normalized = path.rstrip('/')
                route_key = (method.upper(), path_normalized)
                handler = ROUTES.get(route_key)

            if handler is None:
                logger.warning(f"No handler found for route: {method} {path}")
                span.set_attribute("error.type", "NotFound")
                return {
                    "statusCode": 404,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({
                        "error": "Not Found",
                        "message": f"No handler for {method} {path}",
                        "available_routes": list(f"{m} {p}" for m, p in ROUTES.keys())
                    })
                }

            # Call handler
            logger.info(f"Routing to handler: {handler.__module__}.{handler.__name__}")
            response = handler(body, context, tracer, env_tagged)

            # Ensure response has required fields
            if not isinstance(response, dict):
                response = {"statusCode": 200, "body": json.dumps(response)}

            if "statusCode" not in response:
                response["statusCode"] = 200

            if "headers" not in response:
                response["headers"] = {}
            response["headers"]["Content-Type"] = "application/json"

            # Ensure body is JSON string
            if "body" in response and not isinstance(response["body"], str):
                response["body"] = json.dumps(response["body"])

            span.set_attribute("http.status_code", response["statusCode"])

            logger.info(
                f"Request completed: {response['statusCode']}",
                extra={"status_code": response["statusCode"]}
            )

            # Flush spans + logs + metrics before Lambda freezes
            force_flush()
            otel_logs.force_flush()
            otel_metrics.force_flush()
            return response

        except Exception as e:
            logger.error(f"Handler error: {e}", exc_info=True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))

            # Flush spans + logs + metrics before Lambda freezes
            force_flush()
            otel_logs.force_flush()
            otel_metrics.force_flush()
            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "Internal Server Error",
                    "message": str(e)
                })
            }
