# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Planning_Init Lambda Function

Entry point Lambda that receives orders from the K8s planning service.
Routes requests to appropriate handlers based on the API Gateway path.
"""

import json
import os
import sys
from typing import Any, Dict

# Add shared utilities to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from shared.tracing import init_tracer, extract_context, create_span
from shared.logging import get_logger
from opentelemetry.trace import SpanKind

# Import handlers
from handlers import orders, analytics, forecasting

# Initialize
logger = get_logger("Planning_Init")
tracer = init_tracer("Planning_Init")

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
    # Extract parent trace context from incoming headers
    parent_context = extract_context(event)

    # Get request details
    request_context = event.get("requestContext", {})
    http_info = request_context.get("http", {})
    method = http_info.get("method", "POST")
    path = http_info.get("path", "/")

    # Create root span for this Lambda invocation
    span_attributes = {
        "faas.trigger": "http",
        "http.method": method,
        "http.route": path,
        "http.target": path,
        "cloud.provider": "aws",
        "cloud.platform": "aws_lambda",
        "faas.name": context.function_name if context else "Planning_Init",
    }

    with create_span(
        "Planning_Init.handler",
        kind=SpanKind.SERVER,
        attributes=span_attributes,
        parent_context=parent_context
    ) as span:
        try:
            # Log request
            logger.info(
                f"Received request: {method} {path}",
                extra={
                    "method": method,
                    "path": path,
                    "request_id": request_context.get("requestId"),
                }
            )

            # Parse body
            body = event.get("body", "{}")
            if isinstance(body, str):
                try:
                    body = json.loads(body) if body else {}
                except json.JSONDecodeError:
                    logger.warning("Failed to parse request body as JSON")
                    body = {"raw": body}

            span.set_attribute("request.body_size", len(json.dumps(body)))

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
            response = handler(body, context, tracer)

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

            return response

        except Exception as e:
            logger.error(f"Handler error: {e}", exc_info=True)
            span.set_attribute("error.type", type(e).__name__)
            span.set_attribute("error.message", str(e))

            return {
                "statusCode": 500,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({
                    "error": "Internal Server Error",
                    "message": str(e)
                })
            }
