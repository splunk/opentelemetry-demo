"""Minimal OFREP client for flagd. Same HTTP path as astronomy-loadgen."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("k8s-scenario-controller")


@dataclass(frozen=True)
class FlagRead:
    """ok=False means flagd could not be reached; value must not be applied."""

    ok: bool
    value: Any = None


class FlagClient:
    def __init__(self, base_url: str | None = None, timeout: float = 2.0):
        raw = base_url or os.getenv("FLAGD_OFREP_URL", "http://flagd:8016")
        self.base_url = raw.rstrip("/")
        self.timeout = timeout
        self.enabled = os.getenv("FLAGD_OFREP_ENABLED", "true").lower() != "false"

    def read_module(self, module) -> FlagRead:
        """Typed flag value for a scenario module. Skip reconcile when not ok."""
        if not self.enabled:
            return FlagRead(True, module.default)
        fetched = self._fetch(module.flag_key)
        if not fetched.ok:
            return fetched
        return FlagRead(True, self._coerce(module, fetched.value))

    def get_boolean(self, key: str, default: bool = False) -> bool:
        value = self._evaluate(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "on", "1")
        return bool(value)

    def get_string(self, key: str, default: str = "") -> str:
        value = self._evaluate(key, default)
        return default if value is None else str(value)

    def get_number(self, key: str, default: float | int = 0):
        value = self._evaluate(key, default)
        if isinstance(value, (int, float)):
            return value
        try:
            return type(default)(value)
        except (TypeError, ValueError):
            return default

    def _coerce(self, module, value: Any) -> Any:
        if module.flag_type == "string":
            return module.default if value is None else str(value)
        if module.flag_type == "number":
            if isinstance(value, (int, float)):
                return value
            try:
                return type(module.default)(value)
            except (TypeError, ValueError):
                return module.default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "on", "1")
        return bool(value)

    def _fetch(self, key: str) -> FlagRead:
        url = f"{self.base_url}/ofrep/v1/evaluate/flags/{key}"
        payload = json.dumps({"context": {"targetingKey": "k8s-scenario-controller"}}).encode()
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"content-type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            log.warning("OFREP %s failed (%s)", key, exc)
            return FlagRead(False)
        if "value" not in body:
            log.warning("OFREP %s returned no value", key)
            return FlagRead(False)
        return FlagRead(True, body["value"])

    def _evaluate(self, key: str, default):
        if not self.enabled:
            return default
        fetched = self._fetch(key)
        if not fetched.ok:
            log.warning("OFREP %s failed; using default %r", key, default)
            return default
        return fetched.value
