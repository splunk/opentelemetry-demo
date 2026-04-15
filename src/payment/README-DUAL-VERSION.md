# Payment Service Dual-Version Implementation

## Overview

This implementation deploys **two distinct container images** (vA and vB) from a **single codebase**, allowing real A/B testing of payment service versions with different performance characteristics. Each version runs on **separate nodes** with **separate secrets**, making it ideal for AI/ML observability analysis.

---

## Architecture

```
+-------------------------------------+
|      Checkout Service               |
|  PAYMENT_ADDR env var controls      |
|  which version to use:              |
|  - payment-va:8080 (version A)      |
|  - payment-vb:8080 (version B)      |
+-------------------------------------+
                |
    +-----------+-----------+
    |                       |
    v                       v
+---------+           +---------+
| vA Pod  |           | vB Pod  |
| Node 1  |           | Node 2  |
| Secret A|           | Secret B|
+---------+           +---------+
```

---

## Key Features

### 1. **Single Codebase, Two Container Images**
- **Same code**: `src/payment/charge.js`, `index.js`, `logger.js`, etc.
- **Different configs**: `config/vA-config.js` vs `config/vB-config.js`
- **Build-time differentiation**: `docker build --build-arg VERSION=A` vs `VERSION=B`
- **Result**: Two distinct images with different SHAs for AI observability

### 2. **Version-Specific Configurations**

| Feature | Version A (Stable) | Version B (Optimized) |
|---------|-------------------|----------------------|
| **Container** | `otel-payment:1.7.0-a` | `otel-payment:1.7.0-b` |
| **Secret** | `payment-va-secret` | `payment-vb-secret` |
| **Token** | `prod-vA-a8cf28f9...` | `prod-vB-3f2e4d9c...` |
| **Retry Max** | 4 (default) | 6 (more retries) |
| **Retry Strategy** | Exponential | Exponential + Jitter |
| **Success Delay** | 0-200ms | 0-100ms (faster) |
| **Failure Delay** | 0-1000ms | 0-500ms (faster) |
| **Target Failure Time** | 5 seconds | 4 seconds |
| **Timeout** | 5000ms | 3000ms |
| **Log Level** | info | debug |
| **OTEL Attributes** | `payment.variant=A`<br>`deployment.stability=stable` | `payment.variant=B`<br>`deployment.stability=canary` |

### 3. **Uses Feature Flag for A/B Routing**

The **`paymentFailure`** flag controls routing between versions A and B:

- **`paymentFailure`** (number 0.0-1.0): Controls % of traffic to version B
  - **0** (`all-A`): 100% traffic to version A
  - **0.1** (`mostly-A`): 90% to A, 10% to B
  - **0.5** (`balanced`): 50% to A, 50% to B
  - **0.9** (`mostly-B`): 10% to A, 90% to B
  - **1** (`all-B`): 100% traffic to version B
  - **Default**: `all-A` (all traffic to version A)

**How it works**:
- Checkout service reads the flag value
- Uses it as probability to route to version B
- If `random() < paymentFailure`: route to `payment-vb:8080`
- Else: route to `payment-va:8080`

**Other flags**:
- **`paymentRetryMax`** (number): Maximum retry attempts (can be overridden, default from version config)
- **`paymentUnreachable`** (boolean): Checkout routes to bad address (for testing failures)

### 4. **Node Isolation**

Each version has **pod anti-affinity** to ensure they run on **different nodes**:

```yaml
podAntiAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
  - labelSelector:
      matchLabels:
        app: payment
        version: vB  # vA pods avoid vB pods
    topologyKey: kubernetes.io/hostname
```

This creates **distinct host metadata** in traces for AI correlation.

---

## File Structure

```
src/payment/
|-- config/
|   |-- version-config.js    # Loader - reads PAYMENT_VERSION env var
|   |-- vA-config.js          # Version A configuration
|   +-- vB-config.js          # Version B configuration
|-- charge.js                 # [x] Updated to use versionConfig
|-- index.js                  # Shared
|-- logger.js                 # Shared
|-- opentelemetry.js          # Shared
|-- package.json              # Shared
|-- Dockerfile                # [x] Updated with VERSION build arg
|-- build-payment-versions.sh # [x] New - builds both images
|-- payment-vA-k8s.yaml       # [x] New - deploys version A
|-- payment-vB-k8s.yaml       # [x] New - deploys version B
+-- README-DUAL-VERSION.md    # This file
```

---

## How to Build

### Option 1: GitHub Actions (Recommended for Production)

The GitHub Actions workflow automatically builds both A and B versions when you trigger a build for the payment service.

