"""Controller watchdog test — flagd `S-TEST-shelltester`.

On: ConfigMap + Deployment run a shell loop that POSTs OTLP gauge
`scenariotest_metric` to the node-local collector (same NODE_IP:4318
path as shop pods). Value steps 0→100 then resets to 0.

Off: delete the dummy Deployment and ConfigMap (script stops).

Each reconcile (default 5s) checks that a Running pod exists while the
flag is on and recreates it if it vanished or crash-looped.

Does not touch live shop Deployments. No Splunk tokens — metrics go
through the already-configured otel-collector agent.
"""

from __future__ import annotations

import logging
import os

from modules.base import ScenarioModule

log = logging.getLogger("k8s-scenario-controller")

DEPLOYMENT_NAME = "shell-tester"
CONFIGMAP_NAME = "shell-tester-script"
CONTAINER_NAME = "shell-tester"
SCRIPT_NAME = "emit-metric.sh"
LABEL = "opentelemetry.io/name"
DEFAULT_IMAGE = "docker.io/library/busybox:1.37.0"
DEFAULT_METRIC = "scenariotest_metric"
DEFAULT_INTERVAL = "1"

# Busybox wget POSTs OTLP/JSON to the node agent. VALUE wraps after 100.
_SCRIPT = r"""#!/bin/sh
ENDPOINT="${OTLP_ENDPOINT:-http://127.0.0.1:4318}"
METRIC="${METRIC_NAME:-scenariotest_metric}"
INTERVAL="${INTERVAL_SECONDS:-1}"
VALUE=0

echo "shell-tester starting metric=${METRIC} endpoint=${ENDPOINT} interval=${INTERVAL}s"

while true; do
  TS="$(date +%s)000000000"
  BODY=$(printf '{"resourceMetrics":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"shell-tester"}},{"key":"k8s.pod.name","value":{"stringValue":"%s"}}]},"scopeMetrics":[{"metrics":[{"name":"%s","gauge":{"dataPoints":[{"asInt":"%s","timeUnixNano":"%s"}]}}]}]}]}' \
    "${HOSTNAME:-unknown}" "$METRIC" "$VALUE" "$TS")
  if ! wget -q -O /dev/null \
      --header="Content-Type: application/json" \
      --post-data="$BODY" \
      "${ENDPOINT}/v1/metrics"; then
    echo "otlp export failed value=${VALUE}" >&2
  fi
  if [ "$VALUE" -ge 100 ]; then
    VALUE=0
  else
    VALUE=$((VALUE + 1))
  fi
  sleep "$INTERVAL"
done
"""


class ShellTester(ScenarioModule):
    name = "shell-tester"
    flag_key = "S-TEST-shelltester"
    flag_type = "boolean"
    default = False

    def reconcile(self, cluster, value) -> None:
        enabled = bool(value)
        if not enabled:
            cluster.delete_deployment(DEPLOYMENT_NAME)
            cluster.delete_configmap(CONFIGMAP_NAME)
            return

        cluster.apply_configmap(self._configmap_body(), self.name)

        current = cluster.get_deployment(DEPLOYMENT_NAME)
        if current is None:
            action = cluster.apply_deployment(self._deployment_body(cluster.namespace), self.name)
            log.info("%s %s (metric loop expected to start)", action, DEPLOYMENT_NAME)
            return

        pods = cluster.list_pods(f"{LABEL}={DEPLOYMENT_NAME}")
        running = [pod for pod in pods if _script_is_up(pod)]
        if running:
            return

        phases = [_pod_summary(pod) for pod in pods] or ["(no pods)"]
        if _should_recreate(pods):
            log.warning(
                "%s should be up but is not (%s); recreating",
                DEPLOYMENT_NAME,
                "; ".join(phases),
            )
            cluster.apply_deployment(self._deployment_body(cluster.namespace), self.name)
            return

        log.warning(
            "%s should be up; waiting (%s)",
            DEPLOYMENT_NAME,
            "; ".join(phases),
        )

    def _image(self) -> str:
        return os.getenv("SHELLTESTER_IMAGE", DEFAULT_IMAGE)

    def _metric(self) -> str:
        return os.getenv("SHELLTESTER_METRIC", DEFAULT_METRIC)

    def _interval(self) -> str:
        return os.getenv("SHELLTESTER_INTERVAL_SECONDS", DEFAULT_INTERVAL)

    def _configmap_body(self) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": CONFIGMAP_NAME},
            "data": {SCRIPT_NAME: _SCRIPT},
        }

    def _deployment_body(self, namespace: str) -> dict:
        labels = {
            LABEL: DEPLOYMENT_NAME,
            "app.kubernetes.io/name": DEPLOYMENT_NAME,
            "app.kubernetes.io/component": DEPLOYMENT_NAME,
        }
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
                                "name": CONTAINER_NAME,
                                "image": self._image(),
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["/bin/sh", f"/scripts/{SCRIPT_NAME}"],
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
                                        "name": "METRIC_NAME",
                                        "value": self._metric(),
                                    },
                                    {
                                        "name": "INTERVAL_SECONDS",
                                        "value": self._interval(),
                                    },
                                ],
                                "volumeMounts": [
                                    {
                                        "name": "script",
                                        "mountPath": "/scripts",
                                        "readOnly": True,
                                    }
                                ],
                                "resources": {
                                    "requests": {"cpu": "1m", "memory": "8Mi"},
                                    "limits": {"memory": "16Mi"},
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


def _script_is_up(pod) -> bool:
    if pod.status.phase != "Running":
        return False
    statuses = pod.status.container_statuses or []
    if not statuses:
        return False
    return all(cs.state and cs.state.running for cs in statuses)


def _should_recreate(pods) -> bool:
    """Recreate when the workload is gone or the container is crash-looping.

    Leave Pending / ImagePull alone — replacing those does not help.
    """
    if not pods:
        return True
    for pod in pods:
        if pod.status.phase in ("Failed", "Succeeded", "Unknown"):
            return True
        for cs in pod.status.container_statuses or []:
            waiting = cs.state.waiting if cs.state else None
            if waiting and waiting.reason in ("CrashLoopBackOff", "Error"):
                return True
            if cs.state and cs.state.terminated:
                return True
    return False


def _pod_summary(pod) -> str:
    name = pod.metadata.name
    phase = pod.status.phase or "?"
    reasons = []
    for cs in pod.status.container_statuses or []:
        if cs.state and cs.state.waiting and cs.state.waiting.reason:
            reasons.append(cs.state.waiting.reason)
        elif cs.state and cs.state.terminated and cs.state.terminated.reason:
            reasons.append(cs.state.terminated.reason)
    if reasons:
        return f"{name} {phase}/{','.join(reasons)}"
    return f"{name} {phase}"
