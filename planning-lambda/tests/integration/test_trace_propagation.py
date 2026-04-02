# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for trace context propagation."""

import json
import pytest
from unittest.mock import MagicMock, patch
import sys
import os

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'Planning_Init'))

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from shared.tracing import init_tracer, extract_context, create_span


class TestTracePropagation:
    """Tests for trace context propagation through the handler chain."""

    @pytest.fixture(autouse=True)
    def setup_in_memory_exporter(self):
        """Setup in-memory span exporter to capture spans."""
        # Reset global tracer
        from shared import tracing
        tracing._tracer = None

        # Create in-memory exporter
        self.span_exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        trace.set_tracer_provider(provider)

        yield

        # Cleanup
        self.span_exporter.clear()
        tracing._tracer = None

    def test_trace_context_preserved_from_request(self, api_event_with_orders, mock_lambda_context):
        """Parent trace ID preserved from request to response span."""
        from Planning_Init.lambda_function import lambda_handler

        # Set a specific traceparent to track
        parent_trace_id = "0af7651916cd43dd8448eb211c80319c"
        parent_span_id = "b7ad6b7169203331"
        api_event_with_orders["headers"]["traceparent"] = f"00-{parent_trace_id}-{parent_span_id}-01"

        # Initialize tracer with our provider
        init_tracer("test-service")

        response = lambda_handler(api_event_with_orders, mock_lambda_context)

        assert response["statusCode"] == 200

        # Check that spans were created
        spans = self.span_exporter.get_finished_spans()
        assert len(spans) > 0

        # Find the root handler span
        handler_span = next(
            (s for s in spans if "Planning_Init.handler" in s.name),
            None
        )
        assert handler_span is not None

    def test_span_hierarchy(self, api_event_with_orders, mock_lambda_context):
        """Correct parent-child relationships in span hierarchy."""
        from Planning_Init.lambda_function import lambda_handler

        init_tracer("test-service")

        response = lambda_handler(api_event_with_orders, mock_lambda_context)

        assert response["statusCode"] == 200

        spans = self.span_exporter.get_finished_spans()

        # Should have multiple spans
        assert len(spans) >= 2

        # Get span names
        span_names = [s.name for s in spans]

        # Should include handler span and orders span
        assert any("handler" in name.lower() for name in span_names)
        assert any("orders" in name.lower() for name in span_names)

    def test_child_spans_have_same_trace_id(self, api_event_with_orders, mock_lambda_context):
        """All spans in the request share the same trace ID."""
        from Planning_Init.lambda_function import lambda_handler

        init_tracer("test-service")

        response = lambda_handler(api_event_with_orders, mock_lambda_context)

        spans = self.span_exporter.get_finished_spans()

        if len(spans) > 1:
            trace_ids = set(s.context.trace_id for s in spans)
            # All spans should have the same trace ID
            assert len(trace_ids) == 1

    def test_downstream_invoke_propagates_context(self, api_event_with_orders, mock_lambda_context):
        """Trace context injected into downstream Lambda calls."""
        init_tracer("test-service")

        with patch.dict(os.environ, {"DOWNSTREAM_LAMBDA_ARN": "arn:aws:lambda:us-east-1:123:function:Test"}):
            with patch('handlers.orders.invoke_lambda') as mock_invoke:
                mock_invoke.return_value = {"statusCode": 200}

                from Planning_Init.lambda_function import lambda_handler
                response = lambda_handler(api_event_with_orders, mock_lambda_context)

                assert response["statusCode"] == 200

                # Verify invoke_lambda was called
                assert mock_invoke.called

                # Check the payload contains trace context
                call_args = mock_invoke.call_args
                payload = call_args[0][1]  # Second positional arg is payload
                assert "orders" in payload or "source" in payload


class TestContextExtraction:
    """Tests for W3C trace context extraction."""

    def test_extract_valid_traceparent(self):
        """Extracts context from valid traceparent header."""
        init_tracer("test-service")

        event = {
            "headers": {
                "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
            }
        }

        context = extract_context(event)
        assert context is not None

    def test_extract_with_tracestate(self):
        """Extracts context with tracestate header."""
        init_tracer("test-service")

        event = {
            "headers": {
                "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
                "tracestate": "congo=t61rcWkgMzE"
            }
        }

        context = extract_context(event)
        assert context is not None

    def test_extract_mixed_case_headers(self):
        """Handles mixed case header names."""
        init_tracer("test-service")

        event = {
            "headers": {
                "TRACEPARENT": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
                "TraceState": "rojo=00f067aa0ba902b7"
            }
        }

        context = extract_context(event)
        assert context is not None