**Example**: Build payment service version 1.7.1:

1. Go to GitHub Actions -> **Build Images - PRODUCTION**
2. Click **Run workflow**
3. Configure:
   - **Version bump**: `custom`
   - **Custom version**: `1.7.1`
   - **Services**: `payment`
4. Click **Run workflow**

**Result**:
- [x] `ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a` (Version A)
- [x] `ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b` (Version B)

Both images are built in parallel from the same codebase with different build args (`VERSION=A` and `VERSION=B`).

**How it works:**
- The workflow detects when `payment` service is requested
- Automatically expands into TWO matrix entries:
  - `payment` + `variant: A` + `build_args: VERSION=A` -> tags with `-a` suffix
  - `payment` + `variant: B` + `build_args: VERSION=B` -> tags with `-b` suffix
- Builds both in parallel on GitHub's infrastructure
- Pushes to `ghcr.io/splunk/opentelemetry-demo`

### Option 2: Local Build

For local testing and development:

```bash
cd src/payment

# Build with default version (from SPLUNK-VERSION file or 1.7.0)
./build-payment-versions.sh

# Build with specific version
./build-payment-versions.sh 1.7.1

# Build and push to registry
./build-payment-versions.sh 1.7.1 push
```

This creates:
- `ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a`
- `ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b`

### Inspect Version Metadata

```bash
# Check version A metadata
docker run --rm ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a cat /app/version.json

# Check version B metadata
docker run --rm ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b cat /app/version.json
```

Output example:
```json
{
  "version": "vA",
  "buildTime": "2026-03-05T10:30:00Z",
  "nodeVersion": "v22.x.x",
  "imageVariant": "A"
}
```

---

## How to Deploy

### Step 1: Build Payment Versions

```bash
cd src/payment
./build-payment-versions.sh 1.7.1
```

### Step 2: Build Checkout (REQUIRED!)

**Important**: The checkout service has been modified to route based on the `paymentFailure` flag. You must rebuild it:

```bash
# Via GitHub Actions
# Go to: Actions -> Build Images - PRODUCTION
# Services: checkout
# Version: 1.7.1

# This will build the updated checkout with routing logic
```

### Step 3: Deploy Both Payment Versions

```bash
# Update image tags in manifests to match your build version
kubectl apply -f src/payment/payment-vA-k8s.yaml
kubectl apply -f src/payment/payment-vB-k8s.yaml
```

This creates:
- **Secrets**: `payment-va-secret`, `payment-vb-secret`
- **Deployments**: `payment-va` (2 replicas), `payment-vb` (2 replicas)
- **Services**: `payment-va:8080`, `payment-vb:8080`

### Step 4: Deploy Updated Checkout

```bash
# Deploy the rebuilt checkout service
kubectl set image deployment/checkout checkout=ghcr.io/splunk/opentelemetry-demo/otel-checkout:1.7.1
```

### Step 5: Control Routing with Feature Flag

The `paymentFailure` flag now controls routing:

```bash
# Route all traffic to version A (default)
# Flag value: all-A (0)

# Route all traffic to version B
# Change flag to: all-B (1)

# Route 50/50
# Change flag to: balanced (0.5)
```

Use the flagd UI or kubectl to change the flag variant.

### Verify Deployment

```bash
# Check pods
kubectl get pods -l app=payment

# Check which nodes they're on (should be different)
kubectl get pods -l app=payment -o wide

# Check services
kubectl get svc -l app=payment

# Check secrets
kubectl get secrets | grep payment-v

# View version A logs
kubectl logs -l version=vA -f

# View version B logs
kubectl logs -l version=vB -f
```

---

## How Version Configuration Works

### 1. **Build Time**
```bash
docker build --build-arg VERSION=A
```
- Sets `ENV PAYMENT_VERSION=vA` in container
- Creates `version.json` with build metadata
- Adds image labels for tracking

### 2. **Runtime**
```javascript
// config/version-config.js
const PAYMENT_VERSION = process.env.PAYMENT_VERSION || 'vA';
const config = versionConfigs[PAYMENT_VERSION];  // Loads vA-config.js or vB-config.js
```

### 3. **In Code**
```javascript
// charge.js
const versionConfig = require('./config/version-config');

// Use version-specific settings
const RETRY_MAX = versionConfig.retryMaxDefault;  // 4 for vA, 6 for vB
const apiToken = versionConfig.apiToken;           // Different tokens
```

---

## Observability Benefits for AI/ML

