"""Kubernetes scenario controller.

Polls flagd over OFREP and reconciles each discovered scenario module.
On startup, cluster state is synced from flagd. On SIGTERM/SIGINT the
controller turns every scenario off so dummy workloads do not linger.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from cluster import Cluster
from flagclient import FlagClient
from modules import load_modules

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("k8s-scenario-controller")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/readyz", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server(port: int) -> None:
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, name="health", daemon=True)
    thread.start()
    log.info("health server listening on :%d", port)


def install_stop_handler(stop: threading.Event) -> None:
    def handler(signum, _frame):
        log.info("received signal %s; will stop all scenarios", signum)
        stop.set()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def sync_from_flagd(modules, flags, cluster, previous: dict, reason: str) -> None:
    log.info("syncing %d scenario(s) from flagd (%s)", len(modules), reason)
    for module in modules:
        try:
            fetched = flags.read_module(module)
            if not fetched.ok:
                log.warning(
                    "skipping %s; flagd unreachable (leaving cluster objects as-is)",
                    module.flag_key,
                )
                continue
            value = fetched.value
            if previous.get(module.name) != value:
                log.info("flag %s = %r", module.flag_key, value)
                previous[module.name] = value
            module.reconcile(cluster, value)
        except Exception:
            log.exception("module %s failed", module.name)


def stop_all_scenarios(modules, cluster) -> None:
    log.info("stopping all scenarios")
    for module in modules:
        try:
            module.teardown(cluster)
            log.info("stopped %s", module.flag_key)
        except Exception:
            log.exception("teardown of %s failed", module.name)


def main() -> None:
    interval = float(os.getenv("RECONCILE_INTERVAL_SECONDS", "5"))
    health_port = int(os.getenv("HEALTH_PORT", "8080"))
    start_health_server(health_port)

    stop = threading.Event()
    install_stop_handler(stop)

    flags = FlagClient()
    cluster = Cluster.connect()
    modules = load_modules()
    if not modules:
        log.warning("no scenario modules loaded; idling")

    previous: dict[str, object] = {}
    log.info(
        "reconciling every %.1fs in namespace %s against %s",
        interval,
        cluster.namespace,
        flags.base_url,
    )
    try:
        sync_from_flagd(modules, flags, cluster, previous, "startup")
        while not stop.is_set():
            if stop.wait(timeout=interval):
                break
            sync_from_flagd(modules, flags, cluster, previous, "poll")
    finally:
        stop_all_scenarios(modules, cluster)
        log.info("controller stopped")


if __name__ == "__main__":
    main()
