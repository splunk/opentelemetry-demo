# Payment Service A/B Routing with Feature Flags

## Overview

The `paymentFailure` feature flag now controls **routing** between payment service versions A and B, not internal failure simulation. This allows real A/B testing to compare performance characteristics between the two versions.

---

## How It Works

### Routing Logic (Checkout Service)

The checkout service reads the `paymentFailure` flag value (0.0 to 1.0) and uses it as a probability to route to version B:

```go
// src/checkout/main.go
paymentFailureProbability := cs.getFeatureFlagFloat(ctx, "paymentFailure", 0.0)
shouldRouteToB := rand.Float64() < paymentFailureProbability

if shouldRouteToB {
    paymentAddr = "payment-vb:8080"  // Route to version B
} else {
    paymentAddr = "payment-va:8080"  // Route to version A
}
```

### Flag Values

| Flag Value | Behavior | Version A % | Version B % |
|------------|----------|-------------|-------------|
| **0** (`all-A`) | All traffic to version A | 100% | 0% |
| **0.1** (`mostly-A`) | Mostly version A | 90% | 10% |
| **0.5** (`balanced`) | Split evenly | 50% | 50% |
| **0.9** (`mostly-B`) | Mostly version B | 10% | 90% |
| **1** (`all-B`) | All traffic to version B | 0% | 100% |

### Payment Service Behavior

Both payment versions **always succeed** (unless real errors occur). They do NOT simulate failures based on the flag. Instead, they differ in:

- **Retry strategy**: A uses exponential, B uses exponential + jitter
- **Retry count**: A retries 4 times, B retries 6 times
- **Speed**: B is 2x faster (100ms vs 200ms success delay)
- **Resource attributes**: Different OTEL tags for filtering

---

## Configuration

### Feature Flag (flagd-config-k8s.yaml)

```yaml
"paymentFailure": {
  "description": "Route payment requests to version A or B (0=all A, 0.5=50/50, 1=all B)",
  "state": "ENABLED",
  "variants": {
    "all-B": 1,
    "mostly-B": 0.9,
    "balanced": 0.5,
    "mostly-A": 0.1,
    "all-A": 0
  },
  "defaultVariant": "all-A"
}
```

**Default**: All traffic goes to version A (`all-A` = 0)

---

## Testing Scenarios

### Scenario 1: Compare Performance (Version A vs B)

**Objective**: See if version B is faster than version A

**Steps**:
1. Set flag to `all-A` (0)
2. Generate 100 orders
3. Observe metrics in Splunk:
   - Filter: `service.name=payment-va`
   - Average latency: ~150ms
4. Set flag to `all-B` (1)
5. Generate 100 orders
6. Observe metrics in Splunk:
   - Filter: `service.name=payment-vb`
   - Average latency: ~75ms (2x faster!)

### Scenario 2: Canary Deployment (10% to new version)

**Objective**: Test version B with small traffic before full rollout

**Steps**:
1. Set flag to `mostly-A` (0.1)
   - 90% traffic -> version A
   - 10% traffic -> version B
2. Monitor error rates for both versions
3. If B looks good, increase to `balanced` (0.5)
4. Eventually move to `all-B` (1)

### Scenario 3: A/B Test with Load Generator

**Objective**: Compare both versions under load

**Steps**:
1. Set flag to `balanced` (0.5)
2. Run load generator for 10 minutes
3. View in Splunk APM:
   ```
   service.name=payment-va OR service.name=payment-vb
   | stats avg(duration) by service.name
   ```
4. Compare:
   - Latency percentiles (p50, p95, p99)
   - Error rates
   - Retry behavior

---

## Expected Results

### Version A (Stable/Conservative)

**Service Name**: `payment-va`

**Characteristics**:
- Retry max: 4
- Retry strategy: Exponential
- Success delay: 0-200ms
- Timeout: 5000ms
- Log level: info
- OTEL tags:
  - `payment.variant=A`
  - `deployment.stability=stable`
  - `service.version=1.7.0-a`

