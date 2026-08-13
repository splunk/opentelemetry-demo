# How to Deploy and Run the Splunk OpenTelemetry Demo

**Supported deployment target: Kubernetes.**

This fork ships as a set of **stitched Kubernetes manifests + a Helm values
file**, published as assets on each GitHub Release. That is the one and only
path we build, test, and promote.

> **Docker Compose is deprecated and unmaintained.** The `docker-compose*.yml`
> files and `make start` target are inherited from the upstream OpenTelemetry
> demo and are **not** kept in sync with this fork's Splunk instrumentation,
> image tags, or database wiring. They are known-broken on a fresh clone (see
> issues #298 and #299) and will be removed. **Do not use Docker Compose to run
> this demo.** Use the Kubernetes manifests below.

---

## What you deploy

Every release attaches these assets (current promoted version: see
[`kubernetes/PROMOTED-VERSION`](kubernetes/PROMOTED-VERSION)):

| Asset | Purpose |
|-------|---------|
| `splunk-astronomy-shop-<VERSION>.yaml` | **Core** Astronomy Shop services |
| `splunk-astronomy-shop-<VERSION>-diab.yaml` | Demo-in-a-Box (adds Traefik ingress) |
| `splunk-astronomy-shop-<VERSION>-lambda.yaml` | Lambda / planning services |
| `splunk-astronomy-shop-<VERSION>-throttle-demo.yaml` | order-validation (k8s CPU-throttle scenario) |
| `splunk-astronomy-shop-<VERSION>-dc-shim.yaml` | Datacenter shim + db + loadgen |
| `splunk-astronomy-shop-<VERSION>-values.yaml` | Helm values (for the collector / reference) |

The app manifest is plain Kubernetes YAML — apply it with `kubectl apply -f`.
It does **not** need Helm. Telemetry is sent to Splunk Observability Cloud by
the **Splunk OpenTelemetry Collector**, which you install separately with Helm
(see [DEPLOYMENT.md](DEPLOYMENT.md)).

---

## Prerequisites

- A Kubernetes cluster. Minimum ~8 CPU / 16 GB RAM.
- `kubectl` and `helm` (v3+).

### Tested platforms

| Platform | Status |
|----------|--------|
| **k3d** (k3s-in-Docker) | ✅ Tested / known-good — recommended for laptop-scale |
| **Docker Desktop – Kubernetes** | ⚠️ Has worked previously; not continuously verified |
| EKS / GKE / AKS | ✅ Production-like targets |
| Splunk Show Demo-in-a-Box | ✅ Use the `-diab.yaml` variant |
| minikube | ⚠️ Should work; not continuously verified |
- A Splunk Observability Cloud account (realm, access token, RUM token) and,
  for logs, a Splunk Cloud HEC token.

Full collector install, secrets, ingress, and troubleshooting live in
**[DEPLOYMENT.md](DEPLOYMENT.md)** — this page is the short "get it running"
path.

---

## Getting the manifests — three ways

### 1. Direct from the GitHub Release (self-serve)

Pull the version you want straight from the release tag:

```bash
VERSION=2.0.7
BASE=https://github.com/splunk/opentelemetry-demo/releases/download/v${VERSION}

# core app manifest + values
curl -sSLO ${BASE}/splunk-astronomy-shop-${VERSION}.yaml
curl -sSLO ${BASE}/splunk-astronomy-shop-${VERSION}-values.yaml
```

Release page: <https://github.com/splunk/opentelemetry-demo/releases/tag/v2.0.7>

### 2. Splunk Show / Demo-in-a-Box (promoted)

Promoted releases are pushed automatically to
[`splunk/o11y-field-demos`](https://github.com/splunk/o11y-field-demos) by the
**Astronomy Shop – Promote** GitHub Action (this also updates
`kubernetes/PROMOTED-VERSION`). If you deploy through Splunk Show / DIAB, the
manifests are already staged there — use the `-diab.yaml` variant.

### 3. Workshop repo

Workshop deployments consume the same released assets via the workshop
repository. Point the workshop at the pinned `<VERSION>` manifest + values so it
stays reproducible.

> In all three cases it's the **same** release assets. Direct-from-release is
> the source of truth; o11y-field-demos and the workshop are promotion targets.

---

## Deploy (core app)

```bash
VERSION=2.0.7

# 1. (once) install the Splunk OTel Collector via Helm — see DEPLOYMENT.md
#    and create your secret (example: kubernetes/example-secrets.yaml)

# 2. deploy the Astronomy Shop
kubectl apply -f splunk-astronomy-shop-${VERSION}.yaml

# 3. watch it come up
kubectl get pods -w
```

For Demo-in-a-Box (with ingress) use the DIAB variant instead:

```bash
kubectl apply -f splunk-astronomy-shop-${VERSION}-diab.yaml
```

Optional add-on scenarios (apply on top of core):

```bash
kubectl apply -f splunk-astronomy-shop-${VERSION}-lambda.yaml         # lambda/planning
kubectl apply -f splunk-astronomy-shop-${VERSION}-throttle-demo.yaml  # CPU-throttle demo
kubectl apply -f splunk-astronomy-shop-${VERSION}-dc-shim.yaml        # datacenter shim
```

---

## Verify

```bash
# all core pods Ready
kubectl get pods

# reach the store UI (frontend-proxy) via port-forward
kubectl port-forward svc/frontend-proxy 8080:8080
# then open http://localhost:8080
```

Then confirm traces/metrics/logs are arriving in Splunk Observability Cloud for
your `deployment.environment`.

---

## Why not Docker Compose?

This fork's value is in the Splunk-specific instrumentation, image tags,
database wiring (single `astroshop` Postgres), and the stitched k8s manifests —
all of which are exercised by the Kubernetes path and the release pipeline. The
upstream `docker-compose*.yml` files are not part of that pipeline, drift out of
sync, and break on a fresh clone. Use the manifests above.

If you need a laptop-scale cluster, run the manifests on **k3d** (tested,
known-good) — that exercises the exact same artifacts we ship. **Docker Desktop's
built-in Kubernetes** has also worked in the past.
