"""Scenario 2 — ImagePullBackOff.

Field demo: kubernetes-demos/scenario2-image-pull (payment with
registry.invalid/payment_bad:latest).

Astronomy Shop already has a real payment service, so this module
creates a *separate* dummy Deployment instead of patching payment.
Distinct labels keep the real payment Service from selecting it.
"""

from __future__ import annotations

import logging
import os

from modules.base import ScenarioModule

log = logging.getLogger("k8s-scenario-controller")

DEPLOYMENT_NAME = "payment-imagepull"
CONTAINER_NAME = "payment-imagepull"
DEFAULT_BAD_IMAGE = "registry.invalid/payment_bad:latest"


class ImagePullBackoff(ScenarioModule):
    name = "image-pull"
    flag_key = "imagePullBackoff"
    flag_type = "boolean"
    default = False

    def reconcile(self, cluster, value) -> None:
        enabled = bool(value)
        current = cluster.get_deployment(DEPLOYMENT_NAME)
        if not enabled:
            if current is not None:
                cluster.delete_deployment(DEPLOYMENT_NAME)
            return

        desired_image = self._bad_image()
        if current is not None and self._current_image(current) == desired_image:
            return

        action = cluster.apply_deployment(self._body(cluster.namespace), self.name)
        log.info(
            "%s %s with image %s (expected ImagePullBackOff)",
            action,
            DEPLOYMENT_NAME,
            desired_image,
        )

    @staticmethod
    def _current_image(deployment) -> str | None:
        containers = deployment.spec.template.spec.containers or []
        if not containers:
            return None
        return containers[0].image

    def _bad_image(self) -> str:
        return os.getenv("IMAGEPULL_BAD_IMAGE", DEFAULT_BAD_IMAGE)

    def _body(self, namespace: str) -> dict:
        labels = {
            "opentelemetry.io/name": DEPLOYMENT_NAME,
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
                "selector": {"matchLabels": {"opentelemetry.io/name": DEPLOYMENT_NAME}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "containers": [
                            {
                                "name": CONTAINER_NAME,
                                "image": self._bad_image(),
                                "imagePullPolicy": "Always",
                                "resources": {
                                    "requests": {"cpu": "1m", "memory": "8Mi"},
                                    "limits": {"memory": "16Mi"},
                                },
                            }
                        ]
                    },
                },
            },
        }
