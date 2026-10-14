"""S-IV — Kubernetes resource management (APM to K8s).

Sales demo 4: payment degrades every few hours; by the time you look
the pod is healthy again. Sawtooth memory → OOMKill → restart.
Root cause: container memory limit too low.

Does **not** patch live `payment` / `payment-vA` / `payment-vB`. Dummy
Deployment `paymentservice-oom` reports APM service.name=paymentservice
(OTLP traces to the node collector) so Overview → instances links to
the crashing pod. Distinct k8s labels so the real payment Service
never selects it.

Tight limit (default 100Mi) + gradual leak = OOMKilled. HTTP probes
start failing before the kill so Events show Unhealthy then OOMKilled.
"""

from __future__ import annotations

import logging
import os

from modules.base import ScenarioModule

log = logging.getLogger("k8s-scenario-controller")

DEPLOYMENT_NAME = "paymentservice-oom"
CONFIGMAP_NAME = "paymentservice-oom-script"
SCRIPT_NAME = "oom-loop.py"
LABEL = "opentelemetry.io/name"
DEFAULT_IMAGE = "docker.io/library/python:3.12-alpine3.23"
DEFAULT_LIMIT_MIB = "100"

_SCRIPT = r"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

start_mib = int(os.environ.get("MEMORY_START_MIB", "16"))
step_mib = int(os.environ.get("MEMORY_STEP_MIB", "20"))
step_seconds = int(os.environ.get("MEMORY_STEP_SECONDS", "30"))
warmup = int(os.environ.get("MEMORY_WARMUP_SECONDS", "20"))
fail_mib = int(os.environ.get("HEALTH_FAIL_MIB", "80"))
otlp = os.environ.get("OTLP_ENDPOINT", "http://127.0.0.1:4318").rstrip("/")
service = os.environ.get("OTEL_SERVICE_NAME", "paymentservice")
pod = os.environ.get("HOSTNAME", "unknown")
chunk = 1024 * 1024
held = []
allocated = {"mib": 0}
healthy = {"ok": True}


class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        code = 200 if healthy["ok"] else 503
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok" if code == 200 else b"fail")

    def log_message(self, format, *args):
        return


def emit_span(error):
    now = time.time_ns()
    body = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {"key": "service.name", "value": {"stringValue": service}},
                            {"key": "k8s.pod.name", "value": {"stringValue": pod}},
                        ]
                    },
                    "scopeSpans": [
                        {
                            "spans": [
                                {
                                    "traceId": os.urandom(16).hex(),
                                    "spanId": os.urandom(8).hex(),
                                    "name": "charge",
                                    "kind": 3,
                                    "startTimeUnixNano": str(now - 5_000_000),
                                    "endTimeUnixNano": str(now),
                                    "status": {"code": 2 if error else 1},
                                }
                            ]
                        }
                    ],
                }
            ]
        }
    ).encode()
    req = urllib.request.Request(
        otlp + "/v1/traces",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=2).read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"otlp export failed: {exc}", flush=True)


def leak():
    print(f"paymentservice started; warmup {warmup}s", flush=True)
    time.sleep(warmup)
    for _ in range(start_mib):
        held.append(bytearray(chunk))
    allocated["mib"] = start_mib
    print(f"memory ramp: {allocated['mib']}Mi", flush=True)
    while True:
        emit_span(error=not healthy["ok"])
        time.sleep(step_seconds)
        for _ in range(step_mib):
            held.append(bytearray(chunk))
        allocated["mib"] += step_mib
        if allocated["mib"] >= fail_mib:
            healthy["ok"] = False
        print(
            f"memory ramp: {allocated['mib']}Mi healthy={healthy['ok']}",
            flush=True,
        )


if __name__ == "__main__":
    threading.Thread(
        target=lambda: HTTPServer(("0.0.0.0", 8080), Health).serve_forever(),
        name="health",
        daemon=True,
    ).start()
    leak()
