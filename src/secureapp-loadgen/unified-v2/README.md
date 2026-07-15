# Unified SecureApp Datagen v2

Unified deployment of **Java** (secureapp-loadgen), **Python**, and **Node.js** SecureApp test applications with a shared Splunk OpenTelemetry collector.

## Layout

```text
Unified-v2/
├── apps/
│   ├── java-secureapp-loadgen/
│   ├── python-secureapp-loadgen/
│   └── node-secureapp-loadgen/
└── k8s/
    ├── loadgen/                    # Shared attack scheduler (all 3 languages)
    │   ├── loadgen.sh
    │   ├── loadgen-entries.sh      # path|label|intervals per language
    │   ├── datagen-once.sh
    │   └── Dockerfile
    ├── values.env.example
    ├── deploy.sh
    ├── base/                       # Kustomize manifests (3 apps + collector + datagen)
    └── lib/generate-collector-config.sh
```

## Quick start

```bash
cd Unified-v2/k8s
cp values.env.example values.env
# Edit values.env — set INGEST_TOKEN

./deploy.sh --create-k3d
```

Health checks (default NodePorts):

```bash
kubectl -n unified-secureapp get pods
./status.sh
```

## Loadgen model (shared)

All three languages use **`k8s/loadgen/loadgen.sh`** for attack scheduling:

| Pace | Attack frequency |
|------|------------------|
| `minimal` (default) | Each endpoint every ~2–12 hours |
| `targeted` | SQLi + Log4Shell every ~10–15 min |
| `max` | All attacks every ~3–15 min |

| Variable | Purpose |
|----------|---------|
| `FLAGD_HOST` | flagd host for `secureappAttack` pace (empty = use `LOADGEN_PACE` or minimal) |
| `LOADGEN_PACE` | Pace override when flagd is unavailable |
| `FLAG_CHECK_INTERVAL` | Seconds between flagd polls (default `60`) |
| `LOADGEN_LANGUAGE` | `java` \| `python` \| `node` — selects consolidated entries |
| `ATTACK_ENABLED_SCENARIOS` | Filter: `rce`, `ssrf`, `sqli`, `log4j`, `deserial` |

Schedule entries live in **`loadgen-entries.sh`** as `path|label|minimal_min|minimal_max|tgt_min|tgt_max|max_min|max_max` per language.

**`DATAGEN_MODE`** controls attack scheduling; per-language flags gate Python/Node until Splunk attack support is available:

| Mode | Behavior |
|------|----------|
| `loop` | Java in-container loadgen; Python/Node k8s loops when their attack flag is `true` |
| `once` | One-shot k8s jobs per enabled language (Java builtin off) |
| `off` | No attack traffic |

| Variable | Default | Purpose |
|----------|---------|---------|
| `PYTHON_ATTACK_DATAGEN_ENABLED` | `false` | Enable Python k8s attack datagen (`datagen-python-loop` / `-once`) |
| `NODE_ATTACK_DATAGEN_ENABLED` | `false` | Enable Node k8s attack datagen (`datagen-node-loop` / `-once`) |

## Configuration model

### Java (secureapp-loadgen)

| Variable | Purpose |
|----------|---------|
| `JAVA_SERVICE_NAME` | `OTEL_SERVICE_NAME` / Splunk `service.name` |
| `JAVA_SHIPPING_ADDR` | Optional outbound dependency (Astronomy Shop) |
| `SPLUNK_OTEL_JAVAAGENT_VERSION` | CSA Java agent version (default `2.27.0`) |

### Python / Node

Apps always deploy. Attack datagen loops/jobs are controlled by `PYTHON_ATTACK_DATAGEN_ENABLED` and `NODE_ATTACK_DATAGEN_ENABLED` (default `false` until Splunk attack feature is available for those languages).

### Shared

| Variable | Purpose |
|----------|---------|
| `INGEST_TOKEN` | Splunk ingest (required) |
| `REALM` | Splunk realm |
| `DEPLOY_ENV` | `deployment.environment.name` for all apps |
| `ATTACK_LOOP_START_DELAY_SECONDS` | Delay before first k8s datagen round |

## Splunk correlation

Filter by `service.name` and `deployment.environment.name`:

- Java: `service.name=java-ad`
- Python: `service.name=python-ad`
- Node: `service.name=node-ad`

All share `deployment.environment.name=${DEPLOY_ENV}`.

## Teardown

```bash
cd Unified-v2/k8s
./teardown.sh
```
