# Developing with Splunk OpenTelemetry Demo

This guide covers local development, testing, and building production artifacts for the Splunk OpenTelemetry Demo.

**For deployment instructions**, see [DEPLOYMENT.md](./DEPLOYMENT.md) which covers:
- Deploying to Kubernetes with Splunk Observability Cloud
- Configuring the Splunk OTel Collector
- Setting up secrets and credentials
- Demo-in-a-Box deployment
- Publishing packages to GitHub

## Table of Contents

- [Prerequisites](#prerequisites)
- [Fork Setup](#fork-setup)
- [Local Testing](#local-testing)
  - [Splunk Show Demo in a Box](#recommended-splunk-show-demo-in-a-box)
  - [Local k3d Cluster](#alternative-local-k3d-cluster)
  - [Local minikube](#alternative-local-kubernetes-minikube)
- [Building Services](#building-services)
  - [Individual Service Builds](#individual-service-builds)
  - [Multi-Platform Builds](#multi-platform-builds)
- [Building Production Manifests](#building-production-manifests)
  - [Standard Manifest](#standard-manifest)
  - [DIAB Variant](#diab-variant)
- [GitHub Actions Workflows](#github-actions-workflows)
  - [Test Workflows (Forks)](#test-workflows-forks)
  - [Production Workflows (Main Repo)](#production-workflows-main-repo)
- [Version Management](#version-management)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Tools

- **Git**: Version control
- **Docker**: Container runtime (v20.10+)
- **Python 3**: For build scripts (3.8+)
- **kubectl**: Kubernetes CLI

### For Local Development

- **k3d** (recommended): Lightweight Kubernetes in Docker
- **minikube** (alternative): Local Kubernetes cluster
- **Helm**: Package manager for Kubernetes (optional)

### For Demo in a Box Testing

- Access to **Splunk Show** for provisioning instances
- SSH access to provisioned instances

### For Building Multi-Platform Images

- **Docker Buildx**: Multi-platform build support
- **containerd**: Image store backend (for local multi-arch loading)

### Access Requirements

**For pushing images to registries:**
- GitHub account with write access to your fork
- GitHub Personal Access Token (PAT) with `write:packages` scope
- Logged into GitHub Container Registry: `docker login ghcr.io`

**For production builds (Splunk team only):**
- Write access to `splunk/opentelemetry-demo` repository
- Access to production GitHub environment secrets

## Fork Setup

### 1. Fork the Repository

Fork `splunk/opentelemetry-demo` to your personal GitHub account.

### 2. Clone Your Fork

```bash
git clone https://github.com/YOUR-USERNAME/opentelemetry-demo.git
cd opentelemetry-demo
```

### 3. Run Fork Setup Script

```bash
./setup-fork.sh
```

**This script:**
- Creates `dev-repo.yaml` with your GitHub username
- Configures git to exclude production version files
- Sets up your fork for test builds

**Generated `dev-repo.yaml`:**
```yaml
registry:
  dev: "ghcr.io/YOUR-USERNAME/opentelemetry-demo-splunk"
```

### 4. Configure Git Remote (Optional)

Add upstream remote to sync with main repository:

```bash
git remote add upstream https://github.com/splunk/opentelemetry-demo.git
```

## Local Testing

**Note:** This Splunk fork is Kubernetes-focused and does not use Docker Compose. The recommended testing approaches are:

1. **Splunk Show Demo in a Box instance** (recommended for full demo testing)
2. **Local k3d cluster** (recommended for development)
3. **Local minikube cluster** (alternative for development)

### Recommended: Splunk Show Demo in a Box

**Splunk Show Demo in a Box** provides a pre-configured environment with Splunk Observability Cloud integration.

#### Setup

1. **Provision a Demo in a Box instance** from Splunk Show

2. **Build your test images** (if testing code changes):
   ```bash
   # Use GitHub Actions TEST workflow to build images
   # Or build locally and push to your dev registry
   ```

3. **Generate DIAB manifest with your dev registry**:
   ```bash
   .github/scripts/stitch-manifests.sh dev diab
   ```

4. **Copy manifest to your Demo in a Box instance**:
   ```bash
   scp kubernetes/splunk-astronomy-shop-{version}-diab.yaml \
     user@your-diab-instance:/home/splunk/
   ```

5. **Deploy on the instance**:
   ```bash
   ssh user@your-diab-instance
   kubectl apply -f splunk-astronomy-shop-{version}-diab.yaml
   ```

6. **Access via Ingress**:
   - The DIAB manifest includes Ingress configuration
   - Access through the instance's external IP or hostname

### Alternative: Local k3d Cluster

**k3d** is a lightweight wrapper to run k3s in Docker, ideal for local development.

#### 1. Install k3d

```bash
# macOS
brew install k3d

# Linux
curl -s https://raw.githubusercontent.com/k3d-io/k3d/main/install.sh | bash
```

#### 2. Create Cluster

```bash
# Create cluster with port mappings
k3d cluster create astronomy-shop \
  --agents 2 \
  --port "8080:80@loadbalancer" \
  --port "8443:443@loadbalancer"

# Verify cluster
kubectl cluster-info
```

#### 3. Deploy Demo

Follow the standard Kubernetes deployment steps below.

### Alternative: Local Kubernetes (minikube)

#### 1. Install and Start minikube

```bash
# macOS
brew install minikube

# Start cluster
minikube start --cpus=8 --memory=16384
minikube addons enable ingress
```

### Standard Kubernetes Deployment Steps

Once you have a cluster running (k3d, minikube, or Demo in a Box), follow these steps:

#### 1. Create Namespace

```bash
kubectl create namespace astronomy-shop
kubectl config set-context --current --namespace=astronomy-shop
```

#### 2. Create Secrets

**Workshop Secret (required for Splunk-enhanced services):**
```bash
kubectl create secret generic workshop-secret \
  --from-literal=env=dev-local \
  --from-literal=appd_token=YOUR_APPD_TOKEN_IF_AVAILABLE
```

**Note:** If you don't have an AppDynamics token, that's fine. Services with `optional: true` in their secret references will start without it.

#### 3. Deploy Services

**Option A: Using pre-built manifest:**
```bash
kubectl apply -f kubernetes/splunk-astronomy-shop-1.7.1.yaml
```

**Option B: Build and deploy your own manifest:**
```bash
# Build test manifest (see Building Production Manifests section)
.github/scripts/stitch-manifests.sh dev

# Deploy
kubectl apply -f kubernetes/splunk-astronomy-shop-1.7.1.yaml
```

**Option C: Build and deploy DIAB manifest:**
```bash
# Build DIAB manifest with ingress
.github/scripts/stitch-manifests.sh dev diab

# Deploy
kubectl apply -f kubernetes/splunk-astronomy-shop-1.7.1-diab.yaml
```

#### 4. Access Services

**Port forward to access frontend:**
```bash
kubectl port-forward svc/frontend-proxy 8080:8080
```

**Access webstore:**
- Open browser: http://localhost:8080/

**For DIAB variant with Ingress:**

With k3d:
```bash
# Access via localhost (port mapping configured during cluster creation)
# http://localhost:8080/
```

With minikube:
```bash
# Get ingress IP
minikube ip

# Add to /etc/hosts
echo "$(minikube ip) astronomy-shop.local" | sudo tee -a /etc/hosts

# Access via ingress
# http://astronomy-shop.local/
```

With Demo in a Box:
```bash
# Access via instance hostname or IP
# http://<instance-ip>/
```

#### 5. Monitor Deployment

```bash
# Watch pods start
kubectl get pods -w

# Check service status
kubectl get svc

# View logs
kubectl logs -f deployment/frontend

# Describe pod for troubleshooting
kubectl describe pod <pod-name>
```

## Building Services

### Individual Service Builds

Each service has a build script in its directory: `src/{service}/build-{service}.sh`

#### Build Script Usage

```bash
cd src/ad
./build-ad.sh <version> [-cc]
```

**Parameters:**
- `<version>`: Version tag (e.g., `1.7.1`, `test`, `dev`)
- `-cc`: (Optional) Clean cache - repull all base images

**Example:**
```bash
# Build ad service with version 1.7.1
./build-ad.sh 1.7.1

# Build with clean cache
./build-ad.sh 1.7.1 -cc

# Build development version
./build-ad.sh dev
```

#### What the Script Does

1. **Validates inputs** - Checks version parameter
2. **Builds Docker image** - Uses service's Dockerfile
3. **Tags image** - `{registry}/otel-{service}:{version}`
4. **Pushes to registry** - Requires authentication

#### Registry Configuration

**Development (fork):**
- Registry from `dev-repo.yaml`: `ghcr.io/YOUR-USERNAME/opentelemetry-demo-splunk`
- Automatically used by build scripts

**Production (main repo):**
- Registry: `ghcr.io/splunk/opentelemetry-demo`
- Requires write access to Splunk organization

#### Building All Services

To build all buildable services:

```bash
# Get list of services with build: true
python3 .github/scripts/get-services.py --build

# Build each service
for service in $(python3 .github/scripts/get-services.py --build); do
    cd src/$service
    ./build-$service.sh 1.7.1
    cd ../..
done
```

### Multi-Platform Builds

For production releases, build images for multiple architectures (amd64, arm64).

#### Setup

1. **Enable containerd image store** (Docker Desktop Settings or Engine config)

2. **Create multi-platform builder:**
   ```bash
   make create-multiplatform-builder
   ```

   Or manually:
   ```bash
   docker buildx create --name multiplatform-builder \
     --driver docker-container \
     --config buildkitd.toml \
     --use
   ```

#### Build Commands

**Build locally (load into Docker):**
```bash
make build-multiplatform
```

**Build and push to registry:**
```bash
# Set registry in .env.override
echo "IMAGE_NAME=ghcr.io/YOUR-USERNAME/opentelemetry-demo-splunk" > .env.override

# Build and push
make build-multiplatform-and-push
```

**Manual multi-platform build:**
```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/YOUR-USERNAME/opentelemetry-demo-splunk/otel-frontend:1.7.1 \
  --push \
  -f src/frontend/Dockerfile .
```

## Building Production Manifests

The demo uses a "stitching" approach: individual service manifests are combined into a single deployment manifest.

### Standard Manifest

**Generate manifest with development registry:**
```bash
.github/scripts/stitch-manifests.sh dev
```

**Output:** `kubernetes/splunk-astronomy-shop-{version}.yaml`

**What it does:**
- Reads version from `SPLUNK-VERSION` file
- Reads services from `services.yaml` (those with `manifest: true`)
- Combines all `src/{service}/{service}-k8s.yaml` files
- Replaces image registries with dev registry
- Creates unified manifest

### DIAB Variant

**DIAB (Demo In A Box)** includes an Ingress resource for simplified access.

**Generate DIAB manifest:**
```bash
.github/scripts/stitch-manifests.sh dev diab
```

**Output:** `kubernetes/splunk-astronomy-shop-{version}-diab.yaml`

**Differences from standard:**
- Includes `src/ingress/ingress-k8s.yaml`
- Filename has `-diab` suffix
- Includes Traefik IngressClass configuration

### Manual Registry Replacement

If you need to manually change registries in a manifest:

```bash
# Replace registry in existing manifest
sed -i 's|ghcr.io/splunk/opentelemetry-demo|ghcr.io/YOUR-USERNAME/opentelemetry-demo-splunk|g' \
  kubernetes/splunk-astronomy-shop-1.7.1.yaml
```

### Adding Services to Manifests

1. **Edit `services.yaml`:**
   ```yaml
   services:
     - name: my-new-service
       manifest: true
       build: true
       replace_registry: true
   ```

2. **Create service manifest:**
   ```bash
   # Create src/my-new-service/my-new-service-k8s.yaml
   ```

3. **Rebuild manifest:**
   ```bash
   .github/scripts/stitch-manifests.sh dev
   ```

## GitHub Actions Workflows

### Test Workflows (Forks)

These workflows run **only in forks**, not in the main `splunk/opentelemetry-demo` repository.

#### Build Images - TEST

**Workflow:** `.github/workflows/test-build-images.yml`

**When to use:** Building custom service images for testing

**Steps:**
1. Go to your fork: `https://github.com/YOUR-USERNAME/opentelemetry-demo/actions`
2. Select: **"Build Images - TEST"**
3. Click: **"Run workflow"**
4. Configure:
   - **version**: `test` or `1.7.1-dev` (custom tag)
   - **services**: `all` or `frontend,cart,payment` (specific services)
   - **no_cache**: Disable build cache (checkbox)

**Output:**
- Images pushed to: `ghcr.io/YOUR-USERNAME/opentelemetry-demo-splunk/{service}:{version}`

#### Build Demo Manifest - TEST

**Workflow:** `.github/workflows/test-build-manifest.yml`

**When to use:** Testing manifest generation with dev registry

**Steps:**
1. Go to: Actions -> **"Build Demo Manifest - TEST"**
2. Click: **"Run workflow"**
3. Configure:
   - **test_version_suffix**: `-test` (or custom)
   - **commit_manifest**: Usually unchecked
   - **validate_manifest**: Usually checked

**Output:**
- File: `kubernetes/splunk-astronomy-shop-{version}-test.yaml`
- Artifact: Available for download (7-day retention)
- Registry: Dev registry images

### Production Workflows (Main Repo)

These workflows run **only in `splunk/opentelemetry-demo`**, not in forks.

#### Build Images - PRODUCTION

**Workflow:** `.github/workflows/prod-build-images.yml`

**When to use:** Creating official releases

**Steps:**
1. Go to: `https://github.com/splunk/opentelemetry-demo/actions`
2. Select: **"Build Images - PRODUCTION"**
3. Click: **"Run workflow"**
4. Configure:
   - **services**: `all` or specific services
   - **version_bump**: `none`, `patch`, `minor`, `major`

**What it does:**
- Builds specified services
- Optionally bumps `SPLUNK-VERSION`
- Updates service k8s manifests with new image tags
- Creates hotfix versions (e.g., `1.7.1-payment.1`) if no bump
- Creates Pull Request with changes

**Version Bumping:**
- `none`: Creates hotfix version for single service
- `patch`: 1.7.1 -> 1.7.2
- `minor`: 1.7.1 -> 1.8.0
- `major`: 1.7.1 -> 2.0.0

#### Build Demo Manifest - PRODUCTION

**Workflow:** `.github/workflows/prod-build-manifest.yml`

**When to use:** Creating official manifest after image builds

**Steps:**
1. Go to: Actions -> **"Build Demo Manifest - PRODUCTION"**
2. Click: **"Run workflow"**
3. Configure:
   - **version_bump**: `none`, `patch`, `minor`, `major`
   - **build_diab**: Build DIAB variant (checkbox)
   - **commit_manifest**: Commit to repository (checkbox)
   - **validate_manifest**: Validate YAML (checkbox)

**Output:**
- File: `kubernetes/splunk-astronomy-shop-{version}.yaml`
- Optional: `kubernetes/splunk-astronomy-shop-{version}-diab.yaml`
- Registry: Production registry images
- Artifact: 90-day retention
- Optional: Git commit with manifest

**See [PRODUCTION-WORKFLOW-GUIDE.md](./PRODUCTION-WORKFLOW-GUIDE.md) for detailed workflow scenarios.**

## Version Management

### Version File: `SPLUNK-VERSION`

This file contains the current version number:
```
1.7.1
```

### Hotfix Tracking: `.hotfix.yaml`

Tracks service-specific hotfix versions:
```yaml
hotfixes:
  payment: 1
  cart: 2
```

Results in image tags like `1.7.1-payment.1`, `1.7.1-cart.2`

### Version Bump Script

```bash
# Bump version manually
python3 .github/scripts/bump-version.py patch
python3 .github/scripts/bump-version.py minor
python3 .github/scripts/bump-version.py major
```

### Show Image Versions

```bash
# Show what version each service will use
python3 .github/scripts/show-image-versions.py
```

**Example output:**
```
Current SPLUNK-VERSION: 1.7.1

Service Image Versions:
accounting: 1.7.1 (current)
payment: 1.7.1-payment.1 (hotfix)
cart: 1.7.0 (older)
frontend: 1.7.1 (current)
```

## Testing

### Running Tests Locally

**Service-specific tests:**

Most services have their own test suites. Check each service's README:

```bash
# Frontend tests
cd src/frontend
npm test

# Payment tests
cd src/payment
npm test

# Java service tests (ad, fraud-detection, shop-dc-shim)
cd src/ad
./gradlew test
```

### Integration Testing

The main OpenTelemetry Demo repository has integration tests. These are not currently active in the Splunk fork but can be adapted.

### Validation

**Validate Kubernetes manifests:**
```bash
# Python validation
python3 -c "import yaml; yaml.safe_load_all(open('kubernetes/splunk-astronomy-shop-1.7.1.yaml'))"

# kubectl validation
kubectl apply --dry-run=client -f kubernetes/splunk-astronomy-shop-1.7.1.yaml
```

**Validate services.yaml:**
```bash
python3 .github/scripts/get-services.py --manifest
```

### Load Testing

**Cloud services:**
```bash
kubectl port-forward svc/load-generator 8089:8089

# Access Locust UI: http://localhost:8089
```

**Datacenter services (shop-dc-shim):**
```bash
cd src/shop-dc-loadgenerator
pip install -r requirements.txt

# Continuous load
python shop_load_generator.py --mode continuous --tpm 10 --duration 60

# Burst load
python shop_load_generator.py --mode burst --concurrent 20 --total 50
```

## Troubleshooting

### Docker Issues

**Docker daemon not running:**
```bash
# macOS/Windows: Open Docker Desktop
# Linux:
sudo systemctl start docker
```

**Build cache issues:**
```bash
docker system prune -a
# WARNING: Removes all unused Docker data
```

**Permission denied pushing to registry:**
```bash
# Login to GitHub Container Registry
echo $GITHUB_PAT | docker login ghcr.io -u YOUR-USERNAME --password-stdin
```

### Kubernetes Issues

**Pods in CrashLoopBackOff:**
```bash
# Check pod logs
kubectl logs <pod-name>

# Check events
kubectl get events --sort-by='.lastTimestamp'

# Describe pod
kubectl describe pod <pod-name>
```

**ImagePullBackOff:**
- Check registry URL is correct
- Verify image exists: `docker pull {image}`
- Check image pull secrets if using private registry

**Service not accessible:**
```bash
# Check service exists
kubectl get svc

# Check endpoints
kubectl get endpoints

# Port forward to service
kubectl port-forward svc/frontend-proxy 8080:8080
```

### Build Script Issues

**"No version provided":**
```bash
# Always provide version
./build-ad.sh 1.7.1
```

**"Permission denied" when pushing:**
- Login to registry: `docker login ghcr.io`
- Verify write access to registry
- Check token has `write:packages` scope

**Script can't find registry:**
- Ensure `dev-repo.yaml` exists (run `./setup-fork.sh`)
- Check `dev-repo.yaml` has correct registry URL

### Manifest Issues

**"Service manifest not found":**
- Ensure service has `{service}-k8s.yaml` file
- Check `services.yaml` has service listed with `manifest: true`

**Manifest validation failed:**
```bash
# Check YAML syntax
python3 -c "import yaml; yaml.safe_load_all(open('file.yaml'))"

# Check for common issues:
# - Missing --- separators
# - Incorrect indentation
# - Invalid resource types
```

**Registry not replaced:**
- Check `services.yaml` has correct registry URLs
- Verify service doesn't have `replace_registry: false`
- Try manual replacement with sed

### Workflow Issues

**Workflow doesn't appear in Actions:**
- **TEST workflows**: Only run in forks
- **PRODUCTION workflows**: Only run in main repo
- Check you're in the correct repository

**"Environment protection rules not met":**
- Verify running from `main` branch
- Check environment configuration in repository settings

**"Secret not found":**
- Verify secret name matches workflow expectations
- Check secret is in correct scope (environment vs. repository)
- For `GHCR_TOKEN`: See [ENVIRONMENT_SETUP.md](./ENVIRONMENT_SETUP.md)

## Best Practices

### Development Workflow

1. **Create feature branch:**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make changes and test locally:**
   ```bash
   # Build service
   cd src/frontend
   ./build-frontend.sh dev

   # Deploy to local k8s
   kubectl apply -f frontend-k8s.yaml
   ```

3. **Build test images:**
   - Push to dev registry using GitHub Actions TEST workflow

4. **Test complete deployment:**
   ```bash
   # Build manifest with dev images
   .github/scripts/stitch-manifests.sh dev

   # Deploy
   kubectl apply -f kubernetes/splunk-astronomy-shop-{version}.yaml
   ```

5. **Create pull request:**
   ```bash
   git push origin feature/my-feature
   # Create PR on GitHub
   ```

### Production Release Workflow

1. **Build all images:**
   - Run **Build Images - PRODUCTION** workflow with `version_bump: minor`
   - Review and merge PR

2. **Build production manifest:**
   - Run **Build Demo Manifest - PRODUCTION** workflow with `version_bump: none`
   - Review and merge PR

3. **Tag release:**
   - Create GitHub release with version tag
   - Include CHANGELOG updates

## Additional Resources

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- [PRODUCTION-WORKFLOW-GUIDE.md](./PRODUCTION-WORKFLOW-GUIDE.md) - Detailed production workflows
- [WORKFLOWS.md](./WORKFLOWS.md) - GitHub Actions reference
- [SPLUNK-BUILD.md](./SPLUNK-BUILD.md) - Service build instructions
- [CONTRIBUTING.md](./CONTRIBUTING.md) - Contribution guidelines
- [OpenTelemetry Demo Docs](https://opentelemetry.io/docs/demo/) - Upstream documentation
