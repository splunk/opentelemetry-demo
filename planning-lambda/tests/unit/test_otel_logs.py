# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for shared/otel_logs.py and the env ContextVar helpers."""

import logging
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared import env as env_mod
from shared import otel_logs


@pytest.fixture(autouse=True)
def reset_otel_logs_state():
    """Reset module-level globals between tests."""
    otel_logs._provider = None
    otel_logs._handler = None
    yield
    otel_logs._provider = None
    otel_logs._handler = None


class TestEnvContextVar:
    def test_default_is_unknown(self):
        env_mod._current_env.set(env_mod.UNKNOWN_ENV)
        assert env_mod.get_current() == env_mod.UNKNOWN_ENV
        assert env_mod.get_current_tagged() == "unknown-lambda"

    def test_set_and_get(self):
        env_mod.set_current("dev-astronomy-shop-demo")
        assert env_mod.get_current() == "dev-astronomy-shop-demo"
        assert env_mod.get_current_tagged() == "dev-astronomy-shop-demo-lambda"

    def test_set_empty_falls_back_to_unknown(self):
        env_mod.set_current("")
        assert env_mod.get_current() == env_mod.UNKNOWN_ENV

    def test_set_none_falls_back_to_unknown(self):
        env_mod.set_current(None)
        assert env_mod.get_current() == env_mod.UNKNOWN_ENV


class TestInitLogExporter:
    def test_no_endpoint_returns_none(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
            result = otel_logs.init_log_exporter("test-service")
            assert result is None
            assert otel_logs._handler is None
            assert otel_logs._provider is None

    def test_with_endpoint_returns_handler(self):
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}):
            handler = otel_logs.init_log_exporter("test-service")
            assert handler is not None
            assert isinstance(handler, logging.Handler)
            assert otel_logs._handler is handler
            assert otel_logs._provider is not None

    def test_idempotent(self):
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}):
            h1 = otel_logs.init_log_exporter("test-service")
            h2 = otel_logs.init_log_exporter("test-service")
            assert h1 is h2


class TestEnvAttributeFilter:
    def test_filter_injects_tagged_env(self):
        env_mod.set_current("astronomy-shop-eu")
        flt = otel_logs._EnvAttributeFilter("Planning_Init_Lambda")
        rec = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        assert flt.filter(rec) is True
        assert rec.__dict__[env_mod.STAMPED_ATTR] == "astronomy-shop-eu-lambda"

    def test_filter_with_unknown_env(self):
        env_mod.set_current(env_mod.UNKNOWN_ENV)
        flt = otel_logs._EnvAttributeFilter("Planning_Init_Lambda")
        rec = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=0,
            msg="hello", args=(), exc_info=None,
        )
        flt.filter(rec)
        assert rec.__dict__[env_mod.STAMPED_ATTR] == "unknown-lambda"

    def test_filter_injects_splunk_otel_fields(self):
        env_mod.set_current("dev-astronomy-shop-demo")
        flt = otel_logs._EnvAttributeFilter("Planning_Process_Lambda")
        rec = logging.LogRecord(
            name="test", level=logging.INFO, pathname=__file__, lineno=0,
            msg="hi", args=(), exc_info=None,
        )
        flt.filter(rec)
        # Splunk-O11y-recognized log correlation fields must be present.
        assert "otelTraceID" in rec.__dict__
        assert "otelSpanID" in rec.__dict__
        assert "otelTraceSampled" in rec.__dict__
        assert rec.__dict__["otelServiceName"] == "Planning_Process_Lambda"
        # No active span in this test context -> invalid trace_id, unsampled
        assert rec.__dict__["otelTraceID"] == "0" * 32
        assert rec.__dict__["otelTraceSampled"] is False


class TestForceFlush:
    def test_no_provider_no_op(self):
        otel_logs._provider = None
        otel_logs.force_flush()  # should not raise

    def test_with_provider_calls_flush(self):
        with patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"}):
            otel_logs.init_log_exporter("test-service")
            with patch.object(otel_logs._provider, "force_flush") as mock_flush:
                otel_logs.force_flush(timeout_millis=1000)
                mock_flush.assert_called_once_with(1000)