"""


class ResourceManagement(ScenarioModule):
    name = "resource-management"
    flag_key = "S-IV-Resource-management"
    flag_type = "boolean"
    default = False

    def reconcile(self, cluster, value) -> None:
        enabled = bool(value)
        if not enabled:
            cluster.delete_deployment(DEPLOYMENT_NAME)
            cluster.delete_configmap(CONFIGMAP_NAME)
            return

        cluster.apply_configmap(self._configmap_body(), self.name)
        limit = self._limit_mib()
        current = cluster.get_deployment(DEPLOYMENT_NAME)
        if current is not None and _env(current, "MEMORY_STEP_SECONDS") is not None:
            return

        action = cluster.apply_deployment(
            self._body(cluster.namespace, limit), self.name
        )
        log.info(
            "%s %s limit=%sMi (sawtooth OOM; APM service.name=paymentservice)",
            action,
            DEPLOYMENT_NAME,
            limit,
        )

    def _limit_mib(self) -> str:
        return os.getenv("PAYMENT_OOM_LIMIT_MIB", DEFAULT_LIMIT_MIB)

    def _image(self) -> str:
        return os.getenv("PAYMENT_OOM_IMAGE", DEFAULT_IMAGE)

    def _configmap_body(self) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": CONFIGMAP_NAME},
            "data": {SCRIPT_NAME: _SCRIPT},
        }

    def _body(self, namespace: str, limit_mib: str) -> dict:
        labels = {
            LABEL: DEPLOYMENT_NAME,
            "app.kubernetes.io/name": DEPLOYMENT_NAME,
            "app.kubernetes.io/component": DEPLOYMENT_NAME,
        }
        limit = int(limit_mib)
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": DEPLOYMENT_NAME,
                "namespace": namespace,
                "labels": labels,
            },
            "spec": {
                "replicas": 1,
                "revisionHistoryLimit": 3,
                "selector": {"matchLabels": {LABEL: DEPLOYMENT_NAME}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "containers": [
                            {
                                "name": "paymentservice",
                                "image": self._image(),
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["python3", f"/scripts/{SCRIPT_NAME}"],
                                "env": [
                                    {
                                        "name": "NODE_IP",
                                        "valueFrom": {
                                            "fieldRef": {"fieldPath": "status.hostIP"}
                                        },
                                    },
                                    {
                                        "name": "OTLP_ENDPOINT",
                                        "value": "http://$(NODE_IP):4318",
                                    },
                                    {
                                        "name": "OTEL_SERVICE_NAME",
                                        "value": "paymentservice",
                                    },
                                    {"name": "MEMORY_WARMUP_SECONDS", "value": "20"},
                                    {"name": "MEMORY_START_MIB", "value": "16"},
                                    {"name": "MEMORY_STEP_MIB", "value": "20"},
                                    {"name": "MEMORY_STEP_SECONDS", "value": "30"},
                                    {"name": "HEALTH_FAIL_MIB", "value": "80"},
                                ],
                                "ports": [
                                    {"containerPort": 8080, "name": "health"}
                                ],
                                "volumeMounts": [
                                    {
                                        "name": "script",
                                        "mountPath": "/scripts",
                                        "readOnly": True,
                                    }
                                ],
                                "resources": {
                                    "requests": {
                                        "cpu": "10m",
                                        "memory": "32Mi",
                                    },
                                    "limits": {"memory": f"{limit}Mi"},
                                },
                                "readinessProbe": {
                                    "httpGet": {"path": "/healthz", "port": 8080},
                                    "initialDelaySeconds": 3,
                                    "periodSeconds": 5,
                                    "failureThreshold": 1,
                                },
                                "livenessProbe": {
                                    "httpGet": {"path": "/healthz", "port": 8080},
                                    "initialDelaySeconds": 10,
                                    "periodSeconds": 5,
                                    "failureThreshold": 3,
                                },
                            }
                        ],
                        "volumes": [
                            {
                                "name": "script",
                                "configMap": {
                                    "name": CONFIGMAP_NAME,
                                    "defaultMode": 0o555,
                                },
                            }
                        ],
                    },
                },
            },
        }


def _env(deployment, name: str) -> str | None:
    containers = deployment.spec.template.spec.containers or []
    if not containers:
        return None
    for item in containers[0].env or []:
        if item.name == name:
            return item.value
    return None
