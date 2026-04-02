# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Planning_Init/handlers/orders.py."""

import json
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'Planning_Init'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.tracing import init_tracer, get_tracer
from handlers.orders import (
    handle,
    process_order,
    determine_region,
    calculate_priority,
)


class TestOrdersHandle:
    """Tests for orders.handle function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup tracer for each test."""
        init_tracer("test-service")
        self.tracer = get_tracer()

    def test_handle_empty_orders(self, mock_lambda_context):
        """Handles request with no orders."""
        body = {
            "service": "planning",
            "timestamp": "2024-01-15T10:30:00Z",
            "orders_count": 0,
            "orders": []
        }

        response = handle(body, mock_lambda_context, self.tracer)

        assert response["statusCode"] == 200
        response_body = json.loads(response["body"])
        assert response_body["processed_count"] == 0
        assert response_body["status"] == "success"

    def test_handle_single_order(self, mock_lambda_context):
        """Processes single order correctly."""
        body = {
            "service": "planning",
            "timestamp": "2024-01-15T10:30:00Z",
            "orders_count": 1,
            "orders": [
                {
                    "order_id": "ORD-001",
                    "items_count": 3,
                    "shipping_address": {"country": "US"},
                    "shipping_cost": {"units": 25, "currency_code": "USD"}
                }
            ]
        }

        response = handle(body, mock_lambda_context, self.tracer)

        assert response["statusCode"] == 200
        response_body = json.loads(response["body"])
        assert response_body["processed_count"] == 1
        assert len(response_body["orders_summary"]) == 1

    def test_handle_multiple_orders(self, mock_lambda_context, sample_orders_payload):
        """Processes batch of orders."""
        response = handle(sample_orders_payload, mock_lambda_context, self.tracer)

        assert response["statusCode"] == 200
        response_body = json.loads(response["body"])
        assert response_body["processed_count"] == 2
        assert len(response_body["orders_summary"]) == 2

    def test_handle_response_includes_source_service(self, mock_lambda_context, sample_orders_payload):
        """Response includes source service name."""
        response = handle(sample_orders_payload, mock_lambda_context, self.tracer)

        response_body = json.loads(response["body"])
        assert response_body["source_service"] == "planning"

    def test_handle_limits_summary_to_ten(self, mock_lambda_context):
        """Orders summary limited to first 10 orders."""
        body = {
            "service": "planning",
            "orders_count": 15,
            "orders": [
                {"order_id": f"ORD-{i:03d}", "items_count": 1, "shipping_address": {}, "shipping_cost": {}}
                for i in range(15)
            ]
        }

        response = handle(body, mock_lambda_context, self.tracer)

        response_body = json.loads(response["body"])
        assert response_body["processed_count"] == 15
        assert len(response_body["orders_summary"]) == 10

    def test_no_forward_when_no_downstream(self, mock_lambda_context, sample_orders_payload):
        """No forward when DOWNSTREAM_LAMBDA_ARN not set."""
        with patch.dict(os.environ, {"DOWNSTREAM_LAMBDA_ARN": ""}):
            response = handle(sample_orders_payload, mock_lambda_context, self.tracer)

        response_body = json.loads(response["body"])
        assert response_body["downstream_forwarded"] is False

    def test_forward_to_downstream_lambda(self, mock_lambda_context, sample_orders_payload):
        """Forwards when DOWNSTREAM_LAMBDA_ARN set."""
        with patch.dict(os.environ, {"DOWNSTREAM_LAMBDA_ARN": "arn:aws:lambda:us-east-1:123456789012:function:Downstream"}):
            with patch('handlers.orders.invoke_lambda') as mock_invoke:
                mock_invoke.return_value = {"statusCode": 200}
                response = handle(sample_orders_payload, mock_lambda_context, self.tracer)

        response_body = json.loads(response["body"])
        assert response_body["downstream_forwarded"] is True
        mock_invoke.assert_called_once()


