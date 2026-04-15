# Deploying Splunk OpenTelemetry Demo

This guide covers deploying the Splunk OpenTelemetry Astronomy Shop Demo to Kubernetes environments with Splunk Observability Cloud integration.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Splunk Observability Cloud Setup](#splunk-observability-cloud-setup)
- [Deploying Splunk Observability Collector](#deploying-splunk-observability-collector)
- [Configuring Secrets](#configuring-secrets)
- [Deploying the Astronomy Shop](#deploying-the-astronomy-shop)
  - [Standard Kubernetes Deployment](#standard-kubernetes-deployment)
  - [Demo-in-a-Box Deployment](#demo-in-a-box-deployment)
- [Configuring Ingress](#configuring-ingress)
- [Verifying the Deployment](#verifying-the-deployment)
- [Publishing Packages to GitHub](#publishing-packages-to-github)
- [Updating the Deployment](#updating-the-deployment)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### Kubernetes Cluster

You need access to a Kubernetes cluster. Options include:
- **k3s/k3d** - Lightweight Kubernetes for local/edge deployments
- **minikube** - Local Kubernetes for development
- **Cloud providers** - EKS, GKE, AKS for production-like environments
- **Splunk Show Demo-in-a-Box** - Pre-configured demo environment

**Minimum requirements:**
- 8 CPU cores
- 16 GB RAM
- 50 GB disk space
- Kubernetes 1.24+

**Recommended:**
- 16 CPU cores
- 32 GB RAM
- 100 GB disk space

### Splunk Observability Cloud Account

You need a Splunk Observability Cloud account with:
- **Access Token** - For sending telemetry data
- **API Token** - For API operations
- **RUM Token** - For Real User Monitoring (frontend)
- **Realm** - Your Splunk O11y Cloud realm (e.g., `us0`, `us1`, `eu0`)

**How to obtain:**
1. Log into Splunk Observability Cloud
2. Navigate to **Settings** -> **Access Tokens**
3. Create tokens with appropriate permissions

### Splunk Cloud Platform (Optional)

For log ingestion via HEC:
- **Splunk Cloud instance** - Your Splunk Cloud URL
- **HEC Token** - HTTP Event Collector token
- **Index** - Target index for logs (e.g., `main`, `workshop`)

**How to obtain:**
1. Log into Splunk Cloud
2. Navigate to **Settings** -> **Data Inputs** -> **HTTP Event Collector**
3. Create new token
4. Note the token value and HEC endpoint URL

### Tools

- `kubectl` - Kubernetes CLI
- `helm` - Kubernetes package manager (v3+)
- `git` - For cloning manifests (if building custom versions)

## Splunk Observability Cloud Setup

### Find Your Configuration Values

Before deploying, gather these values from your Splunk Observability Cloud account:

| Variable | Description | Example |
|----------|-------------|---------|
| `REALM` | Splunk O11y Cloud realm | `us0`, `us1`, `eu0` |
| `ACCESS_TOKEN` | Observability access token | `xxxx...xxxx` |
| `API_TOKEN` | API token for configuration | `xxxx...xxxx` |
| `RUM_TOKEN` | RUM token for frontend | `xxxx...xxxx` |
| `ENV` | Environment name for this deployment | `dev-shop`, `test-workshop` |
| `SPLUNK_SHOW` | Splunk Cloud instance name | `your-instance` |
| `HEC_TOKEN` | HEC token for log ingestion | `xxxx...xxxx` |
| `INDEX` | Target index for logs | `main`, `workshop` |

### Architecture Decision

**Environment Naming:**
- Use descriptive environment names that identify your deployment
- Examples: `dev-shop`, `test-workshop-jan`, `demo-astronomy`
- This appears in Splunk O11y Cloud as `deployment.environment`

**Cluster Naming:**
- Format: `{ENV}-shop-cluster`
- Example: `dev-shop-cluster`

## Deploying Splunk Observability Collector

The Splunk OpenTelemetry Collector receives telemetry from all services and sends it to Splunk Observability Cloud.

### Step 1: Add Helm Repository

```bash
helm repo add splunk-otel-collector-chart https://signalfx.github.io/splunk-otel-collector-chart
helm repo update
```

### Step 2: Create Collector Values File (Optional)

Create `otelcol-base.yaml` for custom collector configuration:

```yaml
# otelcol-base.yaml
# Add any custom receiver, processor, or exporter configurations here

# Example: Add custom attributes
extraAttributes:
  # Add custom attributes to all telemetry
  - name: custom.attribute
    value: "my-value"

# Example: Configure receiver settings
# receivers:
#   otlp:
#     protocols:
#       grpc:
#         endpoint: 0.0.0.0:4317
```

**Note:** This file is optional. Only create it if you need custom collector configuration beyond the helm chart defaults.

### Step 3: Install Collector

Create `install-collector.sh`:

```bash
#!/bin/bash

# Configuration - Replace with your values
REALM="us0"                                    # Your Splunk O11y realm
ACCESS_TOKEN="your-access-token"               # Observability access token
ENV="dev-shop"                                 # Your environment name
SPLUNK_SHOW="your-instance"                    # Splunk Cloud instance
HEC_TOKEN="your-hec-token"                     # HEC token for logs
INDEX="main"                                   # Target log index

# Install collector
helm install splunk-otel-collector \
  --set="splunkObservability.realm=${REALM}" \
  --set="splunkObservability.accessToken=${ACCESS_TOKEN}" \
  --set="clusterName=${ENV}-shop-cluster" \
  --set="splunkObservability.profilingEnabled=true" \
  --set="environment=${ENV}-shop" \
  --set="logsEngine=otel" \
  --set="splunkPlatform.endpoint=https://http-inputs-${SPLUNK_SHOW}.splunkcloud.com:443/services/collector/event" \
  --set="splunkPlatform.token=${HEC_TOKEN}" \
  --set="splunkPlatform.index=${INDEX}" \
  splunk-otel-collector-chart/splunk-otel-collector \
  -f otelcol-base.yaml  # Omit this line if not using custom config
```

**Make executable and run:**
```bash
chmod +x install-collector.sh
./install-collector.sh
```

### Step 4: Verify Collector Installation

```bash
# Check collector pods
kubectl get pods -l app=splunk-otel-collector

# Check collector logs
kubectl logs -l app=splunk-otel-collector --tail=50

# Verify collector service
kubectl get svc -l app=splunk-otel-collector
```

**Expected output:**
- Agent DaemonSet running on each node
- Gateway Deployment running (usually 3 replicas)
- Services exposing OTLP endpoints (4317 for gRPC, 4318 for HTTP)

## Configuring Secrets

The Astronomy Shop services require Kubernetes secrets for configuration.

### Create Secrets Configuration

Create `workshop-secrets.yaml`:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: workshop-secret
  namespace: default
type: Opaque
stringData:
  # Environment identification
  instance: "dev-shop"                          # Instance name
  app: "dev-shop-store"                         # Application name
  env: "dev-shop"                               # Environment name
  deployment: "deployment.environment=dev-shop" # Deployment attribute

  # Splunk Observability Cloud configuration
  realm: "us0"                                  # Your realm
  access_token: "your-access-token"             # O11y access token
  api_token: "your-api-token"                   # API token
  rum_token: "your-rum-token"                   # RUM token for frontend

  # Splunk Cloud Platform configuration (for logs)
  hec_token: "your-hec-token"                   # HEC token
  hec_url: "https://http-inputs-your-instance.splunkcloud.com:443/services/collector/event"

  # AppDynamics configuration (optional)
  appd_token: "your-appd-token"                 # AppDynamics token (optional)

  # External access (for RUM and load generation)
  url: "http://your-cluster-ip"                 # External URL or IP
```

**Important notes:**
- Replace all placeholder values with your actual credentials
- The `appd_token` is optional - services with `optional: true` will start without it
- Keep this file secure and **do not commit to git** (add to `.gitignore`)

### Apply Secrets

```bash
kubectl apply -f workshop-secrets.yaml

# Verify secret creation
kubectl get secret workshop-secret
kubectl describe secret workshop-secret
```

## Deploying the Astronomy Shop

You have two deployment options:
1. **Standard Kubernetes Deployment** - Manual kubectl apply
2. **Demo-in-a-Box Deployment** - Automated via web interface

### Standard Kubernetes Deployment

#### Step 1: Get Deployment Manifest

**Option A: Use pre-built manifest from repository**

```bash
# Clone repository (if you haven't already)
git clone https://github.com/splunk/opentelemetry-demo.git
cd opentelemetry-demo

# Use latest production manifest
kubectl apply -f kubernetes/splunk-astronomy-shop-1.7.1.yaml
```

**Option B: Build custom manifest**

See [DEVELOPING.md](./DEVELOPING.md) for instructions on building custom manifests with your own service images.

#### Step 2: Deploy

```bash
# Create namespace (if needed)
kubectl create namespace default

# Deploy Astronomy Shop
kubectl apply -f kubernetes/splunk-astronomy-shop-{version}.yaml

# Monitor deployment
kubectl get pods -w
```

#### Step 3: Wait for Pods to Start

```bash
# Watch pods come up
kubectl get pods -w

# Check all pods are running
kubectl get pods

# If needed, check specific pod logs
kubectl logs deployment/frontend
```

**Expected startup time:**
- Most services: 30-60 seconds
- Java services (ad, fraud-detection, shop-dc-shim): 2-5 minutes
- Database services (postgres, sql-server): 1-2 minutes

### Demo-in-a-Box Deployment

Demo-in-a-Box (DIAB) provides a web interface for deploying and managing demos on Splunk Show instances.

#### Prerequisites

- Access to a Splunk Show Demo-in-a-Box instance
- SSH access to the instance
- Ansible installed (for initial DIAB setup)

#### Step 1: Install Demo-in-a-Box Framework

SSH to your instance and run:

```bash
# Install DIAB v3
ansible-playbook diab-v3.yml

# Verify installation
ls ~/demo-in-a-box/v3/
```

#### Step 2: Copy Deployment Files

```bash
# Copy your manifest
cp kubernetes/splunk-astronomy-shop-{version}.yaml \
   ~/demo-in-a-box/v3/deployments/astronomy-shop-v{TAG}.yaml

# Copy collector values (if you have custom config)
cp otelcol-base.yaml \
   ~/demo-in-a-box/v3/deployments/astronomy-shop-values-{TAG}.yaml
```

**File naming convention:**
- Manifest: `astronomy-shop-v{TAG}.yaml`
- Values: `astronomy-shop-values-{TAG}.yaml`
- Example: `astronomy-shop-v1.7.1.yaml`

#### Step 3: Register Demo in DIAB

Edit `~/demo-in-a-box/v3/use-cases.yaml` and add:

```yaml
---
deployment: astronomy-shop-{TAG}
name: "Astronomy Shop v{VERSION} ({description})"
values-yaml: astronomy-shop-values-{TAG}
use-case: "OpenTelemetry Demo with Splunk Observability"
description: |
  Astronomy Shop e-commerce demo showcasing:
  - Microservices with OpenTelemetry instrumentation
  - Multiple programming languages (Java, Node.js, Go, Python, etc.)
  - Hybrid cloud-datacenter architecture
  - Real User Monitoring with Splunk RUM
  - AlwaysOn Profiling
  - Database Query Performance monitoring
  - Fraud detection with SQL Server
  - Feature flag-driven scenarios
---
```

**Customization:**
- Replace `{TAG}` with your version/identifier
- Replace `{VERSION}` with the actual version number
- Customize the description for your specific demo

#### Step 4: Deploy via Web UI

1. Open browser: `http://{instance-ip}:8083`
2. Find your new demo pane in the interface
3. Click the **Deploy** button
4. Wait for deployment to complete (DIAB will automatically):
   - Install Splunk Observability Collector (if values-yaml provided)
   - Deploy Astronomy Shop services
   - Configure ingress

**Deployment status:**
- Green checkmark: Successfully deployed
- Red X: Deployment failed (check logs)
- Spinner: Deployment in progress

#### Step 5: Access Demo

Once deployed, access via:
- **Direct IP**: `http://{instance-ip}/`
- **With custom domain**: `http://{custom-domain}/`

DIAB automatically configures ingress for external access.

### Deploying DIAB Variant

The DIAB variant includes ingress configuration for simplified access.

```bash
# Deploy DIAB manifest (includes ingress)
kubectl apply -f kubernetes/splunk-astronomy-shop-{version}-diab.yaml
```

**Difference from standard manifest:**
- Includes Traefik IngressClass configuration
- Pre-configured ingress rules for frontend-proxy
- Optimized for single-node demo environments

## Configuring Ingress

For external access to the Astronomy Shop, configure Kubernetes ingress.

### For Local Testing (k3d, minikube)

**k3d:**
- Port mappings configured during cluster creation
- Access via: `http://localhost:8080/`

**minikube:**
```bash
# Enable ingress addon
minikube addons enable ingress

# Get minikube IP
minikube ip

# Add to /etc/hosts
echo "$(minikube ip) astronomy-shop.local" | sudo tee -a /etc/hosts

# Access via: http://astronomy-shop.local/
```

### For Cloud Deployments

**Using LoadBalancer:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: frontend-proxy
spec:
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: 8080
  selector:
    app: frontend-proxy
```

**Using Ingress (DIAB manifest includes this):**
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: frontend-proxy-ingress
spec:
  ingressClassName: traefik
  rules:
    - http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-proxy
                port:
                  number: 8080
```

### Verify Ingress

```bash
# Check ingress resources
kubectl get ingress

# Check ingress controller
kubectl get pods -n kube-system | grep ingress

# Test access
curl http://{your-ingress-url}/
```

## Verifying the Deployment

### Check Pod Status

```bash
# All pods should be Running
kubectl get pods

# Check for any errors
kubectl get pods | grep -v Running

# Describe problematic pods
kubectl describe pod {pod-name}
```

### Check Services

```bash
# Verify services are exposed
kubectl get svc

# Check service endpoints
kubectl get endpoints
```

### Check Logs

```bash
# Check frontend logs
kubectl logs deployment/frontend

# Check collector agent logs
kubectl logs -l app=splunk-otel-collector-agent --tail=50

# Check for errors across all pods
kubectl logs -l app.kubernetes.io/part-of=opentelemetry-demo --tail=10
```

### Verify Telemetry in Splunk Observability Cloud

1. **Log into Splunk Observability Cloud**

2. **Check APM:**
   - Navigate to **APM** -> **Services**
   - Filter by environment: `{your-env}-shop`
   - You should see all services listed
   - Click into services to see traces

3. **Check Infrastructure:**
   - Navigate to **Infrastructure** -> **Kubernetes**
   - Find your cluster: `{your-env}-shop-cluster`
   - Verify nodes and pods are reporting

4. **Check RUM:**
   - Navigate to **RUM** -> **Applications**
   - Look for frontend application
   - Verify browser sessions are being captured

5. **Check Metrics:**
   - Navigate to **Metrics**
   - Search for: `k8s.pod.phase`
   - Filter by cluster name
   - Verify metrics are flowing

### Verify Application Functionality

**Access the frontend:**
```bash
# Port forward if not using ingress
kubectl port-forward svc/frontend-proxy 8080:8080

# Open browser
# http://localhost:8080/
```

**Test user flows:**
1. Browse products
2. Add items to cart
3. Complete checkout
4. Verify order confirmation

**Check load generator:**
```bash
# Load generator should be creating traffic
kubectl logs deployment/astronomy-loadgen
```

### Common Issues

**Pods not starting:**
```bash
# Check events
kubectl get events --sort-by='.lastTimestamp'

# Check pod status
kubectl describe pod {pod-name}

# Common causes:
# - ImagePullBackOff: Check image registry access
# - CrashLoopBackOff: Check logs for application errors
# - Pending: Check resource availability
```

**No telemetry in Splunk O11y Cloud:**
```bash
# Verify collector is running
kubectl get pods -l app=splunk-otel-collector

# Check collector logs for errors
kubectl logs -l app=splunk-otel-collector-agent | grep -i error

# Verify environment variables in service pods
kubectl exec deployment/frontend -- env | grep OTEL

# Common causes:
# - Wrong access token
# - Wrong realm
# - Firewall blocking OTLP egress
# - Collector not running
```

## Publishing Packages to GitHub

When you've created a new service or updated an existing one, publish it to GitHub Container Registry for team use.

### Prerequisites

- Docker authentication to `ghcr.io/splunk/opentelemetry-demo`
- Write access to Splunk GitHub organization
- Completed service build and testing

### Step 1: Authenticate with GitHub Container Registry

```bash
# Using Personal Access Token
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Verify login
docker info | grep ghcr.io
```

**Creating a PAT:**
1. GitHub -> Settings -> Developer settings -> Personal access tokens
2. Generate new token
3. Select scope: `write:packages`
4. Copy token (you won't see it again)

### Step 2: Build and Push Container

**Using service build script:**
```bash
cd src/my-new-service
./build-my-new-service.sh 1.7.1
```

**Manual multi-platform build:**
```bash
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/splunk/opentelemetry-demo/otel-my-new-service:1.7.1 \
  -t ghcr.io/splunk/opentelemetry-demo/otel-my-new-service:latest \
  --push \
  -f src/my-new-service/Dockerfile .
```

### Step 3: Verify Package Upload

1. Navigate to https://github.com/orgs/splunk/packages
2. Search for: `otel-my-new-service`
3. Package should appear in list

### Step 4: Connect Repository

1. Click on your package
2. Click **Connect Repository** button
3. Select `splunk/opentelemetry-demo`
4. Click **Connect repository**

### Step 5: Configure Package Settings

**Set team access:**
1. Click **Package settings**
2. In **Manage Access** section:
   - Select **Inherit access from source repository**
3. This gives team members automatic access

**Set visibility to public:**
1. Click **Change Visibility** button
2. Select **Public**
3. Type package name to confirm: `opentelemetry-demo/otel-my-new-service`
4. Click **I understand the consequences, change package visibility**

### Step 6: Verify Public Access

```bash
# Test pulling image without authentication
docker pull ghcr.io/splunk/opentelemetry-demo/otel-my-new-service:latest

# Should work without docker login
```

### Package Publishing Checklist

- [ ] Container built for multiple architectures (amd64, arm64)
- [ ] Image pushed to `ghcr.io/splunk/opentelemetry-demo`
- [ ] Package appears in GitHub packages
- [ ] Repository connected to package
- [ ] Team access inherited from repository
- [ ] Package visibility set to Public
- [ ] Image pull tested successfully
- [ ] Service added to `services.yaml` with correct image path
- [ ] Service k8s manifest created
- [ ] Documentation updated

## Updating the Deployment

### Updating Services

**Rolling update (zero downtime):**
```bash
# Update image in deployment
kubectl set image deployment/frontend \
  frontend=ghcr.io/splunk/opentelemetry-demo/otel-frontend:1.7.2

# Watch rollout
kubectl rollout status deployment/frontend

# Rollback if needed
kubectl rollout undo deployment/frontend
```

**Replace entire deployment:**
```bash
# Apply updated manifest
kubectl apply -f kubernetes/splunk-astronomy-shop-{new-version}.yaml

# Force pod restart
kubectl rollout restart deployment/frontend
```

### Updating Collector

**Upgrade collector with new values:**
```bash
# Update install-collector.sh with new settings

# Run helm upgrade
helm upgrade splunk-otel-collector \
  --set="splunkObservability.realm=${REALM}" \
  --set="splunkObservability.accessToken=${ACCESS_TOKEN}" \
  --set="clusterName=${ENV}-shop-cluster" \
  --set="splunkObservability.profilingEnabled=true" \
  --set="environment=${ENV}-shop" \
  --set="logsEngine=otel" \
  --set="splunkPlatform.endpoint=https://http-inputs-${SPLUNK_SHOW}.splunkcloud.com:443/services/collector/event" \
  --set="splunkPlatform.token=${HEC_TOKEN}" \
  --set="splunkPlatform.index=${INDEX}" \
  splunk-otel-collector-chart/splunk-otel-collector \
  -f otelcol-base.yaml
```

**Verify upgrade:**
```bash
# Check helm release
helm list

# Check collector version
kubectl get pods -l app=splunk-otel-collector -o jsonpath='{.items[0].spec.containers[0].image}'
```

### Updating Secrets

```bash
# Edit existing secret
kubectl edit secret workshop-secret

# Or delete and recreate
kubectl delete secret workshop-secret
kubectl apply -f workshop-secrets.yaml

# Restart pods to pick up new secrets
kubectl rollout restart deployment/frontend
```

## Troubleshooting

### Deployment Issues

**Problem: Pods stuck in Pending**

Check resource availability:
```bash
kubectl describe pod {pod-name}
kubectl top nodes
```

Solution: Scale down or increase cluster resources

---

**Problem: ImagePullBackOff**

Check image name and registry access:
```bash
kubectl describe pod {pod-name}
```

Common causes:
- Typo in image name
- Image doesn't exist
- Registry authentication required
- Rate limiting

---

**Problem: CrashLoopBackOff**

Check application logs:
```bash
kubectl logs {pod-name}
kubectl logs {pod-name} --previous
```

Common causes:
- Missing environment variables
- Database connection failed
- Port already in use
- Application error

---

### Collector Issues

**Problem: No telemetry reaching Splunk O11y Cloud**

Check collector status:
```bash
# Collector pods running?
kubectl get pods -l app=splunk-otel-collector

# Check logs
kubectl logs -l app=splunk-otel-collector-agent --tail=100

# Look for export errors
kubectl logs -l app=splunk-otel-collector-agent | grep -i "export"
```

Common causes:
- Wrong access token
- Wrong realm configuration
- Firewall blocking egress on port 443
- Collector not receiving data from apps

---

**Problem: High collector CPU/memory usage**

Check metrics:
```bash
kubectl top pods -l app=splunk-otel-collector
```

Solutions:
- Reduce sampling rate
- Filter unnecessary metrics
- Scale collector replicas
- Adjust memory limits

---

### Application Issues

**Problem: Services can't communicate**

Check service discovery:
```bash
# Services exist?
kubectl get svc

# Endpoints populated?
kubectl get endpoints

# DNS resolution working?
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup frontend-proxy
```

---

**Problem: Frontend not loading**

Check frontend and proxy:
```bash
# Frontend running?
kubectl get pods -l app=frontend

# Proxy running?
kubectl get pods -l app=frontend-proxy

# Check logs
kubectl logs deployment/frontend
kubectl logs deployment/frontend-proxy
```

---

### Database Issues

**Problem: Fraud detection or shop-dc-shim failing**

Check SQL Server:
```bash
# SQL Server running?
kubectl get pods | grep sql

# Check logs
kubectl logs statefulset/sql-server-fraud

# Test connection from pod
kubectl exec deployment/fraud-detection -- nc -zv sql-server-fraud 1433
```

---

**Problem: Postgres connection failures**

```bash
# Postgres running?
kubectl get pods -l app=postgres

# Check logs
kubectl logs statefulset/postgres

# Verify service
kubectl get svc postgres
```

---

### Ingress Issues

**Problem: Can't access frontend externally**

Check ingress configuration:
```bash
# Ingress exists?
kubectl get ingress

# Ingress controller running?
kubectl get pods -n kube-system | grep ingress

# Check ingress logs
kubectl logs -n kube-system {ingress-controller-pod}
```

---

### Secrets Issues

**Problem: Pods failing due to missing secrets**

```bash
# Secret exists?
kubectl get secret workshop-secret

# Check secret keys
kubectl describe secret workshop-secret

# Verify pod can access secret
kubectl describe pod {pod-name} | grep -A 5 "Mounts"
```

---

## Additional Resources

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System architecture overview
- [DEVELOPING.md](./DEVELOPING.md) - Development and building guide
- [PRODUCTION-WORKFLOW-GUIDE.md](./PRODUCTION-WORKFLOW-GUIDE.md) - Production workflows
- [Splunk Observability Cloud Docs](https://docs.splunk.com/observability)
- [OpenTelemetry Demo Docs](https://opentelemetry.io/docs/demo/)
- [Splunk OTel Collector Chart](https://github.com/signalfx/splunk-otel-collector-chart)

## Getting Help

If you encounter issues:

1. **Check this troubleshooting section** above
2. **Review logs** for error messages
3. **Search existing issues**: https://github.com/splunk/opentelemetry-demo/issues
4. **Open a new issue** with:
   - What you were trying to do
   - What happened vs. expected behavior
   - Deployment logs and pod status
   - Your environment details

**Document Version:** 3.0
**Last Updated:** March 12, 2026
