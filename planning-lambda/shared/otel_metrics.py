# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
OTLP metric exporter wiring for the planning Lambdas.

Initialises a `MeterProvider` with an `OTLPMetricExporter` (gRPC) and a
`PeriodicExportingMetricReader`. Returns a `Meter` for the caller to
create instruments (counters, histograms, etc.).

Per-invocation `deployment.environment` is added to every metric data
point via `env_attrs()`, which the caller merges into the attribute dict
passed to `counter.add(...)` / `histogram.record(...)`. The gateway
collector's `transform/promote_env_metrics` processor then promotes
that attribute to a resource attribute for the routing connector.

Activated only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set; otherwise a
no-op `NoOpMeter` is returned and `force_flush()` does nothing.
"""

import os
from typing import Dict, Optional

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from . import env as env_mod

_provider: Optional[MeterProvider] = None
_meter: Optional[metrics.Meter] = None


def init_meter(service_name: str) -> metrics.Meter:
    """
    Initialise the OTLP meter once per cold start.

    Returns a `Meter` bound to the configured provider. Safe to call
    multiple times; subsequent calls return the cached meter.
    """
    global _provider, _meter

    if _meter is not None:
        return _meter

    service_name = os.getenv("OTEL_SERVICE_NAME", service_name)

    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        # Fall back to the no-op default global meter.
        _meter = metrics.get_meter(service_name)
        return _meter

    resource = Resource.create({
        "service.name": service_name,
        "service.namespace": "opentelemetry-demo",
        "cloud.provider": "aws",
        "cloud.platform": "aws_lambda",
    })

    reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=endpoint, insecure=True),
        export_interval_millis=10_000,
    )
    _provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(_provider)

    _meter = metrics.get_meter(service_name)
    return _meter


def force_flush(timeout_millis: int = 5000) -> None:
    """Force flush pending metric data. Call before Lambda freezes."""
    if _provider is not None:
        _provider.force_flush(timeout_millis)


def env_attrs(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Build an attribute dict carrying the per-invocation env, suitable
    for the `attributes=` kwarg on instrument add/record calls.

    `extra` is merged on top; extra keys win on collision.
    """
    attrs: Dict[str, str] = {env_mod.STAMPED_ATTR: env_mod.get_current_tagged()}
    if extra:
        attrs.update(extra)
    return attrs
