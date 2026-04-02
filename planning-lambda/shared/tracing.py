# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""OpenTelemetry tracing utilities for AWS Lambda."""

import os
from contextlib import contextmanager
from typing import Optional, Dict, Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.propagate import set_global_textmap

# Try to import OTLP exporter (optional dependency)
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    OTLP_AVAILABLE = True
except ImportError:
    OTLP_AVAILABLE = False

# Global tracer instance
_tracer: Optional[trace.Tracer] = None
_provider: Optional[TracerProvider] = None
_propagator = TraceContextTextMapPropagator()


def init_tracer(service_name: str = None) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracer for Lambda.

    Args:
        service_name: Service name for tracing. Defaults to OTEL_SERVICE_NAME env var.

    Returns:
        Configured tracer instance.
    """
    global _tracer, _provider

    if _tracer is not None:
        return _tracer

    service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "planning-lambda")

    # Create resource with service info
    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "opentelemetry-demo",
        "cloud.provider": "aws",
        "cloud.platform": "aws_lambda",
    })

    # Create tracer provider
    provider = TracerProvider(resource=resource)

    # Add OTLP exporter if endpoint is configured
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint and OTLP_AVAILABLE:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Add console exporter for debugging (can be disabled)
    if os.getenv("OTEL_TRACES_CONSOLE", "false").lower() == "true":
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Set as global provider
    trace.set_tracer_provider(provider)
    set_global_textmap(_propagator)

    _provider = provider
    _tracer = trace.get_tracer(service_name)
    return _tracer


def force_flush(timeout_millis: int = 5000):
    """Force flush all pending spans. Must be called before Lambda freezes."""
    if _provider is not None:
        _provider.force_flush(timeout_millis)


def get_tracer() -> trace.Tracer:
    """Get the initialized tracer instance."""
    global _tracer
    if _tracer is None:
        return init_tracer()
    return _tracer


def extract_context(event: Dict[str, Any]) -> trace.Context:
    """
    Extract trace context from API Gateway event headers.

    Args:
        event: API Gateway Lambda event.

    Returns:
        Extracted trace context.
    """
    headers = event.get("headers", {}) or {}
    # Normalize header keys to lowercase
    normalized_headers = {k.lower(): v for k, v in headers.items()}
    return _propagator.extract(carrier=normalized_headers)


def inject_context(headers: Dict[str, str] = None) -> Dict[str, str]:
    """
    Inject current trace context into headers for outgoing requests.

    Args:
        headers: Existing headers dict to inject into. Creates new dict if None.

    Returns:
        Headers dict with trace context injected.
    """
    if headers is None:
        headers = {}
    _propagator.inject(headers)
    return headers


@contextmanager
def create_span(
    name: str,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Dict[str, Any] = None,
    parent_context: trace.Context = None
):
    """
    Create a new span with the given name.

    Args:
        name: Span name.
        kind: Span kind (INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER).
        attributes: Initial span attributes.
        parent_context: Parent context for the span.

    Yields:
        The created span.
    """
    tracer = get_tracer()

    with tracer.start_as_current_span(
        name,
        context=parent_context,
        kind=kind,
        attributes=attributes
    ) as span:
        try:
            yield span
            if span.status.status_code == StatusCode.UNSET:
                span.set_status(Status(StatusCode.OK))
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            raise


def get_current_trace_id() -> str:
    """Get the current trace ID as a hex string."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return trace.format_trace_id(span.get_span_context().trace_id)
    return "00000000000000000000000000000000"


def get_current_span_id() -> str:
    """Get the current span ID as a hex string."""
    span = trace.get_current_span()
    if span and span.get_span_context().is_valid:
        return trace.format_span_id(span.get_span_context().span_id)
    return "0000000000000000"
