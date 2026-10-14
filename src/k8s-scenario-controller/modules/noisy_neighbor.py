"""S-I — Node pressure & noisy-neighbor impact.

Field demo: kubernetes-demos/scenario1-four-clusters, mapped to the
sales story (otel-collector hog + 10-replica anti-affinity spread).

Does **not** patch the real Splunk OTel Collector or shop Deployments.
Two dummy workloads, distinct labels:

  1. otel-collector-noisy — sandbox script holds MEMORY_MIB (default 256).
     Logs the allocation so Navigator can show "how the app behaves".
     Sized to be the obvious memory outlier without taking the node down;
     raise NOISY_NEIGHBOR_MIB only on a dedicated demo node.
  2. storefront-spread — 10 replicas with *required* podAntiAffinity on
     kubernetes.io/hostname. Pending pods appear when the cluster has
     fewer schedulable nodes than replicas (7 nodes → 7 running / 3
     pending). YAML on a pending pod shows the affinity rule.

Flag off deletes both Deployments and the script ConfigMap.
"""

from __future__ import annotations

import logging
import os

from modules.base import ScenarioModule

log = logging.getLogger("k8s-scenario-controller")

HOG_NAME = "otel-collector-noisy"
SPREAD_NAME = "storefront-spread"
CONFIGMAP_NAME = "noisy-neighbor-script"
LEGACY_CONFIGMAP_NAME = "noisy-neighbour-script"
SCRIPT_NAME = "hog.py"
LABEL = "opentelemetry.io/name"
DEFAULT_IMAGE = "docker.io/library/python:3.12-alpine3.23"
DEFAULT_MIB = "256"
DEFAULT_REPLICAS = "10"

_SCRIPT = """\
import os
import time

mib = int(os.environ.get("MEMORY_MIB", "256"))
chunk = 1024 * 1024
print(f"sandbox: otel-collector noisy-neighbor starting; target={mib}MiB", flush=True)
held = []
for i in range(mib):
    held.append(bytearray(chunk))
    n = i + 1
    if n % 32 == 0 or n == mib:
        print(
            f"sandbox: allocated {n}/{mib} MiB (creating node memory condition)",
            flush=True,
        )
print("sandbox: allocation complete; holding to sustain noisy-neighbor load", flush=True)
while True:
    time.sleep(30)
    print(f"sandbox: still holding {mib} MiB", flush=True)
"""


class NoisyNeighbor(ScenarioModule):
    name = "noisy-neighbor"
    flag_key = "S-I-Noisy-neighbor"
    flag_type = "boolean"
    default = False

    def reconcile(self, cluster, value) -> None:
        cluster.delete_configmap(LEGACY_CONFIGMAP_NAME)
        enabled = bool(value)
        if not enabled:
            cluster.delete_deployment(HOG_NAME)
            cluster.delete_deployment(SPREAD_NAME)
            cluster.delete_configmap(CONFIGMAP_NAME)
            return

        cluster.apply_configmap(self._configmap_body(), self.name)
        mib = self._mib()
        replicas = self._replicas()

        hog = cluster.get_deployment(HOG_NAME)
        spread = cluster.get_deployment(SPREAD_NAME)
        hog_ok = hog is not None and _env(hog, "MEMORY_MIB") == mib
        spread_ok = (
            spread is not None and int(spread.spec.replicas or 0) == replicas
        )
        if hog_ok and spread_ok:
            return

        cluster.apply_deployment(self._hog_body(cluster.namespace, mib), self.name)
        cluster.apply_deployment(
            self._spread_body(cluster.namespace, replicas), self.name
        )
        log.info(
            "noisy-neighbor hog=%sMiB spread=%d (anti-affinity on hostname)",
            mib,
            replicas,
        )

    def _mib(self) -> str:
        return os.getenv("NOISY_NEIGHBOR_MIB", DEFAULT_MIB)

    def _replicas(self) -> int:
        return int(os.getenv("NOISY_SPREAD_REPLICAS", DEFAULT_REPLICAS))

    def _image(self) -> str:
        return os.getenv("NOISY_NEIGHBOR_IMAGE", DEFAULT_IMAGE)

    def _configmap_body(self) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": CONFIGMAP_NAME},
            "data": {SCRIPT_NAME: _SCRIPT},
        }

    def _hog_body(self, namespace: str, mib: str) -> dict:
        labels = {
            LABEL: HOG_NAME,
            "app.kubernetes.io/name": HOG_NAME,
            "app.kubernetes.io/component": "noisy-neighbor",
        }
        mib_int = int(mib)
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": HOG_NAME,
                "namespace": namespace,
                "labels": labels,
            },
            "spec": {
                "replicas": 1,
                "revisionHistoryLimit": 3,
                "strategy": {"type": "Recreate"},
                "selector": {"matchLabels": {LABEL: HOG_NAME}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "containers": [
                            {
                                "name": "sandbox",
                                "image": self._image(),
                                "imagePullPolicy": "IfNotPresent",
                                "command": ["python3", f"/scripts/{SCRIPT_NAME}"],
                                "env": [{"name": "MEMORY_MIB", "value": mib}],
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
                                        "memory": f"{mib_int}Mi",
                                    },
                                    "limits": {
                                        "cpu": "50m",
                                        "memory": f"{mib_int + 64}Mi",
                                    },
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

    def _spread_body(self, namespace: str, replicas: int) -> dict:
        labels = {
            LABEL: SPREAD_NAME,
            "app.kubernetes.io/name": SPREAD_NAME,
            "app.kubernetes.io/component": "noisy-neighbor",
        }
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": SPREAD_NAME,
                "namespace": namespace,
                "labels": labels,
            },
            "spec": {
                "replicas": replicas,
                "revisionHistoryLimit": 3,
                "selector": {"matchLabels": {LABEL: SPREAD_NAME}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "affinity": {
                            "podAntiAffinity": {
                                "requiredDuringSchedulingIgnoredDuringExecution": [
                                    {
                                        "labelSelector": {
                                            "matchLabels": {LABEL: SPREAD_NAME}
                                        },
                                        "topologyKey": "kubernetes.io/hostname",
                                    }
                                ]
                            }
                        },
                        "containers": [
                            {
                                "name": "pause",
                                "image": "registry.k8s.io/pause:3.10",
                                "imagePullPolicy": "IfNotPresent",
                                "resources": {
                                    "requests": {"cpu": "1m", "memory": "8Mi"},
                                    "limits": {"memory": "16Mi"},
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
