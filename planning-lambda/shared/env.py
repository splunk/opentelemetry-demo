# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""
Per-invocation env extraction + stamping helpers for Lambda telemetry.

The K8s planning service passes the source cluster name (e.g. "dev-astronomy")
as a payload field. Every Lambda in the chain stamps
`deployment.environment = "<env>-lambda"` on its root span so the gateway
collector can route telemetry to the correct Splunk Observability + HEC org.

This module centralises the contract across all communication channels:
  - API Gateway HTTP request body field   ("env")
  - lambda.invoke ClientContext.custom    (key "env")
  - SNS MessageAttributes                 (key "env")
  - Direct HTTP/JSON header               ("x-demo-env")
"""

import base64
import json
from typing import Any, Dict, Optional

from opentelemetry.trace import Span

# Field/header/attribute names — single source of truth.
BARE_ENV_KEY = "env"
HTTP_HEADER = "x-demo-env"
STAMPED_ATTR = "deployment.environment"
LAMBDA_SUFFIX = "-lambda"
UNKNOWN_ENV = "unknown"


def extract_env(event: Dict[str, Any], context: Any = None) -> str:
    """
    Extract the bare env name from a Lambda invocation.

    Lookup order:
      1. Parsed request body field "env" (set by Planning_Init handler).
      2. Top-level event["env"] (Event-type invokes, manual payloads).
      3. lambda.invoke ClientContext.custom["env"].
      4. SNS record MessageAttributes "env".StringValue.
      5. HTTP header "x-demo-env" (case-insensitive).
      6. Default UNKNOWN_ENV.

    Args:
        event: The Lambda event dict OR a parsed request body dict.
        context: Lambda context object (optional; used for ClientContext).

    Returns:
        Bare env string (no "-lambda" suffix). Caller applies stamp().
    """
    if not isinstance(event, dict):
        return UNKNOWN_ENV

    # 1 + 2: direct field on body or event
    direct = event.get(BARE_ENV_KEY)
    if isinstance(direct, str) and direct:
        return direct

    # API Gateway nested body (still a string at this layer for HTTP API v2)
    body = event.get("body")
    if isinstance(body, dict):
        v = body.get(BARE_ENV_KEY)
        if isinstance(v, str) and v:
            return v

    # 3: ClientContext from lambda.invoke
    if context is not None:
        client_ctx = getattr(context, "client_context", None)
        if client_ctx is not None:
            custom = getattr(client_ctx, "custom", None)
            if isinstance(custom, dict):
                v = custom.get(BARE_ENV_KEY)
                if isinstance(v, str) and v:
                    return v

    # 4: SNS event shape
    records = event.get("Records")
    if isinstance(records, list) and records:
        first = records[0]
        if isinstance(first, dict):
            sns = first.get("Sns") or first.get("sns")
            if isinstance(sns, dict):
                attrs = sns.get("MessageAttributes") or {}
                entry = attrs.get(BARE_ENV_KEY) if isinstance(attrs, dict) else None
                if isinstance(entry, dict):
                    v = entry.get("Value") or entry.get("StringValue")
                    if isinstance(v, str) and v:
                        return v

    # 5: HTTP header (case-insensitive)
    headers = event.get("headers") or {}
    if isinstance(headers, dict):
        for k, v in headers.items():
            if isinstance(k, str) and k.lower() == HTTP_HEADER and isinstance(v, str) and v:
                return v

    return UNKNOWN_ENV


def stamp(span: Optional[Span], env_raw: str) -> str:
    """
    Stamp `deployment.environment = "<env>-lambda"` on the given span.

    Args:
        span: Active OTel span (may be None — function still returns tagged value).
        env_raw: Bare env name from extract_env().

    Returns:
        The tagged env string (env_raw + "-lambda").
    """
    env_tagged = tag(env_raw)
    if span is not None:
        try:
            span.set_attribute(STAMPED_ATTR, env_tagged)
        except Exception:
            # Span may be a no-op / NonRecordingSpan; ignore.
            pass
    return env_tagged


def tag(env_raw: str) -> str:
    """Return env_raw with the Lambda suffix applied. Pure function."""
    base = env_raw if (isinstance(env_raw, str) and env_raw) else UNKNOWN_ENV
    return f"{base}{LAMBDA_SUFFIX}"


def for_invoke(env_raw: str, extra: Optional[Dict[str, str]] = None) -> str:
    """
    Build a base64-encoded ClientContext JSON for boto3 lambda.invoke.

    AWS Lambda surfaces ClientContext.custom to the invoked function as a dict
    of strings. We pack env (bare) plus any extra custom values (e.g. trace
    headers) into the `custom` block.

    Args:
        env_raw: Bare env name. Will be stored under BARE_ENV_KEY.
        extra: Additional custom key/value pairs to merge (e.g. traceparent).

    Returns:
        Base64-encoded JSON string suitable for boto3 `ClientContext` parameter.
    """
    custom: Dict[str, str] = {BARE_ENV_KEY: env_raw or UNKNOWN_ENV}
    if extra:
        custom.update({k: v for k, v in extra.items() if isinstance(v, str)})
    payload = {"custom": custom}
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")


def for_sns(env_raw: str) -> Dict[str, Dict[str, str]]:
    """
    Build SNS MessageAttribute entry for env propagation.

    Merge into the `MessageAttributes` kwarg of boto3 SNS publish().
    """
    return {
        BARE_ENV_KEY: {
            "DataType": "String",
            "StringValue": env_raw or UNKNOWN_ENV,
        }
    }


def for_http(env_raw: str) -> Dict[str, str]:
    """Build HTTP header dict for env propagation on direct HTTP/JSON calls."""
    return {HTTP_HEADER: env_raw or UNKNOWN_ENV}
