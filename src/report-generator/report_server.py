"""Report generator — k8s CPU-throttle demo service.

Flag-gated workload:
  reportGeneratorThrottle = on  -> run full sha256 chain, exceeds CFS quota
                                    under tight cpu limit, triggers throttle.
  reportGeneratorThrottle = off -> return precomputed stub. No throttle.

Default flag state is "on" (broken). Operator toggles off via flagd-ui to
simulate the "fix" code path. Real production fix would be raising the
container's cpu limit; demo path lets you show both stories.
"""
import asyncio
import hashlib
import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from openfeature import api
from openfeature.contrib.hook.opentelemetry import TracingHook
from openfeature.contrib.provider.flagd import FlagdProvider
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("report-generator")

ITERATIONS = int(os.getenv("REPORT_ITERATIONS", "1500000"))
BACKGROUND_INTERVAL = int(os.getenv("REPORT_BACKGROUND_INTERVAL_SECONDS", "15"))
PORT = int(os.getenv("REPORT_PORT", "8080"))
FLAGD_HOST = os.getenv("FLAGD_HOST", "flagd")
FLAGD_PORT = int(os.getenv("FLAGD_PORT", "8013"))
THROTTLE_FLAG = "reportGeneratorThrottle"

tracer = trace.get_tracer("report-generator")

api.set_provider(FlagdProvider(host=FLAGD_HOST, port=FLAGD_PORT))
api.add_hooks([TracingHook()])
_flag_client = api.get_client()


def _cpu_burn(seed: str, iterations: int) -> str:
    h = hashlib.sha256(seed.encode()).digest()
    for _ in range(iterations):
        h = hashlib.sha256(h).digest()
    return h.hex()


# Precomputed stub returned when throttle flag is off ("fixed" path).
_STUB_DIGEST = hashlib.sha256(b"report-stub").hexdigest()


def generate_report(order_id: str) -> dict:
    with tracer.start_as_current_span("generate_report") as span:
        span.set_attribute("app.report.order_id", order_id)
        throttle_on = _flag_client.get_boolean_value(THROTTLE_FLAG, True)
        span.set_attribute("app.report.throttle_flag", throttle_on)

        start = time.monotonic()
        if throttle_on:
            span.set_attribute("app.report.path", "full")
            span.set_attribute("app.report.iterations", ITERATIONS)
            digest = _cpu_burn(order_id, ITERATIONS)
        else:
            span.set_attribute("app.report.path", "stub")
            digest = _STUB_DIGEST
        elapsed_ms = (time.monotonic() - start) * 1000
        span.set_attribute("app.report.duration_ms", elapsed_ms)
        if throttle_on and elapsed_ms > 2000:
            span.set_status(Status(StatusCode.OK, "slow — likely CPU throttled"))
        return {
            "order_id": order_id,
            "digest": digest,
            "duration_ms": elapsed_ms,
            "path": "full" if throttle_on else "stub",
        }


async def _background_loop():
    counter = 0
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, generate_report, f"bg-{counter}"
            )
            counter += 1
        except Exception:
            log.exception("background report failed")
        await asyncio.sleep(BACKGROUND_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_background_loop())
    log.info(
        "report-generator started (iterations=%d, interval=%ds, flagd=%s:%d)",
        ITERATIONS, BACKGROUND_INTERVAL, FLAGD_HOST, FLAGD_PORT,
    )
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/state")
def state():
    """Observable state for AI/operator. Reports flag + last-seen path.

    Advisory only — does not actuate flagd. The honest demo separates
    observation (this endpoint) from remediation (kubectl / flagd-ui).
    """
    throttle_on = _flag_client.get_boolean_value(THROTTLE_FLAG, True)
    return {
        "throttle_flag": throttle_on,
        "iterations": ITERATIONS,
        "background_interval_seconds": BACKGROUND_INTERVAL,
    }


@app.post("/report/{order_id}")
async def report(order_id: str):
    return await asyncio.get_running_loop().run_in_executor(
        None, generate_report, order_id
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
