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

_provider: Optional[LoggerProvider] = None
_handler: Optional[LoggingHandler] = None


class _EnvAttributeFilter(logging.Filter):
    """Inject the per-invocation env onto every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__[env_mod.STAMPED_ATTR] = env_mod.get_current_tagged()
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
    _handler.addFilter(_EnvAttributeFilter())
    return _handler


def force_flush(timeout_millis: int = 5000) -> None:
    """Force flush pending log records. Call before Lambda freezes."""
    if _provider is not None:
        _provider.force_flush(timeout_millis)