class TestProcessOrder:
    """Tests for process_order function."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup tracer for each test."""
        init_tracer("test-service")
        self.tracer = get_tracer()

    def test_process_order_extracts_fields(self):
        """Extracts order_id, shipping_address, etc."""
        order = {
            "order_id": "ORD-123",
            "items_count": 5,
            "shipping_tracking_id": "TRK-456",
            "processed_at": "2024-01-15T10:00:00Z",
            "shipping_address": {"country": "US", "city": "New York"},
            "shipping_cost": {"units": 30, "currency_code": "USD"}
        }

        result = process_order(order, self.tracer)

        assert result["order_id"] == "ORD-123"
        assert result["items_count"] == 5
        assert result["shipping_tracking_id"] == "TRK-456"
        assert result["shipping_cost_units"] == 30
        assert result["shipping_cost_currency"] == "USD"
        assert result["status"] == "processed"

    def test_process_order_handles_missing_fields(self):
        """Handles order with missing optional fields."""
        order = {"order_id": "ORD-MINIMAL"}

        result = process_order(order, self.tracer)

        assert result["order_id"] == "ORD-MINIMAL"
        assert result["items_count"] == 0
        assert result["status"] == "processed"

    def test_process_order_unknown_order_id(self):
        """Handles order without order_id."""
        order = {"items_count": 3}

        result = process_order(order, self.tracer)

        assert result["order_id"] == "unknown"


class TestDetermineRegion:
    """Tests for determine_region function."""

    def test_determine_region_us(self):
        """US → na."""
        assert determine_region({"country": "US"}) == "na"

    def test_determine_region_canada(self):
        """CA → na."""
        assert determine_region({"country": "CA"}) == "na"

    def test_determine_region_mexico(self):
        """MX → na."""
        assert determine_region({"country": "MX"}) == "na"

    def test_determine_region_gb(self):
        """GB → eu."""
        assert determine_region({"country": "GB"}) == "eu"

    def test_determine_region_germany(self):
        """DE → eu."""
        assert determine_region({"country": "DE"}) == "eu"

    def test_determine_region_france(self):
        """FR → eu."""
        assert determine_region({"country": "FR"}) == "eu"

    def test_determine_region_japan(self):
        """JP → apac."""
        assert determine_region({"country": "JP"}) == "apac"

    def test_determine_region_australia(self):
        """AU → apac."""
        assert determine_region({"country": "AU"}) == "apac"

    def test_determine_region_china(self):
        """CN → apac."""
        assert determine_region({"country": "CN"}) == "apac"

    def test_determine_region_unknown(self):
        """Unknown country → global."""
        assert determine_region({"country": "XY"}) == "global"

    def test_determine_region_empty(self):
        """Empty address → global."""
        assert determine_region({}) == "global"

    def test_determine_region_lowercase(self):
        """Handles lowercase country codes."""
        assert determine_region({"country": "us"}) == "na"


class TestCalculatePriority:
    """Tests for calculate_priority function."""

    def test_calculate_priority_high(self):
        """shipping_cost > 50 → high."""
        order = {"shipping_cost": {"units": 75}}
        assert calculate_priority(order) == "high"

    def test_calculate_priority_high_boundary(self):
        """shipping_cost = 51 → high."""
        order = {"shipping_cost": {"units": 51}}
        assert calculate_priority(order) == "high"

    def test_calculate_priority_medium(self):
        """items_count > 5 → medium."""
        order = {"items_count": 10, "shipping_cost": {"units": 20}}
        assert calculate_priority(order) == "medium"

    def test_calculate_priority_medium_boundary(self):
        """items_count = 6 → medium."""
        order = {"items_count": 6, "shipping_cost": {"units": 20}}
        assert calculate_priority(order) == "medium"

    def test_calculate_priority_normal(self):
        """Default → normal."""
        order = {"items_count": 2, "shipping_cost": {"units": 10}}
        assert calculate_priority(order) == "normal"

    def test_calculate_priority_high_takes_precedence(self):
        """High cost takes precedence over high item count."""
        order = {"items_count": 10, "shipping_cost": {"units": 100}}
        assert calculate_priority(order) == "high"

    def test_calculate_priority_empty_order(self):
        """Empty order → normal."""
        assert calculate_priority({}) == "normal"

    def test_calculate_priority_missing_shipping_cost(self):
        """Missing shipping_cost handled."""
        order = {"items_count": 3}
        assert calculate_priority(order) == "normal"
