# Payment Service A/B Version Behavior

## Overview

The payment service has two distinct versions with different behaviors:

- **Version A (Stable)**: Normal operation - gets token from secret, calls Buttercup Payments, succeeds
- **Version B (Canary/Error)**: Error testing pod - gets token from secret, attempts to call Buttercup Payments 4 times with controlled timing, always fails, logs token in errors

---

## Version A (Stable) - `payment-va`

### Behavior

[x] **Normal payment processing**
- Retrieves API token from secret: `payment-va-secret`
- Calls Buttercup Payments API with token
- **Succeeds** on first attempt (unless real errors occur)
- Returns transaction ID
- Response time: 0-200ms

### Configuration

```javascript
// config/vA-config.js
{
  alwaysFail: false,  // Normal operation
  retryMaxDefault: 4,  // Not used (succeeds on first try)
  successDelayRange: [0, 200],  // 0-200ms response time
}
```

### Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: payment-va-secret
stringData:
  api-token: "prod-a8cf28f9-1a1a-4994-bafa-cd4b143c3291"
```

### Expected Logs

```json
{
  "level": "info",
  "service.name": "payment-va",
  "token": "prod-a8cf28f9-...",
  "version": "v350.9",
  "message": "Charging through ButtercupPayments"
}
```

### OTEL Attributes

```yaml
service.name: payment-va
payment.variant: A
deployment.stability: stable
service.version: 1.7.0-a
```

---

## Version B (Canary/Error) - `payment-vb`

### Behavior

[FAIL] **Always fails with controlled timing**
- Retrieves API token from secret: `payment-vb-secret`
- Attempts to call Buttercup Payments API **4 times**
- **All attempts fail** (simulates error pod for testing)
- Each attempt has **random duration**
- Logs the token from secret in error messages (like original)

### Timing Constraints

| Constraint | Min | Max | Notes |
|------------|-----|-----|-------|
| **Total duration** | 4 seconds | 10 seconds | All 4 attempts combined |
| **First 3 attempts** | 4 seconds | 7.3 seconds | Never longer than 7.3s |
| **4th attempt** | Varies | Varies | Gets remaining time |
| **Each attempt** | Random | Random | Distributed across constraints |

**Example timing**:
```
Total: 8.5 seconds
  Attempt 1: 1.2s (API: 840ms, backoff: 360ms)
  Attempt 2: 2.1s (API: 1470ms, backoff: 630ms)
  Attempt 3: 2.5s (API: 1750ms, backoff: 750ms)  <- First 3: 5.8s total
  Attempt 4: 2.7s (API: 2700ms, backoff: 0ms)    <- Remaining time

Total: 8.5 seconds [x] (within 4-10s)
First 3: 5.8 seconds [x] (within 4-7.3s)
```

### Configuration

```javascript
// config/vB-config.js
{
  alwaysFail: true,  // Always fails (error pod)
  retryMaxDefault: 4,  // Always 4 attempts
  failureTimingConstraints: {
    totalMinMs: 4000,          // 4 seconds min total
    totalMaxMs: 10000,         // 10 seconds max total
    threeAttemptsMinMs: 4000,  // 3 attempts: min 4s
    threeAttemptsMaxMs: 7300,  // 3 attempts: max 7.3s
  },
}
```

### Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: payment-vb-secret
stringData:
  api-token: "test-20e26e90-356b-432e-a2c6-956fc03f5609"
```

### Expected Logs

**Per Attempt** (4 times):
```json
{
  "level": "error",
  "service.name": "payment-vb",
  "token": "test-20e26e90-...",  <- Token from secret
  "version": "v350.10",
  "message": "Failed payment processing through ButtercupPayments: Invalid API Token (test-20e26e90-...)"
}
```

**Final Failure** (after 4 attempts):
```json
{
  "level": "error",
  "service.name": "payment-vb",
  "token": "test-20e26e90-...",  <- Token from secret
  "version": "v350.10",
  "message": "Failed payment processing through ButtercupPayments after 4 retries: Invalid API Token (test-20e26e90-...)"
}
```

**Timing Info** (logged at start):
```json
{
  "level": "info",
  "version": "vB",
  "totalDurationMs": 8500,
  "threeAttemptsDuration": 5800,
  "fourthAttemptDuration": 2700,
  "timings": [
    {"apiDelay": 840, "backoff": 360},
    {"apiDelay": 1470, "backoff": 630},
    {"apiDelay": 1750, "backoff": 750},
    {"apiDelay": 2700, "backoff": 0}
  ],
  "message": "Version B: Calculated controlled failure timings"
}
```

