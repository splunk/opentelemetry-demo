# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Planning_Init_Lambda/handlers/orders.py.

After the per-order refactor: Init no longer iterates orders or enriches
them. Per-order processing, region/priority enrichment, and per-order
spans/metrics/logs live in Planning_Process_Lambda.processor. See
tests/unit/test_process_handler.py for those.
"""

import json
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'Planning_Init_Lambda'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.tracing import init_tracer, get_tracer
from handlers.orders import handle


class TestOrdersHandle:

    @pytest.fixture(autouse=True)
    def setup(self):
        init_tracer("test-service")
        self.tracer = get_tracer()

    def test_handle_empty_orders(self, mock_lambda_context):
        body = {"service": "planning", "orders_count": 0, "orders": []}
        response = handle(body, mock_lambda_context, self.tracer, "dev-astronomy-shop-demo-lambda")
        assert response["statusCode"] == 200
        rb = json.loads(response["body"])
        assert rb["status"] == "success"
        assert rb["orders_received"] == 0
        assert rb["downstream_forwarded"] is False  # empty list -> nothing forwarded

    def test_handle_includes_source_service(self, mock_lambda_context, sample_orders_payload):
        response = handle(sample_orders_payload, mock_lambda_context, self.tracer, "dev-astronomy-shop-demo-lambda")
        rb = json.loads(response["body"])
        assert rb["source_service"] == "planning"

    def test_handle_env_round_trip(self, mock_lambda_context, sample_orders_payload):
        response = handle(sample_orders_payload, mock_lambda_context, self.tracer, "astronomy-shop-eu-lambda")
        rb = json.loads(response["body"])
        assert rb["env"] == "astronomy-shop-eu"
        assert rb["lambda"]["deployment.environment"] == "astronomy-shop-eu-lambda"

    def test_handle_env_default_when_missing(self, mock_lambda_context, sample_orders_payload):
        response = handle(sample_orders_payload, mock_lambda_context, self.tracer)
        rb = json.loads(response["body"])
        assert rb["env"] == "unknown"
        assert rb["lambda"]["deployment.environment"] == "unknown-lambda"

    def test_no_forward_when_no_downstream_arn(self, mock_lambda_context, sample_orders_payload):
        with patch("handlers.orders.DOWNSTREAM_LAMBDA_ARN", ""):
            response = handle(sample_orders_payload, mock_lambda_context, self.tracer, "dev-astronomy-shop-demo-lambda")
        rb = json.loads(response["body"])
        assert rb["downstream_forwarded"] is False

    def test_forwards_raw_orders_unchanged(self, mock_lambda_context, sample_orders_payload):
        """Init must forward the orders list verbatim, no per-order enrichment."""
        with patch("handlers.orders.DOWNSTREAM_LAMBDA_ARN", "arn:aws:lambda:us-east-1:123:function:Downstream"):
            with patch("handlers.orders.invoke_lambda") as mock_invoke:
                mock_invoke.return_value = {"statusCode": 200, "status": "success", "processed_count": 2}
                handle(sample_orders_payload, mock_lambda_context, self.tracer, "dev-astronomy-shop-demo-lambda")

        args, kwargs = mock_invoke.call_args
        downstream_payload = args[1]
        assert downstream_payload["source"] == "Planning_Init_Lambda"
        assert downstream_payload["env"] == "dev-astronomy-shop-demo"
        assert downstream_payload["orders"] == sample_orders_payload["orders"], (
            "Init must forward orders verbatim; enrichment belongs to Process"
        )
        assert kwargs.get("env_raw") == "dev-astronomy-shop-demo"

    def test_response_carries_downstream_processed_count(self, mock_lambda_context, sample_orders_payload):
        with patch("handlers.orders.DOWNSTREAM_LAMBDA_ARN", "arn:aws:lambda:us-east-1:123:function:Downstream"):
            with patch("handlers.orders.invoke_lambda") as mock_invoke:
                mock_invoke.return_value = {"statusCode": 200, "status": "success", "processed_count": 7}
                response = handle(sample_orders_payload, mock_lambda_context, self.tracer, "astronomy-shop-us-lambda")
        rb = json.loads(response["body"])
        assert rb["downstream_processed"] == 7
        assert rb["downstream_status"] == "success"
        assert rb["downstream_forwarded"] is True
