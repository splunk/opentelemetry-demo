"""Environment-driven configuration for the Team Portal datagen app."""

from __future__ import annotations

import os
import sys
from enum import Enum
from typing import Optional, Set


class VaRuntimeMode(str, Enum):
    OFF = "off"
    HTTP = "http"
    SCHEDULER = "scheduler"


DEFAULT_VA_STAGGER_INTERVAL_SECONDS = 1800


def _truthy(value: Optional[str], default: bool = False) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    return normalized in {"1", "true", "yes", "on"}


def parse_attack_scenario_subset() -> Optional[Set[str]]:
    raw = os.getenv("ATTACK_ENABLED_SCENARIOS", "").strip()
    if not raw:
        return None
    subset = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return subset or None


def attack_scenario_enabled(scenario_key: str, subset: Optional[Set[str]]) -> bool:
    if subset is None:
        return True
    return scenario_key.lower() in subset


def parse_va_runtime_mode() -> VaRuntimeMode:
    raw = os.getenv("VA_RUNTIME_MODE", "off").strip().lower()
    try:
        return VaRuntimeMode(raw)
    except ValueError:
        return VaRuntimeMode.OFF


def parse_va_stagger_interval_seconds() -> int:
    raw = os.getenv("VA_STAGGER_INTERVAL_SECONDS", "").strip()
    if not raw:
        return DEFAULT_VA_STAGGER_INTERVAL_SECONDS
    try:
        value = int(raw)
        return value if value >= 1 else DEFAULT_VA_STAGGER_INTERVAL_SECONDS
    except ValueError:
        return DEFAULT_VA_STAGGER_INTERVAL_SECONDS


def parse_workspace_sync_enabled() -> bool:
    return _truthy(os.getenv("WORKSPACE_SYNC_ENABLED"), default=False)


def server_port() -> int:
    raw = os.getenv("SERVER_PORT", "8080").strip()
    try:
        return int(raw)
    except ValueError:
        return 8080


def resolve_service_name() -> str:
    return os.getenv("SERVICE_NAME", "").strip() or os.getenv("OTEL_SERVICE_NAME", "").strip()


def resolve_deploy_env() -> str:
    explicit = os.getenv("DEPLOY_ENV", "").strip()
    if explicit:
        return explicit
    attrs = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    for part in attrs.split(","):
        part = part.strip()
        if part.startswith("deployment.environment.name="):
            return part.split("=", 1)[1].strip()
    return ""


def validate_required_splunk_env() -> None:
    """Fail fast when OTel resource identity env vars are missing."""
    missing: list[str] = []
    if not resolve_service_name():
        missing.append("SERVICE_NAME (or OTEL_SERVICE_NAME)")
    if not resolve_deploy_env():
        missing.append("DEPLOY_ENV (or deployment.environment.name in OTEL_RESOURCE_ATTRIBUTES)")
    if missing:
        print(
            "ERROR: missing required environment variables: " + ", ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(1)


def splunk_env_summary() -> dict:
    return {
        "realm": os.getenv("REALM", ""),
        "serviceName": resolve_service_name(),
        "deployEnv": resolve_deploy_env(),
    }
