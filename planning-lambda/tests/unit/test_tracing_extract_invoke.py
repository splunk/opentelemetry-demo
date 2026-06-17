# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for shared.tracing.extract_context_from_invoke."""

import os
import sys
from unittest.mock import MagicMock

import pytest
from opentelemetry import trace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.tracing import init_tracer, extract_context_from_invoke

VALID_TRACEPARENT = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
EXPECTED_TRACE_ID = 0x0af7651916cd43dd8448eb211c80319c


@pytest.fixture(autouse=True)
def setup_tracer():
    init_tracer("test")


def _span_ctx_from(ctx):
    span = trace.get_current_span(ctx)
    return span.get_span_context() if span is not None else None


class TestExtractFromInvokePayload:
    def test_traceparent_in_payload_field(self):
        event = {"_trace_context": {"traceparent": VALID_TRACEPARENT}}
        sc = _span_ctx_from(extract_context_from_invoke(event))
        assert sc is not None
        assert sc.is_valid
        assert sc.trace_id == EXPECTED_TRACE_ID

    def test_traceparent_case_insensitive(self):
        event = {"_trace_context": {"TraceParent": VALID_TRACEPARENT}}
        sc = _span_ctx_from(extract_context_from_invoke(event))
        assert sc.is_valid
        assert sc.trace_id == EXPECTED_TRACE_ID


class TestExtractFromClientContext:
    def test_traceparent_in_client_context_custom(self):
        ctx = MagicMock()
        ctx.client_context.custom = {"traceparent": VALID_TRACEPARENT, "env": "dev-astronomy"}
        sc = _span_ctx_from(extract_context_from_invoke({}, ctx))
        assert sc.is_valid
        assert sc.trace_id == EXPECTED_TRACE_ID

    def test_payload_field_wins_over_client_context(self):
        # Different traceparent in each location; payload field should win.
        other_traceparent = "00-12345678901234567890123456789012-1234567890123456-01"
        event = {"_trace_context": {"traceparent": VALID_TRACEPARENT}}
        ctx = MagicMock()
        ctx.client_context.custom = {"traceparent": other_traceparent}
        sc = _span_ctx_from(extract_context_from_invoke(event, ctx))
        assert sc.trace_id == EXPECTED_TRACE_ID


class TestExtractFallback:
    def test_missing_returns_invalid_span_context(self):
        sc = _span_ctx_from(extract_context_from_invoke({}, None))
        # No trace context means the current span is non-recording with an
        # invalid span context.
        assert sc is not None
        assert not sc.is_valid

    def test_non_dict_event_safe(self):
        sc = _span_ctx_from(extract_context_from_invoke(None, None))
        assert sc is not None
        assert not sc.is_valid

    def test_empty_trace_context_field(self):
        sc = _span_ctx_from(extract_context_from_invoke({"_trace_context": {}}, None))
        assert sc is not None
        assert not sc.is_valid
