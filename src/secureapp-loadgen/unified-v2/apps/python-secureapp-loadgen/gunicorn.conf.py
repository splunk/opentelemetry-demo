"""Gunicorn configuration for SecureApp Python datagen.
"""

bind = "0.0.0.0:8080"
workers = 1
threads = 4
timeout = 120
accesslog = "-"
errorlog = "-"
loglevel = "info"


def post_fork(server, worker):  # noqa: ANN001
    try:
        import splunk_secureapp_opentelemetry_extension.agent as agent_module
        from splunk_secureapp_opentelemetry_extension import start_monitoring

        existing = agent_module._agent
        if existing is not None:
            existing.shutdown()
            agent_module._agent = None

        start_monitoring()
        server.log.info("SecureApp dependency monitoring restarted in worker %s", worker.pid)
    except Exception as exc:  # noqa: BLE001
        server.log.warning("SecureApp post_fork restart failed: %s", exc)
