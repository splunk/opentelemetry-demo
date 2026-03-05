# Payment Service A/B Build Integration

## Overview

The GitHub Actions CI/CD pipeline has been enhanced to automatically build **two distinct container images** (Version A and Version B) whenever the payment service is built. This enables real A/B testing with different performance characteristics from a single codebase.

---

## What Changed

### Modified Workflows

**File**: `.github/workflows/prod-build-images.yml`

**Changes**:
1. **Matrix Generation** - Detects `payment` service and expands into TWO build jobs
2. **Version Tagging** - Adds `-a` and `-b` suffixes to version tags
3. **Build Args** - Passes `VERSION=A` or `VERSION=B` to Docker build

### Key Code Changes

#### 1. Matrix Generation (lines 234-260)

```python
# Special handling for payment service - build A and B versions
if name == 'payment':
    # Build version A
    services_to_build.append({
        'name': name,
        'variant': 'A',
        'platform': platform,
        'dockerfile': dockerfile,
        'build_args': 'VERSION=A'
    })
    # Build version B
    services_to_build.append({
        'name': name,
        'variant': 'B',
        'platform': platform,
        'dockerfile': dockerfile,
        'build_args': 'VERSION=B'
    })
else:
    # Normal service - single build
    services_to_build.append({
        'name': name,
        'variant': '',
        'platform': platform,
        'dockerfile': dockerfile,
        'build_args': ''
    })
```

#### 2. Image Tagging (lines 332-361)

```bash
# Add variant suffix to version tag if this is a variant build (payment A/B)
if [ -n "$VARIANT" ]; then
  VARIANT_LOWER=$(echo "$VARIANT" | tr '[:upper:]' '[:lower:]')
  VERSION_TAG="${VERSION}-${VARIANT_LOWER}"
else
  VERSION_TAG="${VERSION}"
fi

FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${VERSION_TAG}"
```

#### 3. Build Args (line 384)

```yaml
- name: Build and push image
  uses: docker/build-push-action@v5
  with:
    context: .
    file: ${{ matrix.dockerfile }}
    platforms: ${{ matrix.platform }}
    push: true
    tags: ${{ steps.image.outputs.full_image }}
    build-args: ${{ matrix.build_args }}  # ← NEW: Passes VERSION=A or VERSION=B
    cache-from: type=gha
    cache-to: type=gha,mode=max
```

---

## Usage Examples

### Example 1: Build Payment Service with Version 1.7.1

**GitHub Actions UI**:
1. Navigate to: **Actions** → **Build Images - PRODUCTION**
2. Click **Run workflow**
3. Set:
   - **Version bump**: `custom`
   - **Custom version**: `1.7.1`
   - **Services**: `payment`
4. Click **Run workflow**

**Result**:
```
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b
```

**Build Matrix**:
```json
{
  "include": [
    {
      "name": "payment",
      "variant": "A",
      "platform": "linux/amd64,linux/arm64",
      "dockerfile": "src/payment/Dockerfile",
      "build_args": "VERSION=A"
    },
    {
      "name": "payment",
      "variant": "B",
      "platform": "linux/amd64,linux/arm64",
      "dockerfile": "src/payment/Dockerfile",
      "build_args": "VERSION=B"
    }
  ]
}
```

### Example 2: Full Release Build (All Services)

**GitHub Actions UI**:
1. Navigate to: **Actions** → **Build Images - PRODUCTION**
2. Click **Run workflow**
3. Set:
   - **Version bump**: `minor` (e.g., 1.6.0 → 1.7.0)
   - **Services**: `all`
4. Click **Run workflow**

**Result for Payment**:
```
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.0-a
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.0-b
```

**Result for Other Services** (e.g., ad, accounting, etc.):
```
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-ad:1.7.0
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-accounting:1.7.0
... (single image each)
```

### Example 3: Build Multiple Services Including Payment

**GitHub Actions UI**:
- **Services**: `payment,ad,frontend`

**Result**:
```
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.0-a
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.0-b
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-ad:1.7.0
✅ Built: ghcr.io/splunk/opentelemetry-demo/otel-frontend:1.7.0
```

---

## How It Works

### 1. Workflow Triggered
User triggers workflow with:
- **Version**: `1.7.1` (custom)
- **Services**: `payment`

### 2. Matrix Generation
Python script in workflow reads `services.yaml`:
```yaml
- name: payment
  build: true
  manifest: true
```

