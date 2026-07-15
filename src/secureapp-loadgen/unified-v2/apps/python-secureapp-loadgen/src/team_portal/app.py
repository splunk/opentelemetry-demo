"""
Team Portal — Flask app for SecureApp Python e2e datagen.

Each attack scenario maps to an intentionally pinned vulnerable library/CVE.
Attack traffic is driven by in-cluster datagen (k8s Job/Deployment), not in-process schedulers.
"""

from __future__ import annotations

import logging
from typing import Optional, Set

from flask import Flask, jsonify

from team_portal import attacks, config, va, vulnerabilities

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

config.validate_required_splunk_env()

app = Flask(__name__)

ATTACK_SUBSET: Optional[Set[str]] = config.parse_attack_scenario_subset()
VA_MODE = config.parse_va_runtime_mode()
WORKSPACE_SYNC_ENABLED = config.parse_workspace_sync_enabled()


def _scenario_response(scenario: str):
    handler = attacks.ATTACK_HANDLERS.get(scenario)
    if handler is None:
        return jsonify({"error": "unknown scenario"}), 404
    return jsonify(handler())


def _register_attack_route(path: str, scenario: str) -> None:
    if not config.attack_scenario_enabled(scenario, ATTACK_SUBSET):
        return

    endpoint = "attack_" + path.strip("/").replace("/", "_").replace("-", "_")

    def _handler(scenario_key=scenario):  # noqa: ANN001
        return _scenario_response(scenario_key)

    app.add_url_rule(path, endpoint=endpoint, view_func=_handler, methods=["GET"])


@app.get("/health")
def health():
    return "OK", 200


@app.get("/internal/vulnerabilities")
def list_vulnerabilities():
    return jsonify(
        {
            "splunk": config.splunk_env_summary(),
            "targets": vulnerabilities.all_targets_summary(),
        }
    )


@app.get("/internal/va/next")
def va_next():
    if VA_MODE != config.VaRuntimeMode.HTTP:
        return jsonify(
            {
                "error": "VA hints disabled or wrong mode",
                "hint": "Set VA_RUNTIME_MODE=http",
                "mode": VA_MODE.value.upper(),
            }
        ), 503
    result = va.advance_va_hint()
    return jsonify(result.to_json_dict())


@app.get("/api/v1/workspace/sync")
def workspace_sync():
    if not WORKSPACE_SYNC_ENABLED:
        return jsonify({"error": "workspace sync disabled"}), 404
    return jsonify(attacks.trigger_workspace_sync(ATTACK_SUBSET))


def _register_routes() -> None:
    for path, scenario in attacks.PATH_TO_SCENARIO.items():
        _register_attack_route(path, scenario)


_register_routes()
attacks.ensure_db()
