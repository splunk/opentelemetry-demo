"""Report generator — k8s CPU-throttle demo service.

Workload tier is derived from order context (cart contents + currency)
provided by the caller (accounting service). Drives a bimodal+ duration
distribution so APM p50/p90/p99 tell a clear story:

  - light    : ~100k iters     (~50ms,   below quota)
  - medium   : ~500k iters     (~300ms,  brushes throttle)
  - heavy    : ~2M iters       (~5-10s,  clearly throttled)
  - extreme  : ~10M iters      (~60s+,   severe throttle)

Tier selection rules (cart × currency):
  | cart has HIGH_VALUE SKU | currency      | tier    |
  | no                      | USD           | light   |
  | no                      | non-USD       | medium  |
  | yes                     | USD           | heavy   |
  | yes                     | non-USD       | extreme |

Plus a random 5% audit overlay forces extreme regardless. Real story:
"high-value items need compliance review; cross-border adds work; we
audit-sample 5% of orders no matter what."

Flag-gated kill-switch:
  reportGeneratorThrottle = on  -> compute the tier path as designed.
  reportGeneratorThrottle = off -> skip work, return precomputed stub.

The "real" production fix is raising the container's cpu limit; the
flag is the in-process kill-switch story for demo flips.
"""
import asyncio
import hashlib
import logging
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from openfeature import api
from openfeature.contrib.hook.opentelemetry import TracingHook
from openfeature.contrib.provider.flagd import FlagdProvider
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("report-generator")

BACKGROUND_INTERVAL = int(os.getenv("REPORT_BACKGROUND_INTERVAL_SECONDS", "0"))
PORT = int(os.getenv("REPORT_PORT", "8080"))
FLAGD_HOST = os.getenv("FLAGD_HOST", "flagd")
FLAGD_PORT = int(os.getenv("FLAGD_PORT", "8013"))
THROTTLE_FLAG = "reportGeneratorThrottle"

# High-value SKUs that trigger the heavy/extreme compliance path.
# Default: the Optical Tube Assembly ($3599) — highest-priced item in
# the catalog. Override via env to flag other SKUs.
HIGH_VALUE_SKUS = {
    s.strip() for s in os.getenv("HIGH_VALUE_SKUS", "9SIQT8TOJO").split(",") if s.strip()
}

# Per-tier iteration counts (sha256 chain length). Tune to shape the
# duration spread.
TIER_ITERATIONS = {
    "light": int(os.getenv("REPORT_ITERATIONS_LIGHT", "100000")),
    "medium": int(os.getenv("REPORT_ITERATIONS_MEDIUM", "500000")),
    "heavy": int(os.getenv("REPORT_ITERATIONS_HEAVY", "2000000")),
    "extreme": int(os.getenv("REPORT_ITERATIONS_EXTREME", "10000000")),
}

# Probability that any order — regardless of tier — gets flagged for a
# "random audit" and forced to extreme. Adds genuine p99 tail noise.
AUDIT_SAMPLE_RATE = float(os.getenv("REPORT_AUDIT_SAMPLE_RATE", "0.05"))

tracer = trace.get_tracer("report-generator")

api.set_provider(FlagdProvider(host=FLAGD_HOST, port=FLAGD_PORT))
api.add_hooks([TracingHook()])
_flag_client = api.get_client()


class ReportRequest(BaseModel):
    currency: Optional[str] = None
    product_ids: Optional[list[str]] = None


def _cpu_burn(seed: str, iterations: int) -> str:
    h = hashlib.sha256(seed.encode()).digest()
    for _ in range(iterations):
        h = hashlib.sha256(h).digest()
    return h.hex()


# Precomputed stub returned when throttle flag is off ("fixed" path).
_STUB_DIGEST = hashlib.sha256(b"report-stub").hexdigest()


def _decide_tier(currency: Optional[str], product_ids: Optional[list[str]]) -> tuple[str, bool, bool]:
    """Return (tier, has_high_value, audit_sampled).

    Audit sampling happens last and forces extreme regardless of the
    cart-derived tier. Caller decides what to log.
    """
    cur = (currency or "USD").upper()
    is_non_usd = cur != "USD"
    has_high_value = bool(product_ids) and any(p in HIGH_VALUE_SKUS for p in product_ids)

    if has_high_value and is_non_usd:
        tier = "extreme"
    elif has_high_value:
        tier = "heavy"
    elif is_non_usd:
        tier = "medium"
    else:
        tier = "light"

    audit_sampled = False
    if AUDIT_SAMPLE_RATE > 0 and random.random() < AUDIT_SAMPLE_RATE:
        tier = "extreme"
        audit_sampled = True

    return tier, has_high_value, audit_sampled


def generate_report(
    order_id: str,
    currency: Optional[str] = None,
    product_ids: Optional[list[str]] = None,
) -> dict:
    with tracer.start_as_current_span("generate_report") as span:
        span.set_attribute("app.report.order_id", order_id)
        throttle_on = _flag_client.get_boolean_value(THROTTLE_FLAG, True)
        span.set_attribute("app.report.throttle_flag", throttle_on)

        tier, has_high_value, audit_sampled = _decide_tier(currency, product_ids)
        span.set_attribute("app.report.tier", tier)
        span.set_attribute("app.report.currency", (currency or "USD").upper())
        span.set_attribute("app.report.has_high_value_sku", has_high_value)
        span.set_attribute("app.report.audit_sampled", audit_sampled)
        if product_ids:
            span.set_attribute("app.report.product_ids", ",".join(product_ids))

        start = time.monotonic()
        if throttle_on:
            iterations = TIER_ITERATIONS[tier]
            span.set_attribute("app.report.path", "full")
            span.set_attribute("app.report.iterations", iterations)
            digest = _cpu_burn(order_id, iterations)
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
            "tier": tier,
            "path": "full" if throttle_on else "stub",
        }


async def _background_loop():
    counter = 0
    while True:
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, generate_report, f"bg-{counter}", "USD", None
            )
            counter += 1
        except Exception:
            log.exception("background report failed")
        await asyncio.sleep(BACKGROUND_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if BACKGROUND_INTERVAL > 0:
        task = asyncio.create_task(_background_loop())
        log.info(
            "report-generator started w/ background loop (interval=%ds, flagd=%s:%d, high_value_skus=%s)",
            BACKGROUND_INTERVAL, FLAGD_HOST, FLAGD_PORT, sorted(HIGH_VALUE_SKUS),
        )
    else:
        log.info(
            "report-generator started (background loop disabled, flagd=%s:%d, high_value_skus=%s)",
            FLAGD_HOST, FLAGD_PORT, sorted(HIGH_VALUE_SKUS),
        )
    try:
        yield
    finally:
        if task is not None:
            task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/state")
def state():
    """Observable state for AI/operator. Reports flag + tier config.

    Advisory only — does not actuate flagd. The honest demo separates
    observation (this endpoint) from remediation (kubectl / flagd-ui).
    """
    throttle_on = _flag_client.get_boolean_value(THROTTLE_FLAG, True)
    return {
        "throttle_flag": throttle_on,
        "high_value_skus": sorted(HIGH_VALUE_SKUS),
        "tier_iterations": TIER_ITERATIONS,
        "audit_sample_rate": AUDIT_SAMPLE_RATE,
        "background_interval_seconds": BACKGROUND_INTERVAL,
    }


@app.post("/report/{order_id}")
async def report(order_id: str, body: Optional[ReportRequest] = None):
    currency = body.currency if body else None
    product_ids = body.product_ids if body else None
    return await asyncio.get_running_loop().run_in_executor(
        None, generate_report, order_id, currency, product_ids
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