Detects `payment` and creates TWO matrix entries:
```json
[
  {"name": "payment", "variant": "A", "build_args": "VERSION=A"},
  {"name": "payment", "variant": "B", "build_args": "VERSION=B"}
]
```

### 3. Parallel Builds
GitHub Actions runs TWO build jobs in parallel:

**Job 1: Payment A**
```bash
docker build \
  --build-arg VERSION=A \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a \
  -f src/payment/Dockerfile \
  .
```

**Job 2: Payment B**
```bash
docker build \
  --build-arg VERSION=B \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b \
  -f src/payment/Dockerfile \
  .
```

### 4. Dockerfile Receives Build Arg
```dockerfile
# Dockerfile (src/payment/Dockerfile)
ARG VERSION=A
ENV PAYMENT_VERSION=v${VERSION}

# Creates version.json with build metadata
RUN echo "{ \
  \"version\": \"${PAYMENT_VERSION}\", \
  \"buildTime\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\", \
  \"nodeVersion\": \"$(node --version)\", \
  \"imageVariant\": \"${VERSION}\" \
}" > /app/version.json
```

### 5. Version Config Loaded at Runtime
```javascript
// config/version-config.js
const PAYMENT_VERSION = process.env.PAYMENT_VERSION || 'vA';
const config = versionConfigs[PAYMENT_VERSION];  // Loads vA-config.js or vB-config.js
```

### 6. Images Pushed to Registry
```
ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a  (SHA: abc123...)
ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b  (SHA: def456...)
```

---

## Verification

### Check Build Logs in GitHub Actions

1. Go to **Actions** tab
2. Click on the workflow run
3. Expand **build-images** job
4. Look for matrix strategy output:

```
Matrix: Includes 2 configurations
  payment (variant A)
  payment (variant B)
```

### Check Registry

```bash
# List images in registry
docker pull ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a
docker pull ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b

# Inspect metadata
docker run --rm ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a cat /app/version.json
docker run --rm ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b cat /app/version.json
```

### Check Image SHAs (Different!)

```bash
docker inspect ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a --format='{{.Id}}'
# Output: sha256:abc123...

docker inspect ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b --format='{{.Id}}'
# Output: sha256:def456... (DIFFERENT!)
```

---

## Impact on Other Services

**No impact** - All other services build normally with a single image:

```yaml
# services.yaml
- name: ad
  build: true
  manifest: true
```

**Result**: `ghcr.io/splunk/opentelemetry-demo/otel-ad:1.7.1` (single image)

Only `payment` service is special-cased in the workflow logic.

---

## Local Testing

For local development, use the build script:

```bash
cd src/payment

# Build with version 1.7.1
./build-payment-versions.sh 1.7.1

# Result:
#   otel-payment:1.7.1-a
#   otel-payment:1.7.1-b
```

---

## Troubleshooting

### Images not appearing with -a/-b suffixes

**Check**: Ensure the payment service was actually requested:
```yaml
inputs:
  services: "payment"  # ✅ Correct
  # OR
  services: "all"      # ✅ Includes payment
```

### Both images have the same SHA

**Cause**: Build args not being passed
**Fix**: Check line 384 in `prod-build-images.yml`:
```yaml
build-args: ${{ matrix.build_args }}  # Should be present
```

### Only one payment image built

**Cause**: Matrix generation didn't expand payment
**Fix**: Check lines 234-260 in workflow for payment detection logic

---

## Benefits

✅ **Automatic**: No manual steps needed - just trigger workflow with `payment` in services list
✅ **Consistent**: Same process as other services, just expanded matrix
✅ **Parallel**: Both versions build simultaneously on GitHub infrastructure
✅ **Distinct SHAs**: Different container digests for AI/ML correlation
✅ **Version-aware**: Tags include `-a` and `-b` suffixes automatically
✅ **Scalable**: Easy to add more variants in the future

---

## Future Enhancements

- Add variant C, D, etc. by expanding the matrix logic
- Support variant-specific platforms (e.g., A=amd64 only, B=arm64 only)
- Add variant-specific build flags/optimizations
- Create separate caches per variant for faster builds

---

## Summary

**Before**:
```
payment service → ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1
```

**After**:
```
payment service → ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-a (Version A)
                → ghcr.io/splunk/opentelemetry-demo/otel-payment:1.7.1-b (Version B)
```

**How to use**:
1. Trigger GitHub Actions workflow
2. Set services to `payment` (or `all`)
3. Specify version (e.g., `1.7.1`)
4. Two images built automatically with `-a` and `-b` suffixes
