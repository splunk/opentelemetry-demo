# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
OTLP log exporter wiring for the Planning_Init Lambda.

Attaches an OTel `LoggingHandler` to the Python logger so every log record
emitted via `shared.logging.get_logger()` is also exported over OTLP/gRPC
to the gateway collector. A filter stamps each record with the current
per-invocation `deployment.environment` (from the env ContextVar) so the
gateway's routing connector can fan logs out to the correct Splunk Cloud
HEC org alongside traces.

Activated only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise this
is a no-op and logs continue to flow only via the existing stdout handler.
"""

import logging
import os
from typing import Optional

from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource

from . import env as env_mod
from .tracing import get_current_trace_id, get_current_span_id

_INVALID_TRACE_ID = "0" * 32

_provider: Optional[LoggerProvider] = None
_handler: Optional[LoggingHandler] = None


class _EnvAttributeFilter(logging.Filter):
    """
    Inject the fields Splunk O11y Related Content uses to link logs to
    traces, metrics and infrastructure onto every log record. The OTel
    `LoggingHandler` lifts these record-dict keys into LogRecord
    attributes, which the gateway's `splunk_hec/<env>` exporter then
    writes as HEC event fields.

    Per the Splunk O11y docs (data-tools/related-content), the
    log-to-trace correlation fields are: `trace_id`, `span_id`,
    `service.name`, `host.name`. The `deployment.environment` attribute
    discriminates between envs in the same service.

    We additionally emit the `otelTraceID` / `otelSpanID` /
    `otelTraceSampled` / `otelServiceName` field names the
    splunk-otel-python distro produces (the K8s planning service uses
    those). Both forms are harmless duplicates and Splunk O11y
    recognises either.
    """

    def __init__(self, service_name: str):
        super().__init__()
        self._service_name = service_name
        # AWS Lambda runtime sets this; fall back to function-name pattern.
        self._host_name = os.getenv("AWS_LAMBDA_FUNCTION_NAME", service_name)

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__[env_mod.STAMPED_ATTR] = env_mod.get_current_tagged()
        trace_id = get_current_trace_id()
        span_id = get_current_span_id()
        # Splunk O11y Related Content primary fields (per docs).
        record.__dict__["trace_id"] = trace_id
        record.__dict__["span_id"] = span_id
        record.__dict__["service.name"] = self._service_name
        record.__dict__["host.name"] = self._host_name
        # splunk-otel-python convention (also recognised by Splunk O11y).
        record.__dict__["otelTraceID"] = trace_id
        record.__dict__["otelSpanID"] = span_id
        record.__dict__["otelTraceSampled"] = trace_id != _INVALID_TRACE_ID
        record.__dict__["otelServiceName"] = self._service_name
        return True


def init_log_exporter(service_name: str) -> Optional[LoggingHandler]:
    """
    Initialize the OTLP log exporter once per cold start.

    Returns the LoggingHandler to attach to a Python logger, or None when
    OTEL_EXPORTER_OTLP_ENDPOINT is not set.
    """
    global _provider, _handler

    if _handler is not None:
        return _handler

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return None

    # OTEL_SERVICE_NAME env var is the spec-governed source of service identity;
    # the caller-provided arg is a fallback only. Prevents accidental hijack
    # when a caller passes __name__ (e.g. a shared utility module).
    service_name = os.getenv("OTEL_SERVICE_NAME", service_name)

    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "opentelemetry-demo",
        "cloud.provider": "aws",
        "cloud.platform": "aws_lambda",
    })

    _provider = LoggerProvider(resource=resource)
    _provider.add_log_record_processor(
        BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, insecure=True))
    )
    set_logger_provider(_provider)

    _handler = LoggingHandler(level=logging.NOTSET, logger_provider=_provider)
    _handler.addFilter(_EnvAttributeFilter(service_name))
    return _handler


def force_flush(timeout_millis: int = 5000) -> None:
    """Force flush pending log records. Call before Lambda freezes."""
    if _provider is not None:
        _provider.force_flush(timeout_millis)