**Use Case**: Production-stable baseline

### Version B (Optimized/Fast)

**Service Name**: `payment-vb`

**Characteristics**:
- Retry max: 6 (more retries)
- Retry strategy: Exponential + Jitter
- Success delay: 0-100ms (2x faster!)
- Timeout: 3000ms (stricter)
- Log level: debug (more verbose)
- OTEL tags:
  - `payment.variant=B`
  - `deployment.stability=canary`
  - `service.version=1.7.0-b`

**Use Case**: Testing optimizations

---

## Observability Queries

### Splunk APM - Compare Latency

```spl
index=apm service.name=payment-va OR service.name=payment-vb
| stats avg(duration) as avg_ms, p95(duration) as p95_ms by service.name
```

**Expected**:
- `payment-va`: avg_ms=150, p95_ms=200
- `payment-vb`: avg_ms=75, p95_ms=100

### Splunk APM - Traffic Distribution

```spl
index=apm service.name=payment-va OR service.name=payment-vb
| stats count by service.name
```

**With `balanced` (0.5)**:
- `payment-va`: count ~500
- `payment-vb`: count ~500

### Filter by Variant

```spl
payment.variant=A
payment.variant=B
deployment.stability=stable
deployment.stability=canary
```

---

## Deployment Requirements

### Build Both Versions

```bash
cd src/payment
./build-payment-versions.sh 1.7.1
```

**Creates**:
- `otel-payment:1.7.1-a`
- `otel-payment:1.7.1-b`

### Deploy Both Services

```bash
# Update image tags in manifests to match your build version
kubectl apply -f src/payment/payment-vA-k8s.yaml
kubectl apply -f src/payment/payment-vB-k8s.yaml
```

### Rebuild Checkout (Required!)

**Important**: The checkout service code has changed to implement routing logic. You must rebuild it:

```bash
# If using GitHub Actions
# Services: checkout
# Version: 1.7.1

# Or locally (if you have checkout build configured)
```

---

## Switching Between Versions

### Via Feature Flag (Recommended)

Use the flagd UI or kubectl:

```bash
# Route 100% to version A
kubectl patch configmap flagd-config --patch '{
  "data": {
    "demo.flagd.json": "...\"defaultVariant\": \"all-A\"..."
  }
}'

# Route 100% to version B
kubectl patch configmap flagd-config --patch '{
  "data": {
    "demo.flagd.json": "...\"defaultVariant\": \"all-B\"..."
  }
}'

# Route 50/50
kubectl patch configmap flagd-config --patch '{
  "data": {
    "demo.flagd.json": "...\"defaultVariant\": \"balanced\"..."
  }
}'
```

---

## Troubleshooting

### All traffic going to version A even with flag set to `all-B`

**Check**:
1. Checkout service has been rebuilt with new routing code
2. Flagd is running and checkout can connect to it
3. Flag value is actually updated: `kubectl logs flagd-xxx | grep paymentFailure`

### Payment service logging failures

**Note**: Payment services no longer simulate failures based on the flag. If you see failures:
- Check for real errors (network, resource limits, etc.)
- Version B has stricter timeout (3s vs 5s) - may timeout faster

### Can't tell which version was used

**Solution**: Check OTEL attributes in traces:
- `service.name`: `payment-va` or `payment-vb`
- `payment.variant`: `A` or `B`
- `deployment.stability`: `stable` or `canary`

---

## Summary

[x] **`paymentFailure` flag** -> Controls routing percentage to version B
[x] **Version A** -> Stable, slower, conservative (default)
[x] **Version B** -> Optimized, faster, more retries
[x] **Both versions** -> Always succeed (no simulated failures)
[x] **Checkout service** -> Routes probabilistically based on flag
[x] **Easy A/B testing** -> Just change flag value in flagd

**Next**: Build payment A/B, rebuild checkout, deploy both, and control routing with the feature flag!
