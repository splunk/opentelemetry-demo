# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

from fastmcp.server.middleware import Middleware
from opentelemetry import context as otel_context
from opentelemetry import propagate


class TraceContextMiddleware(Middleware):
    """Restore per-message context across the long-lived MCP transport."""

    async def on_message(self, context, call_next):
        request = (
            context.fastmcp_context.request_context
            if context.fastmcp_context is not None
            else None
        )
        meta = dict(request.meta) if request is not None and request.meta else {}
        carrier = {
            key: meta[key]
            for key in ("traceparent", "tracestate", "baggage")
            if isinstance(meta.get(key), str)
        }
        token = otel_context.attach(propagate.extract(carrier))
        try:
            return await call_next(context)
        finally:
            otel_context.detach(token)
