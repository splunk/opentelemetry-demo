"""Kubernetes scenario controller.

Polls flagd over OFREP and reconciles each discovered scenario module.
Adding a scenario is a new file under modules/ plus a flagd flag.
"""

from __future__ import annotations

import logging
import os
import threading
import time
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


def main() -> None:
    interval = float(os.getenv("RECONCILE_INTERVAL_SECONDS", "5"))
    health_port = int(os.getenv("HEALTH_PORT", "8080"))
    start_health_server(health_port)

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
    while True:
        for module in modules:
            try:
                value = module.read_flag(flags)
                if previous.get(module.name) != value:
                    log.info("flag %s = %r", module.flag_key, value)
                    previous[module.name] = value
                module.reconcile(cluster, value)
            except Exception:
                log.exception("module %s failed", module.name)
        time.sleep(interval)


if __name__ == "__main__":
    main()