### OTEL Attributes

```yaml
service.name: payment-vb
payment.variant: B
deployment.stability: canary
service.version: 1.7.0-b
app.payment.planned_failure: true
app.payment.target_duration_ms: 8500
retry.count: 4
retry.success: false
error: true
```

---

## Routing Between Versions

The `paymentFailure` flag controls what percentage of traffic goes to version B:

```yaml
"paymentFailure": {
  "variants": {
    "off": 0,      # 0% to B (all to A - stable)
    "10%": 0.1,    # 10% to B (error pod)
    "25%": 0.25,   # 25% to B
    "50%": 0.5,    # 50% to B
    "75%": 0.75,   # 75% to B
    "90%": 0.95,   # 95% to B
    "100%": 1      # 100% to B (all to error pod)
  },
  "defaultVariant": "off"  # Default: all to A
}
```

**Checkout routing logic**:
```go
probability := getFeatureFlagFloat(ctx, "paymentFailure", 0.0)
if rand.Float64() < probability {
    route to payment-vb:8080  // Version B (error pod)
} else {
    route to payment-va:8080  // Version A (stable)
}
```

---

## Comparison

| Feature | Version A | Version B |
|---------|-----------|-----------|
| **Behavior** | Succeeds | Always fails |
| **Secret** | `payment-va-secret` | `payment-vb-secret` |
| **Token** | `prod-a8cf28f9...` | `test-20e26e90...` |
| **Version** | `v350.9` | `v350.10` |
| **Attempts** | 1 (succeeds) | 4 (all fail) |
| **Duration** | 0-200ms | 4-10 seconds |
| **Logs Token** | Yes (on success) | Yes (in errors) |
| **Use Case** | Production baseline | Error testing/canary |
| **OTEL Tag** | `payment.variant=A` | `payment.variant=B` |

---

## Testing Scenarios

### Scenario 1: Normal Traffic (All to Version A)

**Flag**: `off` (0)

**Result**:
- All payments go to `payment-va`
- All succeed in ~100ms
- Logs show `prod-a8cf28f9...` token with version `v350.9`
- No errors

### Scenario 2: Error Testing (10% to Version B)

**Flag**: `10%` (0.1)

**Result**:
- 90% of payments -> `payment-va` (succeed)
- 10% of payments -> `payment-vb` (fail after 4-10 seconds)
- Version B logs show `test-20e26e90...` token with version `v350.10` in errors
- Can compare error behavior in Splunk APM

### Scenario 3: Full Error Mode (All to Version B)

**Flag**: `100%` (1)

**Result**:
- All payments go to `payment-vb`
- All fail with 4 retry attempts
- Total duration: 4-10 seconds per payment
- Logs show `test-20e26e90...` token with version `v350.10` in all error messages
- Useful for testing error handling, retry behavior, timeout handling

---

## Key Points

[x] **Version A**: Retrieves token from `payment-va-secret`, calls Buttercup, succeeds
[x] **Version B**: Retrieves token from `payment-vb-secret`, attempts 4 calls, always fails
[x] **Both versions**: Use tokens from their respective secrets
[x] **Version B logs token**: In error messages (like original implementation)
[x] **Controlled timing**: Version B has precise timing constraints (4-10s total, 3 attempts 4-7.3s)
[x] **Random per attempt**: Each of the 4 attempts has random duration within constraints
[x] **Flag-based routing**: Checkout routes based on `paymentFailure` flag value

---

## Observability

### Splunk APM Queries

**Compare success vs error rates**:
```spl
service.name=payment-va OR service.name=payment-vb
| stats count by service.name, error
```

**Version B timing analysis**:
```spl
service.name=payment-vb
| stats avg(duration), min(duration), max(duration)
```

**Expected**:
- Min: ~4000ms
- Max: ~10000ms
- Avg: ~6500ms

**Token visibility in logs**:
```spl
index=logs service.name=payment-vb error=true
| rex field=message "(?<token>test-[a-f0-9-]+)"
| stats count by token
```

Should show: `test-20e26e90-356b-432e-a2c6-956fc03f5609`

---

## Summary

**Version A (Stable)**:
- [x] Gets token from secret
- [x] Calls Buttercup Payments
- [x] Succeeds (~100ms)
- [x] Production-ready

**Version B (Canary/Error)**:
- [x] Gets token from secret
- [x] Attempts to call Buttercup Payments 4 times
- [FAIL] Always fails (controlled error pod)
-  Total duration: 4-10 seconds (random)
-  First 3 attempts: 4-7.3 seconds (random)
-  Logs token in error messages
-  Perfect for error/retry testing
