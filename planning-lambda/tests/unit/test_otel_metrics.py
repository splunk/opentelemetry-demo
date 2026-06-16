# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for shared/otel_metrics.py."""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared import env as env_mod
from shared import otel_metrics


@pytest.fixture(autouse=True)
def reset_state():
    """Reset module-level globals between tests."""
    otel_metrics._provider = None
    otel_metrics._meter = None
    yield
    otel_metrics._provider = None
    otel_metrics._meter = None


class TestInitMeter:
    def test_no_endpoint_returns_noop_meter(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            meter = otel_metrics.init_meter("test-service")
            assert meter is not None
            assert otel_metrics._provider is None

    def test_with_endpoint_initialises_provider(self):
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}):
            meter = otel_metrics.init_meter("test-service")
            assert meter is not None
            assert otel_metrics._provider is not None

    def test_idempotent(self):
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}):
            m1 = otel_metrics.init_meter("test-service")
            m2 = otel_metrics.init_meter("test-service")
            assert m1 is m2


class TestEnvAttrs:
    def test_includes_current_env(self):
        env_mod.set_current("astronomy-shop-eu")
        attrs = otel_metrics.env_attrs()
        assert attrs[env_mod.STAMPED_ATTR] == "astronomy-shop-eu-lambda"

    def test_merges_extra(self):
        env_mod.set_current("dev-astronomy-shop-demo")
        attrs = otel_metrics.env_attrs({"order.priority": "high"})
        assert attrs[env_mod.STAMPED_ATTR] == "dev-astronomy-shop-demo-lambda"
        assert attrs["order.priority"] == "high"

    def test_extra_wins_on_collision(self):
        env_mod.set_current("dev-astronomy-shop-demo")
        attrs = otel_metrics.env_attrs({env_mod.STAMPED_ATTR: "override-value"})
        assert attrs[env_mod.STAMPED_ATTR] == "override-value"


class TestForceFlush:
    def test_no_provider_no_op(self):
        otel_metrics._provider = None
        otel_metrics.force_flush()  # should not raise

    def test_with_provider_calls_flush(self):
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}):
            otel_metrics.init_meter("test-service")
            with patch.object(otel_metrics._provider, "force_flush") as mock_flush:
                otel_metrics.force_flush(timeout_millis=1000)
                mock_flush.assert_called_once_with(1000)
