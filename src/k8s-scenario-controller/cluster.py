"""Namespaced Kubernetes helpers shared by scenario modules.

Modules should call these instead of the raw client so create/delete/patch
and managed-by labels stay consistent across scenarios.
"""

from __future__ import annotations

import copy
import logging
import os

from kubernetes import client, config
from kubernetes.client.rest import ApiException

log = logging.getLogger("k8s-scenario-controller")

MANAGED_BY = "k8s-scenario-controller"
MANAGED_LABEL = "app.kubernetes.io/managed-by"
MODULE_LABEL = "k8s-scenario-controller/module"


class Cluster:
    def __init__(self, namespace: str):
        self.namespace = namespace
        self.apps = client.AppsV1Api()
        self.core = client.CoreV1Api()

    @classmethod
    def connect(cls) -> "Cluster":
        try:
            config.load_incluster_config()
            log.info("using in-cluster Kubernetes config")
        except config.ConfigException:
            config.load_kube_config()
            log.info("using local kubeconfig")
        namespace = os.getenv("POD_NAMESPACE") or _default_namespace()
        return cls(namespace)

    def managed_labels(self, module_name: str, extra: dict | None = None) -> dict:
        labels = {
            MANAGED_LABEL: MANAGED_BY,
            MODULE_LABEL: module_name,
            "app.kubernetes.io/part-of": "splunk-opentelemetry-demo",
        }
        if extra:
            labels.update(extra)
        return labels

    def stamp(self, body: dict, module_name: str) -> dict:
        """Attach managed-by labels. Does not rewrite spec.selector."""
        stamped = copy.deepcopy(body)
        meta = stamped.setdefault("metadata", {})
        meta.setdefault("namespace", self.namespace)
        meta.setdefault("labels", {}).update(self.managed_labels(module_name))
        template = (
            stamped.setdefault("spec", {})
            .setdefault("template", {})
            .setdefault("metadata", {})
        )
        template.setdefault("labels", {}).update(
            {
                MANAGED_LABEL: MANAGED_BY,
                MODULE_LABEL: module_name,
            }
        )
        return stamped

    def get_deployment(self, name: str):
        try:
            return self.apps.read_namespaced_deployment(name, self.namespace)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def deployment_exists(self, name: str) -> bool:
        return self.get_deployment(name) is not None

    def apply_deployment(self, body: dict, module_name: str) -> str:
        return self._apply(
            kind="Deployment",
            body=self.stamp(body, module_name),
            read=self.apps.read_namespaced_deployment,
            create=self.apps.create_namespaced_deployment,
            replace=self.apps.replace_namespaced_deployment,
        )

    def delete_deployment(self, name: str) -> str:
        return self._delete(
            kind="Deployment",
            name=name,
            delete=lambda: self.apps.delete_namespaced_deployment(name, self.namespace),
        )

    def apply_configmap(self, body: dict, module_name: str) -> str:
        stamped = copy.deepcopy(body)
        meta = stamped.setdefault("metadata", {})
        meta.setdefault("namespace", self.namespace)
        meta.setdefault("labels", {}).update(self.managed_labels(module_name))
        return self._apply(
            kind="ConfigMap",
            body=stamped,
            read=self.core.read_namespaced_config_map,
            create=self.core.create_namespaced_config_map,
            replace=self.core.replace_namespaced_config_map,
        )

    def delete_configmap(self, name: str) -> str:
        return self._delete(
            kind="ConfigMap",
            name=name,
            delete=lambda: self.core.delete_namespaced_config_map(name, self.namespace),
        )

    def apply_service(self, body: dict, module_name: str) -> str:
        stamped = copy.deepcopy(body)
        meta = stamped.setdefault("metadata", {})
        meta.setdefault("namespace", self.namespace)
        meta.setdefault("labels", {}).update(self.managed_labels(module_name))
        return self._apply(
            kind="Service",
            body=stamped,
            read=self.core.read_namespaced_service,
            create=self.core.create_namespaced_service,
            replace=self.core.replace_namespaced_service,
        )

    def delete_service(self, name: str) -> str:
        return self._delete(
            kind="Service",
            name=name,
            delete=lambda: self.core.delete_namespaced_service(name, self.namespace),
        )

    def _apply(self, kind, body, read, create, replace) -> str:
        name = body["metadata"]["name"]
        try:
            current = read(name, self.namespace)
            body["metadata"]["resourceVersion"] = current.metadata.resource_version
            replace(name, self.namespace, body)
            return "updated"
        except ApiException as exc:
            if exc.status != 404:
                raise
            create(self.namespace, body)
            return "created"

    def _delete(self, kind, name, delete) -> str:
        try:
            delete()
            log.info("deleted %s/%s", kind, name)
            return "deleted"
        except ApiException as exc:
            if exc.status == 404:
                return "absent"
            raise


def _default_namespace() -> str:
    path = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip() or "default"
    except FileNotFoundError:
        return os.getenv("NAMESPACE", "default")
