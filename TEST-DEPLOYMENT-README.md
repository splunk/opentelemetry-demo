# Payment A/B Test Deployment

This directory contains minimal manifests for testing the Payment A/B and updated Checkout services.

## Files

- **test-payment-ab-deployment.yaml** - Kubernetes manifest for the three services
- **test-payment-ab.sh** - Helper script to manage the deployment

## Prerequisites

Before deploying, ensure you have:

1. **Existing OpenTelemetry Demo infrastructure:**
   - Namespace with `opentelemetry-demo` ServiceAccount
   - Flagd service running (for feature flags)
   - OpenTelemetry Collector DaemonSet
   - Dependent services: cart, currency, email, product-catalog, shipping, kafka

2. **Built container images:**
   - `ghcr.io/hagen-p/opentelemetry-demo-splunk/otel-checkout:test-1.7`
   - `ghcr.io/hagen-p/opentelemetry-demo-splunk/otel-payment:test-1.7-a`
   - `ghcr.io/hagen-p/opentelemetry-demo-splunk/otel-payment:test-1.7-b`

## Quick Start

### 1. Deploy the Services

```bash
./test-payment-ab.sh deploy
```

This will create:
- 2 Secrets (payment-va-secret, payment-vb-secret)
- 3 Services (payment-va, payment-vb, checkout)
- 3 Deployments (payment-va, payment-vb, checkout)

### 2. Check Status

```bash
./test-payment-ab.sh status
```

Output shows all resources and pod status.

### 3. Test Routing

```bash
./test-payment-ab.sh test
```

Verifies checkout can reach both payment services.

### 4. View Logs

```bash
./test-payment-ab.sh logs
```

Tail logs from all three services (Ctrl+C to stop).

## Testing Payment A/B Routing

The checkout service uses the `paymentFailure` feature flag to route between payment versions:

### Set the Flag in Flagd

Edit the flagd ConfigMap or use the flagd UI:

```bash
kubectl edit configmap flagd-config
```

Change the `paymentFailure` defaultVariant:

| Variant | Value | Behavior |
|---------|-------|----------|
| `off` | 0.0 | 100% → payment-va (stable) |
| `10%` | 0.1 | 10% → payment-vb, 90% → payment-va |
| `25%` | 0.25 | 25% → payment-vb, 75% → payment-va |
| `50%` | 0.5 | 50% → payment-vb, 50% → payment-va |
| `75%` | 0.75 | 75% → payment-vb, 25% → payment-va |
| `90%` | 0.95 | 95% → payment-vb, 5% → payment-va |
| `100%` | 1.0 | 100% → payment-vb (error pod) |

### Observe Behavior

**Payment Version A (Stable):**
- ✅ Succeeds immediately
- ⏱️ Response time: 0-200ms
- 🔑 Uses token: `prod-vA-a8cf28f9...`
- 📊 OTEL tag: `payment.variant=A`

**Payment Version B (Error Pod):**
- ❌ Always fails after 4 retry attempts
- ⏱️ Total duration: 4-10 seconds (random)
- ⏱️ First 3 attempts: 4-7.3 seconds
- 🔑 Uses token: `prod-vB-3f2e4d9c...`
- 📊 OTEL tag: `payment.variant=B`
- 📝 Logs token in error messages

## Testing Scenarios

### Scenario 1: All Traffic to Stable Version

```yaml
paymentFailure:
  defaultVariant: "off"  # 0.0
```

**Expected:**
- All payments succeed
- All go to payment-va
- Response time: ~100ms

### Scenario 2: 10% Canary Testing

```yaml
paymentFailure:
  defaultVariant: "10%"  # 0.1
```

**Expected:**
- 90% succeed (payment-va)
- 10% fail after 4-10 seconds (payment-vb)
- Can compare error behavior in Splunk APM

### Scenario 3: Full Error Mode

```yaml
paymentFailure:
  defaultVariant: "100%"  # 1.0
```

**Expected:**
- All payments fail
- All go to payment-vb
- 4 retry attempts per payment
- Total duration: 4-10 seconds
- Useful for testing error handling

## Observability

### View in Splunk APM

Filter by service name:
- `service.name=payment-va` - Stable version
- `service.name=payment-vb` - Error version
- `service.name=checkout` - Checkout service

Filter by variant:
- `payment.variant=A` - Version A
- `payment.variant=B` - Version B

### Example Queries

**Compare success vs error rates:**
```spl
service.name=payment-va OR service.name=payment-vb
| stats count by service.name, error
```

**Version B timing analysis:**
```spl
service.name=payment-vb
| stats avg(duration), min(duration), max(duration)
```

**Expected timing:**
- Min: ~4000ms (4 seconds)
- Max: ~10000ms (10 seconds)
- Avg: ~6500ms

## Updating After Rebuilding Images

If you rebuild the container images:

```bash
# Restart deployments to pull new images
./test-payment-ab.sh restart
```

This performs a rolling restart and waits for pods to be ready.

## Cleanup

To remove all test resources:

```bash
./test-payment-ab.sh delete
```

This deletes:
- Secrets
- Services
- Deployments
- Pods

## Troubleshooting

### Pods not starting

Check pod status:
```bash
kubectl describe pod -l app=payment
kubectl describe pod -l app.kubernetes.io/component=checkout
```

Common issues:
- Image pull errors (verify images exist in registry)
- Missing ServiceAccount
- Missing dependent services

### Can't reach payment services

Check service endpoints:
```bash
kubectl get endpoints payment-va payment-vb
```

Should show pod IPs. If empty, pods aren't ready.

### Feature flag not working

Verify flagd is running:
```bash
kubectl get pods -l app=flagd
kubectl get svc flagd
```

Check flagd configuration:
```bash
kubectl get configmap flagd-config -o yaml
```

## Manual Deployment

If you don't want to use the helper script:

```bash
# Deploy
kubectl apply -f test-payment-ab-deployment.yaml

# Check status
kubectl get all -l 'app in (payment),app.kubernetes.io/component in (checkout)'

# Delete
kubectl delete -f test-payment-ab-deployment.yaml
```

## Integration with Full Demo

This test deployment can run alongside the full OpenTelemetry Demo. The services use different names:

**Test deployment:**
- payment-va
- payment-vb
- checkout (from test)

**Full demo:**
- payment (original)
- checkout (original)

You can switch between them by updating service references or DNS.
