# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for shared/env.py."""

import base64
import json
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from shared.env import (
    BARE_ENV_KEY,
    HTTP_HEADER,
    LAMBDA_SUFFIX,
    STAMPED_ATTR,
    UNKNOWN_ENV,
    extract_env,
    for_http,
    for_invoke,
    for_sns,
    stamp,
    tag,
)


class TestTag:
    def test_appends_suffix(self):
        assert tag("dev-astronomy") == "dev-astronomy-lambda"

    def test_empty_falls_back_to_unknown(self):
        assert tag("") == "unknown-lambda"

    def test_none_falls_back_to_unknown(self):
        assert tag(None) == "unknown-lambda"


class TestStamp:
    def test_sets_attribute(self):
        span = MagicMock()
        result = stamp(span, "astronomy-shop-eu")
        span.set_attribute.assert_called_once_with(STAMPED_ATTR, "astronomy-shop-eu-lambda")
        assert result == "astronomy-shop-eu-lambda"

    def test_none_span_returns_tagged(self):
        result = stamp(None, "dev-astronomy")
        assert result == "dev-astronomy-lambda"

    def test_span_set_attribute_error_swallowed(self):
        span = MagicMock()
        span.set_attribute.side_effect = RuntimeError("non-recording")
        result = stamp(span, "dev-astronomy")
        assert result == "dev-astronomy-lambda"


class TestExtractEnv:
    def test_direct_body_field(self):
        assert extract_env({"env": "dev-astronomy"}) == "dev-astronomy"

    def test_top_level_event_field(self):
        assert extract_env({"env": "astronomy-shop-us"}, context=None) == "astronomy-shop-us"

    def test_client_context_custom(self):
        ctx = MagicMock()
        ctx.client_context.custom = {"env": "astronomy-shop-eu"}
        assert extract_env({}, context=ctx) == "astronomy-shop-eu"

    def test_sns_message_attributes(self):
        event = {
            "Records": [
                {"Sns": {"MessageAttributes": {"env": {"Type": "String", "Value": "dev-astronomy"}}}}
            ]
        }
        assert extract_env(event) == "dev-astronomy"

    def test_sns_string_value_variant(self):
        event = {
            "Records": [
                {"Sns": {"MessageAttributes": {"env": {"DataType": "String", "StringValue": "dev-astronomy"}}}}
            ]
        }
        assert extract_env(event) == "dev-astronomy"

    def test_http_header_lowercase(self):
        assert extract_env({"headers": {"x-demo-env": "astronomy-shop-us"}}) == "astronomy-shop-us"

    def test_http_header_case_insensitive(self):
        assert extract_env({"headers": {"X-DEMO-ENV": "astronomy-shop-eu"}}) == "astronomy-shop-eu"

    def test_default_unknown(self):
        assert extract_env({}) == UNKNOWN_ENV

    def test_non_dict_event_safe(self):
        assert extract_env(None) == UNKNOWN_ENV
        assert extract_env("string") == UNKNOWN_ENV

    def test_empty_string_falls_through(self):
        assert extract_env({"env": ""}) == UNKNOWN_ENV

    def test_precedence_body_over_header(self):
        event = {"env": "dev-astronomy", "headers": {"x-demo-env": "astronomy-shop-eu"}}
        assert extract_env(event) == "dev-astronomy"


class TestForInvoke:
    def test_base64_encodes_custom_env(self):
        encoded = for_invoke("dev-astronomy")
        decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
        assert decoded == {"custom": {"env": "dev-astronomy"}}

    def test_merges_extra(self):
        encoded = for_invoke("astronomy-shop-eu", extra={"traceparent": "00-abc-def-01"})
        decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
        assert decoded["custom"]["env"] == "astronomy-shop-eu"
        assert decoded["custom"]["traceparent"] == "00-abc-def-01"

    def test_extra_non_string_values_dropped(self):
        encoded = for_invoke("dev-astronomy", extra={"good": "ok", "bad": 123})
        decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
        assert "good" in decoded["custom"]
        assert "bad" not in decoded["custom"]

    def test_empty_env_uses_unknown(self):
        encoded = for_invoke("")
        decoded = json.loads(base64.b64decode(encoded).decode("utf-8"))
        assert decoded["custom"]["env"] == UNKNOWN_ENV


class TestForSns:
    def test_returns_message_attribute_entry(self):
        result = for_sns("dev-astronomy")
        assert result == {"env": {"DataType": "String", "StringValue": "dev-astronomy"}}


class TestForHttp:
    def test_returns_header_dict(self):
        assert for_http("astronomy-shop-us") == {"x-demo-env": "astronomy-shop-us"}

    def test_empty_uses_unknown(self):
        assert for_http("") == {"x-demo-env": UNKNOWN_ENV}


class TestConstants:
    def test_keys_match_contract(self):
        assert BARE_ENV_KEY == "env"
        assert HTTP_HEADER == "x-demo-env"
        assert STAMPED_ATTR == "deployment.environment"
        assert LAMBDA_SUFFIX == "-lambda"
        assert UNKNOWN_ENV == "unknown"
