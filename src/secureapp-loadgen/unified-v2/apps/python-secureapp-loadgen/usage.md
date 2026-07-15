# SecureApp Python Datagen — Usage Guide

## Overview

This is a Python (Flask + Gunicorn) application that exercises vulnerability classes for Splunk SecureApp agent detection. It ships **intentionally pinned vulnerable libraries** and maps each HTTP attack endpoint to the library/CVE it exercises.

Attack traffic is driven by **in-cluster k8s datagen** (`datagen-python-loop` Deployment or `datagen-python-once` Job) when `PYTHON_ATTACK_DATAGEN_ENABLED=true` in `k8s/values.env`. By default attack datagen is off until Splunk Python attack support is available. Telemetry flows through the shared Splunk OpenTelemetry collector to Splunk Observability Cloud.

## Service Identity

The app is name-agnostic. Nothing in the Flask routes or attack handlers changes based on the service name. Splunk APM identity comes from OpenTelemetry resource attributes:

```
OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=${DEPLOY_ENV},service.name=${SERVICE_NAME}"
```

Set `SERVICE_NAME` (or `OTEL_SERVICE_NAME`) and `DEPLOY_ENV` before startup — the app **exits immediately** if either is missing. To appear as a different service in APM, change `SERVICE_NAME`; endpoints and attack behavior stay the same.

| Env Var | Purpose |
|---------|---------|
| `SERVICE_NAME` / `OTEL_SERVICE_NAME` | Splunk `service.name` |
| `DEPLOY_ENV` | Splunk `deployment.environment.name` |
| `REALM` | Splunk realm (collector routing) |
| `OTEL_RESOURCE_ATTRIBUTES` | Full resource string (set by `k8s/deploy.sh`) |

## Splunk OTel / SecureApp Configuration

The container runs under `opentelemetry-instrument` with the Splunk SecureApp Python extension:

| Env Var | Default | Purpose |
|---------|---------|---------|
| `SPLUNK_SECUREAPP_AGENT_ENABLED` | `true` | Enable SecureApp runtime protection |
| `SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY` | `60` | Seconds before first dependency (VA) report |
| `SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL` | `86400` | Dependency scan interval in **seconds** |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://collector:4318` | Collector OTLP endpoint |
| `OTEL_LOGS_EXPORTER` | `otlp` | Export logs for SecureApp event routing |

If `SPLUNK_SECUREAPP_AGENT_ENABLED` is off or the collector is unreachable, the app still serves HTTP but produces no APM or security telemetry.

## Attack Scenario Filtering

| Env Var | Purpose |
|---------|---------|
| `ATTACK_ENABLED_SCENARIOS` | Comma-separated subset: `rce`, `ssrf`, `sqli`, `log4j`, `deserial`. Empty = all enabled. |
| `WORKSPACE_SYNC_ENABLED` | `true` registers `/api/v1/workspace/sync` (all scenarios in one request) |

## VA Runtime (Python only)

| `VA_RUNTIME_MODE` | Behavior |
|-------------------|----------|
| `off` (default) | VA hints served only via in-process rotation at startup |
| `http` | Enables `GET /internal/va/next` for external VA hint polling |
| `scheduler` | Reserved; behaves as `off` in current build |

`VA_STAGGER_INTERVAL_SECONDS` controls hint rotation cadence (default `1800`).

## Endpoints

### Always registered

| Endpoint | Method | CVE / Library | Purpose |
|----------|--------|---------------|---------|
| `/health` | GET | — | Health check |
| `/api/v1/documents/convert` | GET | CVE-2024-22195 / Jinja2 3.1.2 | RCE / SSTI |
| `/api/v1/links/preview` | GET | CVE-2021-33503 / urllib3 1.26.5 | SSRF to cloud metadata |
| `/api/v1/users/search` | GET | CVE-2022-21698 / SQLAlchemy 1.4.46 | SQL injection |
| `/api/v1/auth/login` | GET | CVE-2020-14343 / PyYAML 5.3.1 | Unsafe YAML load (Log4Shell parity) |
| `/api/v1/sessions/import` | GET | CVE-2022-45199 / Pillow 9.2.0 | Deserialization via ImageMath.eval |
| `/internal/vulnerabilities` | GET | — | JSON summary of pinned CVE targets |

### Alternate attack paths (same scenarios)

| Endpoint | Scenario |
|----------|----------|
| `/attack/rce-jinja2` | rce |
| `/attack/ssrf` | ssrf |
| `/attack/sqli` | sqli |
| `/attack/log4j` | log4j |
| `/attack/deserialization-pillow` | deserial |

### Conditionally registered

| Endpoint | Condition | Purpose |
|----------|-----------|---------|
| `/api/v1/workspace/sync` | `WORKSPACE_SYNC_ENABLED=true` | All 5 vuln classes in one transaction |
| `/internal/va/next` | `VA_RUNTIME_MODE=http` | Advance VA dependency hint |

## Datagen Behavior (shared loadgen)

Attack traffic uses **`k8s/loadgen/loadgen.sh`** — the same scheduler as Java in-container loadgen. Controlled via `Unified-v2/k8s/values.env`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATAGEN_MODE` | `loop` | `off` \| `once` \| `loop` — attack scheduling mode |
| `PYTHON_ATTACK_DATAGEN_ENABLED` | `false` | Enable k8s attack datagen for Python (set `true` when Splunk attack feature ships) |
| `FLAGD_HOST` | — | flagd pace control (`secureappAttack` flag) |
| `LOADGEN_PACE` | — | Pace when flagd unavailable: `minimal` \| `targeted` \| `max` |
| `ATTACK_LOOP_START_DELAY_SECONDS` | `90` | Delay before loadgen starts firing |

Each endpoint fires on its own randomized interval per pace tier (not a fixed rotation interval).

## Local / Standalone Run

```bash
cd apps/python-secureapp-loadgen

export SERVICE_NAME=python-ad
export DEPLOY_ENV=dev-secureapp-python
export REALM=us1
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318

pip install -r requirements.txt
opentelemetry-instrument gunicorn -c gunicorn.conf.py run:app
```

Trigger attacks manually:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/api/v1/auth/login
curl http://localhost:8080/internal/vulnerabilities
```

## Unified Deploy

From `Unified-v2/k8s`:

```bash
cp values.env.example values.env   # set INGEST_TOKEN
# PYTHON_ATTACK_DATAGEN_ENABLED=true when Splunk Python attack feature is available
./deploy.sh
curl http://localhost:30081/health   # default NodePort
```

See `SECURITY.md` for intentional CVE pins and scanner suppression policy.