### 1. **Distinct Container Images**
- **Image SHA**: Different digest for correlation
- **Image Tags**: `1.7.0-a` vs `1.7.0-b`
- **SBOM**: Separate software bills of materials
- **Vulnerability Scans**: Per-image results

### 2. **OTEL Resource Attributes**
```javascript
// Version A
{
  'service.name': 'payment-va',
  'service.version': '1.7.0-a',
  'payment.variant': 'A',
  'deployment.stability': 'stable',
  'payment.api.version': 'v1'
}

// Version B
{
  'service.name': 'payment-vb',
  'service.version': '1.7.0-b',
  'payment.variant': 'B',
  'deployment.stability': 'canary',
  'payment.api.version': 'v2'
}
```

### 3. **Splunk APM Queries**

Filter by version:
```
service.name=payment-va OR service.name=payment-vb
payment.variant=A
deployment.stability=canary
```

Compare error rates:
```
service.name=payment-va | timechart count by error
service.name=payment-vb | timechart count by error
```

### 4. **AI Pattern Detection**

AI can detect:
- **Performance differences**: vB is 2x faster on success (100ms vs 200ms)
- **Retry behavior**: vB retries more (6 vs 4)
- **Error patterns**: Different tokens create different error signatures
- **Node correlation**: Different host metadata per version
- **Timing patterns**: vB uses jitter, vA doesn't

---

## Testing Scenarios

### Scenario 1: Compare Success Performance

```bash
# Set paymentFailure to off
kubectl patch configmap flagd-config --patch '{"data":{"demo.flagd.json":"...\"paymentFailure\":{\"defaultVariant\":\"off\"}..."}}'

# Send traffic to vA
curl -X POST checkout-with-va/checkout

# Send traffic to vB
curl -X POST checkout-with-vb/checkout

# Compare in Splunk APM:
# - vA: avg 100ms response time
# - vB: avg 50ms response time (faster!)
```

### Scenario 2: Compare Failure Handling

```bash
# Set paymentFailure to 50%
# Default is already 50%

# Observe in Splunk:
# - vA: 4 retries, ~5 second total failure time
# - vB: 6 retries, ~4 second total failure time
```

### Scenario 3: Token-Based Error Analysis

```bash
# Check logs for different tokens
kubectl logs -l version=vA | grep "prod-vA"
kubectl logs -l version=vB | grep "prod-vB"

# AI can correlate token patterns to errors
```

---

## Migration Path

### Phase 1: Deploy Both Versions
```bash
kubectl apply -f payment-vA-k8s.yaml
kubectl apply -f payment-vB-k8s.yaml
```

### Phase 2: Test vB with Small Traffic
```bash
# Update 10% of checkout pods to use vB
kubectl scale deployment checkout --replicas=10
# Manually edit 1 pod to use PAYMENT_ADDR=payment-vb:8080
```

### Phase 3: Monitor and Compare
- Check Splunk APM for error rates
- Compare latency percentiles
- Review logs for anomalies

### Phase 4: Full Rollout
```bash
# Update all checkout pods to use vB
kubectl set env deployment/checkout PAYMENT_ADDR=payment-vb:8080
```

### Phase 5: Deprecate vA
```bash
kubectl delete -f payment-vA-k8s.yaml
```

---

## Troubleshooting

### Pods on Same Node

```bash
# Check node distribution
kubectl get pods -l app=payment -o wide

# If on same node, check anti-affinity
kubectl describe pod payment-va-xxx | grep -A 10 Affinity
```

### Version Not Loading

```bash
# Check environment variable
kubectl exec payment-va-xxx -- env | grep PAYMENT_VERSION

# Check version file in container
kubectl exec payment-va-xxx -- cat /app/version.json
```

### Wrong Token Being Used

```bash
# Check secret
kubectl get secret payment-va-secret -o jsonpath='{.data.api-token}' | base64 -d

# Check logs
kubectl logs payment-va-xxx | grep "apiToken"
```

### Feature Flags Not Working

```bash
# Check flagd connection
kubectl logs payment-va-xxx | grep flagd

# Check flag values
kubectl exec flagd-xxx -- cat /etc/flagd/demo.flagd.json | grep paymentFailure
```

---

## Summary

[x] **Single codebase** with version-specific configs
[x] **Two distinct containers** for AI image correlation
[x] **Separate secrets** per version
[x] **Node anti-affinity** for different host metadata
[x] **Reuses existing feature flags** (no new flags needed)
[x] **Easy A/B testing** via PAYMENT_ADDR env var
[x] **Performance differences** built-in (vB is faster)
[x] **Perfect for AI/ML observability** analysis

**Next Steps**: Build images and deploy!
