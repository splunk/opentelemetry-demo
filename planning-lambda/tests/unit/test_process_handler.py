# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for Planning_Process_Lambda."""

import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'Planning_Process_Lambda'))

from shared.tracing import init_tracer
from shared import otel_metrics
from Planning_Process_Lambda.lambda_function import lambda_handler
from Planning_Process_Lambda.processor import (
    process_orders,
    _get_counter,
    _enrich,
    determine_region,
    calculate_priority,
)


@pytest.fixture(autouse=True)
def setup_tracer():
    init_tracer("test-process")


@pytest.fixture(autouse=True)
def reset_counter():
    """Reset module-level counter between tests so init_meter is re-called."""
    import Planning_Process_Lambda.processor as proc
    proc._counter = None
    otel_metrics._meter = None
    otel_metrics._provider = None
    yield
    proc._counter = None
    otel_metrics._meter = None
    otel_metrics._provider = None


def _ctx(name="Planning_Process_Lambda"):
    c = MagicMock()
    c.function_name = name
    c.aws_request_id = "test-req"
    return c


class TestLambdaHandler:
    def test_handler_processes_payload_from_init(self):
        event = {
            "source": "Planning_Init_Lambda",
            "env": "dev-astronomy-shop-demo",
            "orders": [
                {"order_id": "ORD-001", "items_count": 2, "priority": "high", "region": "na"},
                {"order_id": "ORD-002", "items_count": 5, "priority": "normal", "region": "eu"},
            ],
            "original_timestamp": "2026-06-16T10:00:00Z",
        }
        resp = lambda_handler(event, _ctx())
        assert resp["statusCode"] == 200
        assert resp["status"] == "success"
        assert resp["env"] == "dev-astronomy-shop-demo"
        assert resp["processed_count"] == 2
        assert resp["lambda"]["deployment.environment"] == "dev-astronomy-shop-demo-lambda"
        assert len(resp["results_summary"]) == 2

    def test_handler_with_no_orders(self):
        event = {"source": "Planning_Init_Lambda", "env": "astronomy-shop-eu", "orders": []}
        resp = lambda_handler(event, _ctx())
        assert resp["statusCode"] == 200
        assert resp["processed_count"] == 0
        assert resp["env"] == "astronomy-shop-eu"
        assert resp["lambda"]["deployment.environment"] == "astronomy-shop-eu-lambda"

    def test_handler_env_from_client_context_when_missing_in_body(self):
        event = {"source": "Planning_Init_Lambda", "orders": []}
        ctx = _ctx()
        ctx.client_context.custom = {"env": "astronomy-shop-us"}
        resp = lambda_handler(event, ctx)
        assert resp["env"] == "astronomy-shop-us"
        assert resp["lambda"]["deployment.environment"] == "astronomy-shop-us-lambda"

    def test_handler_env_defaults_to_unknown(self):
        event = {"source": "Planning_Init_Lambda", "orders": []}
        ctx = _ctx()
        ctx.client_context = None
        resp = lambda_handler(event, ctx)
        assert resp["env"] == "unknown"
        assert resp["lambda"]["deployment.environment"] == "unknown-lambda"


class TestProcessOrders:
    def test_returns_one_result_per_order(self):
        orders = [
            {"order_id": "A", "items_count": 1, "shipping_address": {"country": "US"}, "shipping_cost": {"units": 10}},
            {"order_id": "B", "items_count": 3, "shipping_address": {"country": "DE"}, "shipping_cost": {"units": 75}},
            {"order_id": "C", "items_count": 7, "shipping_address": {"country": "JP"}, "shipping_cost": {"units": 20}},
        ]
        results = process_orders(orders, env_tagged="dev-astronomy-shop-demo-lambda")
        assert len(results) == 3
        assert [r["order_id"] for r in results] == ["A", "B", "C"]
        assert all(r["status"] == "processed" for r in results)
        assert results[1]["priority"] == "high"   # cost 75 -> high
        assert results[2]["region"] == "apac"     # JP -> apac

    def test_missing_order_id_falls_back_to_unknown(self):
        results = process_orders([{"items_count": 1}], env_tagged="astronomy-shop-eu-lambda")
        assert results[0]["order_id"] == "unknown"

    def test_enriches_with_region_and_priority(self):
        orders = [
            {"order_id": "X", "items_count": 1, "shipping_address": {"country": "GB"}, "shipping_cost": {"units": 60}},
        ]
        results = process_orders(orders, env_tagged="astronomy-shop-eu-lambda")
        assert results[0]["region"] == "eu"
        assert results[0]["priority"] == "high"  # cost > 50


class TestDetermineRegion:
    def test_us(self): assert determine_region({"country": "US"}) == "na"
    def test_ca(self): assert determine_region({"country": "CA"}) == "na"
    def test_mx(self): assert determine_region({"country": "MX"}) == "na"
    def test_gb(self): assert determine_region({"country": "GB"}) == "eu"
    def test_de(self): assert determine_region({"country": "DE"}) == "eu"
    def test_fr(self): assert determine_region({"country": "FR"}) == "eu"
    def test_jp(self): assert determine_region({"country": "JP"}) == "apac"
    def test_au(self): assert determine_region({"country": "AU"}) == "apac"
    def test_cn(self): assert determine_region({"country": "CN"}) == "apac"
    def test_unknown(self): assert determine_region({"country": "XY"}) == "global"
    def test_empty(self): assert determine_region({}) == "global"
    def test_lowercase(self): assert determine_region({"country": "us"}) == "na"


class TestCalculatePriority:
    def test_high(self):
        assert calculate_priority({"shipping_cost": {"units": 75}}) == "high"

    def test_high_boundary(self):
        assert calculate_priority({"shipping_cost": {"units": 51}}) == "high"

    def test_medium(self):
        assert calculate_priority({"items_count": 10, "shipping_cost": {"units": 20}}) == "medium"

    def test_medium_boundary(self):
        assert calculate_priority({"items_count": 6, "shipping_cost": {"units": 20}}) == "medium"

    def test_normal(self):
        assert calculate_priority({"items_count": 2, "shipping_cost": {"units": 10}}) == "normal"

    def test_high_takes_precedence(self):
        assert calculate_priority({"items_count": 10, "shipping_cost": {"units": 100}}) == "high"

    def test_empty(self):
        assert calculate_priority({}) == "normal"

    def test_missing_shipping_cost(self):
        assert calculate_priority({"items_count": 3}) == "normal"


class TestEnrich:
    def test_enriches_full_order(self):
        order = {
            "order_id": "E-1",
            "items_count": 4,
            "shipping_tracking_id": "TRK",
            "shipping_address": {"country": "DE"},
            "shipping_cost": {"units": 25, "currency_code": "EUR"},
            "processed_at": "2026-06-16T11:00:00Z",
        }
        out = _enrich(order)
        assert out["order_id"] == "E-1"
        assert out["status"] == "processed"
        assert out["region"] == "eu"
        assert out["priority"] == "normal"
        assert out["shipping_cost_units"] == 25
        assert out["shipping_cost_currency"] == "EUR"
        assert out["items_count"] == 4

    def test_enrich_defaults(self):
        out = _enrich({})
        assert out["order_id"] == "unknown"
        assert out["region"] == "global"
        assert out["priority"] == "normal"
        assert out["shipping_cost_currency"] == "USD"
