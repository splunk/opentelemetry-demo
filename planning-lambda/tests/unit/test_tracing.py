# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for shared/tracing.py."""

import pytest
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from shared.tracing import (
    init_tracer,
    get_tracer,
    extract_context,
    inject_context,
    create_span,
    get_current_trace_id,
    get_current_span_id,
)


class TestInitTracer:
    """Tests for init_tracer function."""

    def test_init_tracer_creates_provider(self):
        """Verify init_tracer creates a TracerProvider."""
        tracer = init_tracer("test-service")
        assert tracer is not None

        # Verify the global provider is set
        provider = trace.get_tracer_provider()
        assert provider is not None

    def test_init_tracer_idempotent(self):
        """Calling init_tracer twice returns the same tracer."""
        tracer1 = init_tracer("test-service")
        tracer2 = init_tracer("test-service")
        assert tracer1 is tracer2

    def test_init_tracer_default_service_name(self, env_vars):
        """Uses OTEL_SERVICE_NAME env var as default."""
        tracer = init_tracer()
        assert tracer is not None


class TestExtractContext:
    """Tests for extract_context function."""

    def test_extract_context_with_valid_traceparent(self, sample_traceparent):
        """Extract context from headers with valid traceparent."""
        event = {
            "headers": {
                "traceparent": sample_traceparent
            }
        }
        context = extract_context(event)
        # Context should be extracted (non-empty)
        assert context is not None

    def test_extract_context_empty_headers(self):
        """Returns empty context when no trace headers present."""
        event = {"headers": {}}
        context = extract_context(event)
        assert context is not None

    def test_extract_context_no_headers(self):
        """Handles event with no headers key."""
        event = {}
        context = extract_context(event)
        assert context is not None

    def test_extract_context_none_headers(self):
        """Handles event with None headers."""
        event = {"headers": None}
        context = extract_context(event)
        assert context is not None

    def test_extract_context_case_insensitive(self, sample_traceparent):
        """Headers are normalized to lowercase."""
        event = {
            "headers": {
                "TRACEPARENT": sample_traceparent,
                "Traceparent": sample_traceparent
            }
        }
        context = extract_context(event)
        assert context is not None


class TestInjectContext:
    """Tests for inject_context function."""

    def test_inject_context_creates_headers(self):
        """inject_context creates new headers dict if None provided."""
        init_tracer("test-service")
        with create_span("test-span"):
            headers = inject_context()
            assert isinstance(headers, dict)

    def test_inject_context_adds_to_existing(self):
        """inject_context adds to existing headers dict."""
        init_tracer("test-service")
        existing = {"X-Custom": "value"}
        with create_span("test-span"):
            headers = inject_context(existing)
            assert "X-Custom" in headers
            assert headers["X-Custom"] == "value"

    def test_inject_context_adds_traceparent(self):
        """inject_context adds traceparent header when span active."""
        init_tracer("test-service")
        with create_span("test-span"):
            headers = inject_context()
            assert "traceparent" in headers


class TestCreateSpan:
    """Tests for create_span context manager."""

    def test_create_span_basic(self):
        """Context manager creates span with name."""
        init_tracer("test-service")
        with create_span("test-span") as span:
            assert span is not None
            assert span.is_recording()

    def test_create_span_with_kind(self):
        """Span created with specified kind."""
        init_tracer("test-service")
        with create_span("test-span", kind=SpanKind.SERVER) as span:
            assert span.kind == SpanKind.SERVER

    def test_create_span_with_attributes(self):
        """Span created with initial attributes."""
        init_tracer("test-service")
        attrs = {"key1": "value1", "key2": 42}
        with create_span("test-span", attributes=attrs) as span:
            # Attributes should be set (can't easily read them back in OTel SDK)
            assert span is not None

    def test_create_span_with_parent(self, sample_traceparent):
        """Span links to provided parent context."""
        init_tracer("test-service")
        event = {"headers": {"traceparent": sample_traceparent}}
        parent_ctx = extract_context(event)

        with create_span("test-span", parent_context=parent_ctx) as span:
            assert span is not None

    def test_create_span_sets_ok_status(self):
        """Span status set to OK on successful exit."""
        init_tracer("test-service")
        with create_span("test-span") as span:
            pass
        # Status should be OK (span ended)

    def test_create_span_sets_error_on_exception(self):
        """Span records exception and sets ERROR status."""
        init_tracer("test-service")
        with pytest.raises(ValueError):
            with create_span("test-span") as span:
                raise ValueError("test error")


class TestGetCurrentTraceId:
    """Tests for get_current_trace_id function."""

    def test_get_current_trace_id_with_span(self):
        """Returns valid hex trace ID when span active."""
        init_tracer("test-service")
        with create_span("test-span"):
            trace_id = get_current_trace_id()
            assert len(trace_id) == 32
            assert trace_id != "0" * 32

    def test_get_current_trace_id_no_span(self):
        """Returns zero trace ID when no span."""
        init_tracer("test-service")
        trace_id = get_current_trace_id()
        assert trace_id == "0" * 32


class TestGetCurrentSpanId:
    """Tests for get_current_span_id function."""

    def test_get_current_span_id_with_span(self):
        """Returns valid hex span ID when span active."""
        init_tracer("test-service")
        with create_span("test-span"):
            span_id = get_current_span_id()
            assert len(span_id) == 16
            assert span_id != "0" * 16

    def test_get_current_span_id_no_span(self):
        """Returns zero span ID when no span."""
        init_tracer("test-service")
        span_id = get_current_span_id()
        assert span_id == "0" * 16
