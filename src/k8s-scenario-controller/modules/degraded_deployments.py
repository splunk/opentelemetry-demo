"""S-II — Troubleshoot degraded deployments.

Sales demo 2: K8s Overview → Top issues → PaymentService degraded,
then the same pending-pod / anti-affinity walk as S-I steps 6–9.

Does **not** patch live `payment` / `payment-vA` / `payment-vB`. Dummy
Deployment `paymentservice` uses distinct labels so the real payment
Service never selects it.

5 replicas + required hostname podAntiAffinity, sized for a 3-node
cluster (e.g. dev-astronomy): 3 Running, 2 Pending. YAML on a pending
pod shows spec.affinity.
"""

from __future__ import annotations

import logging
import os

from modules.base import ScenarioModule

log = logging.getLogger("k8s-scenario-controller")

DEPLOYMENT_NAME = "paymentservice"
LABEL = "opentelemetry.io/name"
DEFAULT_REPLICAS = "5"
PAUSE_IMAGE = "registry.k8s.io/pause:3.10"


class DegradedDeployments(ScenarioModule):
    name = "degraded-deployments"
    flag_key = "S-II-Degraded-deployments"
    flag_type = "boolean"
    default = False

    def reconcile(self, cluster, value) -> None:
        enabled = bool(value)
        current = cluster.get_deployment(DEPLOYMENT_NAME)
        if not enabled:
            if current is not None:
                cluster.delete_deployment(DEPLOYMENT_NAME)
            return

        replicas = self._replicas()
        if current is not None and int(current.spec.replicas or 0) == replicas:
            return

        action = cluster.apply_deployment(
            self._body(cluster.namespace, replicas), self.name
        )
        log.info(
            "%s %s replicas=%d (required hostname anti-affinity)",
            action,
            DEPLOYMENT_NAME,
            replicas,
        )

    def _replicas(self) -> int:
        return int(os.getenv("DEGRADED_PAYMENT_REPLICAS", DEFAULT_REPLICAS))

    def _body(self, namespace: str, replicas: int) -> dict:
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
                "replicas": replicas,
                "revisionHistoryLimit": 3,
                "selector": {"matchLabels": {LABEL: DEPLOYMENT_NAME}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "affinity": {
                            "podAntiAffinity": {
                                "requiredDuringSchedulingIgnoredDuringExecution": [
                                    {
                                        "labelSelector": {
                                            "matchLabels": {LABEL: DEPLOYMENT_NAME}
                                        },
                                        "topologyKey": "kubernetes.io/hostname",
                                    }
                                ]
                            }
                        },
                        "containers": [
                            {
                                "name": "pause",
                                "image": PAUSE_IMAGE,
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
