# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Planning_Init/lambda_function.py."""

import json
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add Planning_Init to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'Planning_Init'))

from shared.tracing import init_tracer


class TestLambdaHandler:
    """Tests for lambda_handler function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup for each test."""
        init_tracer("test-service")

    def test_handler_routes_to_orders(self, api_event_with_orders, mock_lambda_context):
        """POST /orders routes to orders.handle."""
        from Planning_Init.lambda_function import lambda_handler

        response = lambda_handler(api_event_with_orders, mock_lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "success"

    def test_handler_routes_to_analytics(self, sample_api_gateway_event, mock_lambda_context):
        """POST /analytics routes to analytics.handle."""
        from Planning_Init.lambda_function import lambda_handler

        event = sample_api_gateway_event.copy()
        event["requestContext"]["http"]["path"] = "/analytics"
        event["body"] = json.dumps({"type": "analytics"})

        response = lambda_handler(event, mock_lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "stub"

    def test_handler_routes_to_forecast(self, sample_api_gateway_event, mock_lambda_context):
        """POST /forecast routes to forecasting.handle."""
        from Planning_Init.lambda_function import lambda_handler

        event = sample_api_gateway_event.copy()
        event["requestContext"]["http"]["path"] = "/forecast"
        event["body"] = json.dumps({"type": "forecast"})

        response = lambda_handler(event, mock_lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "stub"

    def test_handler_root_routes_to_orders(self, sample_api_gateway_event, mock_lambda_context, sample_orders_payload):
        """POST / defaults to orders.handle."""
        from Planning_Init.lambda_function import lambda_handler

        event = sample_api_gateway_event.copy()
        event["requestContext"]["http"]["path"] = "/"
        event["body"] = json.dumps(sample_orders_payload)

        response = lambda_handler(event, mock_lambda_context)

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["status"] == "success"

    def test_handler_404_unknown_route(self, sample_api_gateway_event, mock_lambda_context):
        """Unknown path returns 404 with available routes."""
        from Planning_Init.lambda_function import lambda_handler

        event = sample_api_gateway_event.copy()
        event["requestContext"]["http"]["path"] = "/unknown"
        event["body"] = "{}"

        response = lambda_handler(event, mock_lambda_context)

        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert "error" in body
        assert "available_routes" in body

    def test_handler_extracts_trace_context(self, api_event_with_orders, mock_lambda_context, sample_traceparent):
        """Trace context extracted from headers."""
        from Planning_Init.lambda_function import lambda_handler

        # Ensure traceparent is in headers
        api_event_with_orders["headers"]["traceparent"] = sample_traceparent

        response = lambda_handler(api_event_with_orders, mock_lambda_context)

        assert response["statusCode"] == 200

    def test_handler_parses_json_body(self, sample_api_gateway_event, mock_lambda_context):
        """JSON body parsed correctly."""
        from Planning_Init.lambda_function import lambda_handler

        payload = {"test": "data", "number": 42}
        event = sample_api_gateway_event.copy()
        event["body"] = json.dumps(payload)

        response = lambda_handler(event, mock_lambda_context)

        assert response["statusCode"] == 200

    def test_handler_invalid_json_body(self, sample_api_gateway_event, mock_lambda_context):
        """Invalid JSON handled gracefully."""
        from Planning_Init.lambda_function import lambda_handler

        event = sample_api_gateway_event.copy()
        event["body"] = "not valid json {"

        response = lambda_handler(event, mock_lambda_context)

        # Should not crash, handler continues with raw body
        assert response["statusCode"] in [200, 404]

    def test_handler_empty_body(self, sample_api_gateway_event, mock_lambda_context):
        """Empty body handled correctly."""
        from Planning_Init.lambda_function import lambda_handler

        event = sample_api_gateway_event.copy()
        event["body"] = ""

        response = lambda_handler(event, mock_lambda_context)

        assert response["statusCode"] == 200

    def test_handler_null_body(self, sample_api_gateway_event, mock_lambda_context):
        """Null body handled correctly."""
        from Planning_Init.lambda_function import lambda_handler

        event = sample_api_gateway_event.copy()
        event["body"] = None

        response = lambda_handler(event, mock_lambda_context)

        assert response["statusCode"] == 200

    def test_handler_ensures_response_format(self, api_event_with_orders, mock_lambda_context):
        """Response always has statusCode, headers, body."""
        from Planning_Init.lambda_function import lambda_handler

        response = lambda_handler(api_event_with_orders, mock_lambda_context)

        assert "statusCode" in response
        assert "headers" in response
        assert "body" in response
        assert response["headers"]["Content-Type"] == "application/json"
        assert isinstance(response["body"], str)

    def test_handler_exception_returns_500(self, sample_api_gateway_event, mock_lambda_context):
        """Handler exception returns 500 response."""
        from Planning_Init.lambda_function import lambda_handler

        event = sample_api_gateway_event.copy()
        event["body"] = json.dumps({"orders": []})

        # Patch handler to raise exception
        with patch('Planning_Init.lambda_function.orders.handle', side_effect=RuntimeError("Test error")):
            response = lambda_handler(event, mock_lambda_context)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert "error" in body
        assert "Internal Server Error" in body["error"]

    def test_handler_without_context(self, api_event_with_orders):
        """Handler works when context is None."""
        from Planning_Init.lambda_function import lambda_handler

        response = lambda_handler(api_event_with_orders, None)

        assert response["statusCode"] == 200
