"""Order validation — k8s CPU-throttle demo service.

Validates each incoming order against a synthetic compliance/audit
workload. Workload size depends on order context (cart contents +
currency) passed by the caller (accounting). Drives a bimodal+ duration
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

Plus a random 5% audit overlay forces extreme regardless. Story:
"high-value items need export-control review; cross-border adds work;
we audit-sample 5% of orders no matter what."

Flag-gated kill-switch:
  orderValidationThrottle = on  -> compute the tier path as designed.
  orderValidationThrottle = off -> skip work, return precomputed stub.

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
log = logging.getLogger("order-validation")

BACKGROUND_INTERVAL = int(os.getenv("VALIDATION_BACKGROUND_INTERVAL_SECONDS", "0"))
# Foreign currencies used by background heartbeat to force the extreme
# tier (non-USD + high-value SKU). Spread across regions so the demo
# story isn't always the same country.
BACKGROUND_CURRENCIES = [
    c.strip() for c in os.getenv(
        "VALIDATION_BACKGROUND_CURRENCIES", "RUB,ZAR,BRL,PLN,MMK"
    ).split(",") if c.strip()
]
PORT = int(os.getenv("VALIDATION_PORT", "8080"))
FLAGD_HOST = os.getenv("FLAGD_HOST", "flagd")
FLAGD_PORT = int(os.getenv("FLAGD_PORT", "8013"))
THROTTLE_FLAG = "orderValidationThrottle"

# High-value SKUs that trigger the heavy/extreme compliance path.
# Default: the Optical Tube Assembly ($3599) — highest-priced item in
# the catalog. Override via env to flag other SKUs.
HIGH_VALUE_SKUS = {
    s.strip() for s in os.getenv("HIGH_VALUE_SKUS", "9SIQT8TOJO").split(",") if s.strip()
}

# Per-tier iteration counts (sha256 chain length). For non-extreme tiers
# the work is paced (chunks + sleeps) so per-100ms CPU stays well under
# the container's quota — CPU chart shows flat-low w/ tiny spikes, no
# throttle. Extreme runs a tight loop and pegs the limit for the full
# duration, producing the dramatic single-tier signature.
TIER_ITERATIONS = {
    "light": int(os.getenv("VALIDATION_ITERATIONS_LIGHT", "30000")),
    "medium": int(os.getenv("VALIDATION_ITERATIONS_MEDIUM", "100000")),
    "heavy": int(os.getenv("VALIDATION_ITERATIONS_HEAVY", "300000")),
    "extreme": int(os.getenv("VALIDATION_ITERATIONS_EXTREME", "3000000")),
}

# Wall-clock targets for non-extreme tiers — work is paced over this
# duration with sleep slack so the CPU never sustains at the limit.
# Extreme has no target: it runs tight, wall time = throttle * work.
TIER_TARGET_SECONDS = {
    "light": float(os.getenv("VALIDATION_TARGET_LIGHT_SECONDS", "2.0")),
    "medium": float(os.getenv("VALIDATION_TARGET_MEDIUM_SECONDS", "5.0")),
    "heavy": float(os.getenv("VALIDATION_TARGET_HEAVY_SECONDS", "10.0")),
}

PACING_CHUNKS = int(os.getenv("VALIDATION_PACING_CHUNKS", "10"))

# Probability that any order — regardless of tier — gets flagged for a
# "random audit" and forced to extreme. Adds genuine p99 tail noise.
AUDIT_SAMPLE_RATE = float(os.getenv("VALIDATION_AUDIT_SAMPLE_RATE", "0.05"))

tracer = trace.get_tracer("order-validation")

api.set_provider(FlagdProvider(host=FLAGD_HOST, port=FLAGD_PORT))
api.add_hooks([TracingHook()])
_flag_client = api.get_client()


class ValidationRequest(BaseModel):
    currency: Optional[str] = None
    product_ids: Optional[list[str]] = None


def _cpu_burn(seed: str, iterations: int) -> str:
    h = hashlib.sha256(seed.encode()).digest()
    for _ in range(iterations):
        h = hashlib.sha256(h).digest()
    return h.hex()


def _paced_burn(seed: str, iterations: int, target_seconds: float, chunks: int) -> str:
    """Spread CPU work across `target_seconds` wall time in N chunks.

    Each chunk does a small CPU burst then sleeps to fill the per-chunk
    budget. Per-100ms CPU usage stays well under the CFS quota, so
    these tiers do not throttle. Wall time ≈ target_seconds regardless
    of how fast the host CPU actually is.
    """
    per_chunk_iter = max(1, iterations // chunks)
    per_chunk_budget = target_seconds / chunks
    h = hashlib.sha256(seed.encode()).digest()
    for i in range(chunks):
        chunk_start = time.monotonic()
        for _ in range(per_chunk_iter):
            h = hashlib.sha256(h).digest()
        elapsed = time.monotonic() - chunk_start
        slack = per_chunk_budget - elapsed
        if slack > 0:
            time.sleep(slack)
    return h.hex()


# Precomputed stub returned when throttle flag is off ("fixed" path).
_STUB_DIGEST = hashlib.sha256(b"validation-stub").hexdigest()


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


def validate_order(
    order_id: str,
    currency: Optional[str] = None,
    product_ids: Optional[list[str]] = None,
) -> dict:
    with tracer.start_as_current_span("validate_order") as span:
        span.set_attribute("app.validation.order_id", order_id)
        try:
            throttle_on = _flag_client.get_boolean_value(THROTTLE_FLAG, True)
            span.set_attribute("app.validation.throttle_flag", throttle_on)

            tier, has_high_value, audit_sampled = _decide_tier(currency, product_ids)
            span.set_attribute("app.validation.tier", tier)
            span.set_attribute("app.validation.currency", (currency or "USD").upper())
            span.set_attribute("app.validation.has_high_value_sku", has_high_value)
            span.set_attribute("app.validation.audit_sampled", audit_sampled)
            if product_ids:
                span.set_attribute("app.validation.product_ids", ",".join(product_ids))

            log.info(
                "validate request: order_id=%s currency=%s product_ids=%s "
                "tier=%s has_high_value=%s audit_sampled=%s throttle=%s",
                order_id, (currency or "USD").upper(), product_ids or [],
                tier, has_high_value, audit_sampled, throttle_on,
            )

            start = time.monotonic()
            if throttle_on:
                iterations = TIER_ITERATIONS[tier]
                span.set_attribute("app.validation.path", "full")
                span.set_attribute("app.validation.iterations", iterations)
                if tier == "extreme":
                    # Tight loop — peg the CPU at the container limit for
                    # the full duration. Produces the dramatic single-tier
                    # throttle signature in IM.
                    span.set_attribute("app.validation.pacing", "tight")
                    digest = _cpu_burn(order_id, iterations)
                else:
                    # Paced work — wall time held to TIER_TARGET_SECONDS,
                    # per-100ms CPU stays sub-quota, no sustained throttle.
                    target = TIER_TARGET_SECONDS[tier]
                    span.set_attribute("app.validation.pacing", "paced")
                    span.set_attribute("app.validation.target_seconds", target)
                    span.set_attribute("app.validation.chunks", PACING_CHUNKS)
                    digest = _paced_burn(order_id, iterations, target, PACING_CHUNKS)
            else:
                span.set_attribute("app.validation.path", "stub")
                digest = _STUB_DIGEST
            elapsed_ms = (time.monotonic() - start) * 1000
            span.set_attribute("app.validation.duration_ms", elapsed_ms)
            if throttle_on and elapsed_ms > 2000:
                span.set_status(Status(StatusCode.OK, "slow — likely CPU throttled"))

            log.info(
                "validate done: order_id=%s tier=%s duration_ms=%.1f path=%s",
                order_id, tier, elapsed_ms, "full" if throttle_on else "stub",
            )
            return {
                "order_id": order_id,
                "digest": digest,
                "duration_ms": elapsed_ms,
                "tier": tier,
                "path": "full" if throttle_on else "stub",
            }
        except Exception:
            # Log full stacktrace + mark span; re-raise so FastAPI returns 500.
            log.exception("validate failed: order_id=%s", order_id)
            span.set_status(Status(StatusCode.ERROR, "validation raised"))
            raise


async def _background_loop():
    """Periodic heartbeat that guarantees the extreme tier appears.

    Real orders skew light/medium; extreme depends on cart contents
    (non-USD + high-value SKU) and is sparse, leaving the p99 chart
    flat between hits. This loop forces an extreme call on a fixed
    cadence so the throttle story is always visible.

    Order id format `99-{16-digit}` is intentionally distinct from
    the UUID format used by real orders, so synthetic traffic is
    easy to filter out in APM.
    """
    while True:
        order_id = f"99-{random.randint(10**15, 10**16 - 1)}"
        currency = random.choice(BACKGROUND_CURRENCIES) if BACKGROUND_CURRENCIES else "RUB"
        product_ids = list(HIGH_VALUE_SKUS) or None
        try:
            await asyncio.get_running_loop().run_in_executor(
                None, validate_order, order_id, currency, product_ids
            )
        except Exception:
            log.exception("background validation failed")
        await asyncio.sleep(BACKGROUND_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = None
    if BACKGROUND_INTERVAL > 0:
        task = asyncio.create_task(_background_loop())
        log.info(
            "order-validation started w/ background loop (interval=%ds, flagd=%s:%d, high_value_skus=%s)",
            BACKGROUND_INTERVAL, FLAGD_HOST, FLAGD_PORT, sorted(HIGH_VALUE_SKUS),
        )
    else:
        log.info(
            "order-validation started (background loop disabled, flagd=%s:%d, high_value_skus=%s)",
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


@app.post("/validate/{order_id}")
async def validate(order_id: str, body: Optional[ValidationRequest] = None):
    currency = body.currency if body else None
    product_ids = body.product_ids if body else None
    return await asyncio.get_running_loop().run_in_executor(
        None, validate_order, order_id, currency, product_ids
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
