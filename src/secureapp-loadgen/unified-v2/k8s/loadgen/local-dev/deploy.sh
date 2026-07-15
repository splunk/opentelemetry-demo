#!/bin/bash
# Build Java, Python, and Node SecureApp test apps; deploy unified stack to k8s/k3d.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UNIFIED_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APPS_ROOT="${UNIFIED_ROOT}/apps"
LOADGEN_DIR="${SCRIPT_DIR}/loadgen"
JAVA_APP_DIR="${APPS_ROOT}/java-secureapp-loadgen"
PYTHON_APP_DIR="${APPS_ROOT}/python-secureapp-loadgen"
NODE_APP_DIR="${APPS_ROOT}/node-secureapp-loadgen"
GENERATED_DIR="${SCRIPT_DIR}/generated"
VALUES_FILE="${SCRIPT_DIR}/values.env"

DEFAULT_K3D_CLUSTER="secapp-default"
DO_SKIP_BUILD=false
DO_SKIP_DEPLOY=false
K3D_IMPORT=true
DO_CREATE_K3D=false

usage() {
  cat <<'EOF'
deploy.sh — build all three SecureApp datagen apps and deploy unified stack

Usage:
  cp values.env.example values.env   # set INGEST_TOKEN
  ./deploy.sh

Options:
  --values-file PATH   Env file (default: ./values.env)
  --skip-build         Skip docker builds
  --skip-deploy        Build/import only
  --no-k3d-import      Skip k3d image import
  --create-k3d         Create k3d cluster if missing
  -h, --help           Show help

Deploys Java + Python + Node.js with shared INGEST_TOKEN and REALM.
Optional dual-realm: set REALM_SECONDARY + INGEST_TOKEN_SECONDARY to fan-out telemetry.
Health checks (NodePort defaults):
  curl http://localhost:30080/health   # java
  curl http://localhost:30081/health   # python
  curl http://localhost:30082/health   # node
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --values-file) VALUES_FILE="$2"; shift 2 ;;
    --skip-build)  DO_SKIP_BUILD=true; shift ;;
    --skip-deploy) DO_SKIP_DEPLOY=true; shift ;;
    --no-k3d-import) K3D_IMPORT=false; shift ;;
    --create-k3d)    DO_CREATE_K3D=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done

log() { printf '[unified/deploy] %s\n' "$*"; }
die() { printf '[unified/deploy] ERROR: %s\n' "$*" >&2; exit 1; }

datagen_lang_enabled() {
  local val="$1"
  case "$(echo "${val}" | tr '[:upper:]' '[:lower:]')" in
    false|0|no|off) return 1 ;;
    *) return 0 ;;
  esac
}

append_datagen_delete_patch() {
  local file="$1" api_version="$2" kind="$3" name="$4"
  if [[ ! -s "${file}" ]]; then
    : >"${file}"
  else
    printf '\n---\n' >>"${file}"
  fi
  cat >>"${file}" <<EOF
apiVersion: ${api_version}
kind: ${kind}
metadata:
  name: ${name}
\$patch: delete
EOF
}

write_attack_datagen_patches() {
  [[ "${DATAGEN_MODE}" == "off" ]] && return 0

  local patch_file="${GENERATED_DIR}/patch-attack-datagen-lang.yaml"
  rm -f "${patch_file}"
  local n=0

  if [[ "${DATAGEN_MODE}" == "loop" ]]; then
    if ! datagen_lang_enabled "${PYTHON_ATTACK_DATAGEN_ENABLED}"; then
      append_datagen_delete_patch "${patch_file}" "apps/v1" "Deployment" "datagen-python-loop"
      n=$((n + 1))
    fi
    if ! datagen_lang_enabled "${NODE_ATTACK_DATAGEN_ENABLED}"; then
      append_datagen_delete_patch "${patch_file}" "apps/v1" "Deployment" "datagen-node-loop"
      n=$((n + 1))
    fi
  elif [[ "${DATAGEN_MODE}" == "once" ]]; then
    if ! datagen_lang_enabled "${PYTHON_ATTACK_DATAGEN_ENABLED}"; then
      append_datagen_delete_patch "${patch_file}" "batch/v1" "Job" "datagen-python-once"
      n=$((n + 1))
    fi
    if ! datagen_lang_enabled "${NODE_ATTACK_DATAGEN_ENABLED}"; then
      append_datagen_delete_patch "${patch_file}" "batch/v1" "Job" "datagen-node-once"
      n=$((n + 1))
    fi
  fi

  if [[ "${n}" -gt 0 ]]; then
    echo "  - path: patch-attack-datagen-lang.yaml" >>"${GENERATED_DIR}/kustomization.yaml"
  fi
}

prune_disabled_attack_datagen() {
  # kubectl apply -k does not remove resources omitted by $patch: delete; prune explicitly.
  [[ "${DATAGEN_MODE}" == "off" ]] && return 0

  if [[ "${DATAGEN_MODE}" == "loop" ]]; then
    kubectl -n unified-secureapp delete job datagen-java-once --ignore-not-found=true >/dev/null
    if ! datagen_lang_enabled "${PYTHON_ATTACK_DATAGEN_ENABLED}"; then
      kubectl -n unified-secureapp delete deployment datagen-python-loop --ignore-not-found=true >/dev/null
      kubectl -n unified-secureapp delete job datagen-python-once --ignore-not-found=true >/dev/null
    fi
    if ! datagen_lang_enabled "${NODE_ATTACK_DATAGEN_ENABLED}"; then
      kubectl -n unified-secureapp delete deployment datagen-node-loop --ignore-not-found=true >/dev/null
      kubectl -n unified-secureapp delete job datagen-node-once --ignore-not-found=true >/dev/null
    fi
  elif [[ "${DATAGEN_MODE}" == "once" ]]; then
    if ! datagen_lang_enabled "${PYTHON_ATTACK_DATAGEN_ENABLED}"; then
      kubectl -n unified-secureapp delete job datagen-python-once --ignore-not-found=true >/dev/null
      kubectl -n unified-secureapp delete deployment datagen-python-loop --ignore-not-found=true >/dev/null
    fi
    if ! datagen_lang_enabled "${NODE_ATTACK_DATAGEN_ENABLED}"; then
      kubectl -n unified-secureapp delete job datagen-node-once --ignore-not-found=true >/dev/null
      kubectl -n unified-secureapp delete deployment datagen-node-loop --ignore-not-found=true >/dev/null
    fi
  fi
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

[[ -f "${VALUES_FILE}" ]] || die "Missing ${VALUES_FILE} — copy values.env.example to values.env"

set -a
# shellcheck disable=SC1090
source "${VALUES_FILE}"
set +a

: "${INGEST_TOKEN:?INGEST_TOKEN is required in values.env}"

# shellcheck source=lib/generate-collector-config.sh
source "${SCRIPT_DIR}/lib/generate-collector-config.sh"

# Shared
REALM="${REALM:-us1}"
REALM_SECONDARY="${REALM_SECONDARY:-}"
DUAL_REALM_ENABLED=false
if [[ -n "${REALM_SECONDARY}" ]]; then
  DUAL_REALM_ENABLED=true
  : "${INGEST_TOKEN_SECONDARY:?INGEST_TOKEN_SECONDARY is required when REALM_SECONDARY is set}"
  [[ "${REALM}" != "${REALM_SECONDARY}" ]] || die "REALM and REALM_SECONDARY must differ"
fi
DEPLOY_ENV="${DEPLOY_ENV:-${JAVA_DEPLOY_ENV:-${PYTHON_DEPLOY_ENV:-${NODE_DEPLOY_ENV:-dev-secureapp-unified}}}}"
IMAGE_REGISTRY="${IMAGE_REGISTRY:-secureapp}"
IMAGE_TAG="${IMAGE_TAG:-local}"
DATAGEN_MODE="${DATAGEN_MODE:-loop}"
# Legacy master switch (LOADGEN_ENABLED=false forces DATAGEN_MODE=off)
if [[ -n "${LOADGEN_ENABLED:-}" ]] && ! datagen_lang_enabled "${LOADGEN_ENABLED}"; then
  DATAGEN_MODE="off"
fi
APP_SERVICE_TYPE="${APP_SERVICE_TYPE:-NodePort}"
K3D_CLUSTER="${K3D_CLUSTER:-}"
ATTACK_ENABLED_SCENARIOS="${ATTACK_ENABLED_SCENARIOS:-}"
ATTACK_LOOP_START_DELAY_SECONDS="${ATTACK_LOOP_START_DELAY_SECONDS:-90}"
WORKSPACE_SYNC_ENABLED="${WORKSPACE_SYNC_ENABLED:-false}"

# Per-language attack datagen (apps still deploy; Splunk attack feature may be Java-only today)
PYTHON_ATTACK_DATAGEN_ENABLED="${PYTHON_ATTACK_DATAGEN_ENABLED:-false}"
NODE_ATTACK_DATAGEN_ENABLED="${NODE_ATTACK_DATAGEN_ENABLED:-false}"

# Shared loadgen (k8s/loadgen/loadgen.sh) — pace + per-endpoint intervals
FLAGD_HOST="${FLAGD_HOST:-}"
FLAGD_OFREP_PORT="${FLAGD_OFREP_PORT:-8016}"
FLAG_CHECK_INTERVAL="${FLAG_CHECK_INTERVAL:-60}"
LOADGEN_PACE="${LOADGEN_PACE:-}"

SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY="${SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY:-${PYTHON_SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY:-${NODE_SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY:-60}}}"

# Scan interval: one value in seconds for values.env; Node agent receives ms (×1000) at deploy time.
if [[ -n "${SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL:-}" ]]; then
  SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL_SECONDS="${SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL}"
elif [[ -n "${PYTHON_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL:-}" ]]; then
  SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL_SECONDS="${PYTHON_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL}"
elif [[ -n "${NODE_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL:-}" ]]; then
  SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL_SECONDS=$(( NODE_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL / 1000 ))
else
  SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL_SECONDS=86400
fi
PYTHON_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL="${SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL_SECONDS}"
NODE_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL="$(( SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL_SECONDS * 1000 ))"

VA_RUNTIME_MODE="${VA_RUNTIME_MODE:-${JAVA_VA_RUNTIME_MODE:-${PYTHON_VA_RUNTIME_MODE:-off}}}"
VA_STAGGER_INTERVAL_SECONDS="${VA_STAGGER_INTERVAL_SECONDS:-${JAVA_VA_STAGGER_INTERVAL_SECONDS:-${PYTHON_VA_STAGGER_INTERVAL_SECONDS:-1800}}}"

SPLUNK_OTEL_JAVAAGENT_VERSION="${SPLUNK_OTEL_JAVAAGENT_VERSION:-2.27.0}"
SPLUNK_OTEL_JAVAAGENT_URL="${SPLUNK_OTEL_JAVAAGENT_URL:-}"

# Java
JAVA_SERVICE_NAME="${JAVA_SERVICE_NAME:-java-ad}"
JAVA_APP_NODE_PORT="${JAVA_APP_NODE_PORT:-30080}"

# Java in-container loadgen: on only when DATAGEN_MODE=loop (Python/Node use k8s datagen pods)
if [[ "${DATAGEN_MODE}" == "loop" ]]; then
  JAVA_BUILTIN_LOADGEN_ENABLED=true
else
  JAVA_BUILTIN_LOADGEN_ENABLED=false
fi
JAVA_OTEL_SERVICE_NAMESPACE="${JAVA_OTEL_SERVICE_NAMESPACE:-unified-secureapp}"
JAVA_SHIPPING_ADDR="${JAVA_SHIPPING_ADDR:-}"
JAVA_SHIPPING_API="${JAVA_SHIPPING_API:-}"

# Python
PYTHON_SERVICE_NAME="${PYTHON_SERVICE_NAME:-python-ad}"
PYTHON_APP_NODE_PORT="${PYTHON_APP_NODE_PORT:-30081}"

# Node
NODE_SERVICE_NAME="${NODE_SERVICE_NAME:-node-ad}"
NODE_APP_NODE_PORT="${NODE_APP_NODE_PORT:-30082}"

JAVA_OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=${DEPLOY_ENV},service.name=${JAVA_SERVICE_NAME}"
PYTHON_OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=${DEPLOY_ENV},service.name=${PYTHON_SERVICE_NAME}"
NODE_OTEL_RESOURCE_ATTRIBUTES="deployment.environment.name=${DEPLOY_ENV},service.name=${NODE_SERVICE_NAME}"

JAVA_IMAGE="${IMAGE_REGISTRY}/java-app:${IMAGE_TAG}"
PYTHON_IMAGE="${IMAGE_REGISTRY}/python-app:${IMAGE_TAG}"
NODE_IMAGE="${IMAGE_REGISTRY}/node-app:${IMAGE_TAG}"
LOADGEN_IMAGE="${IMAGE_REGISTRY}/loadgen-runner:${IMAGE_TAG}"

detect_k3d_cluster() {
  local ctx
  ctx="$(kubectl config current-context 2>/dev/null || true)"
  if [[ "${ctx}" == k3d-* ]]; then
    echo "${ctx#k3d-}"
  fi
}

k3d_cluster_exists() {
  k3d cluster get "${1}" >/dev/null 2>&1
}

kubectl_cluster_ready() {
  kubectl cluster-info >/dev/null 2>&1
}

ensure_k3d_cluster() {
  local name="$1"
  if k3d_cluster_exists "${name}"; then
    return 0
  fi
  if $DO_CREATE_K3D; then
    log "k3d cluster '${name}' not found — creating..."
    JAVA_APP_NODE_PORT="${JAVA_APP_NODE_PORT}" \
      PYTHON_APP_NODE_PORT="${PYTHON_APP_NODE_PORT}" \
      NODE_APP_NODE_PORT="${NODE_APP_NODE_PORT}" \
      "${SCRIPT_DIR}/k3d-create-cluster.sh" "${name}"
    return 0
  fi
  die "k3d cluster '${name}' not found. Run: ./k3d-create-cluster.sh ${name} or ./deploy.sh --create-k3d"
}

if [[ -z "${K3D_CLUSTER}" ]]; then
  _detected="$(detect_k3d_cluster || true)"
  if [[ -n "${_detected}" ]]; then
    K3D_CLUSTER="${_detected}"
    log "Auto-detected k3d cluster: ${K3D_CLUSTER}"
  elif $DO_CREATE_K3D; then
    K3D_CLUSTER="${DEFAULT_K3D_CLUSTER}"
  fi
fi

USE_K3D=false
if [[ -n "${K3D_CLUSTER}" ]]; then
  USE_K3D=true
  if ! $DO_SKIP_DEPLOY || ([[ -n "${K3D_CLUSTER}" ]] && $K3D_IMPORT && ! $DO_SKIP_BUILD); then
    ensure_k3d_cluster "${K3D_CLUSTER}"
  elif ! k3d_cluster_exists "${K3D_CLUSTER}"; then
    log "Warning: k3d cluster '${K3D_CLUSTER}' not found — skipping import until cluster exists"
    K3D_IMPORT=false
  fi
fi

require_cmd docker
require_cmd kubectl

for dir in "${JAVA_APP_DIR}" "${PYTHON_APP_DIR}" "${NODE_APP_DIR}" "${LOADGEN_DIR}"; do
  [[ -d "${dir}" ]] || die "Required directory not found: ${dir}"
done

chmod +x "${LOADGEN_DIR}/loadgen.sh" "${LOADGEN_DIR}/loadgen-entries.sh" "${LOADGEN_DIR}/datagen-once.sh"

build_image() {
  local name="$1" dir="$2"
  local image="${IMAGE_REGISTRY}/${name}-app:${IMAGE_TAG}"
  if $DO_SKIP_BUILD; then
    log "Skipping build for ${image}"
    return 0
  fi
  log "Building ${image} from ${dir}..."
  if [[ "${name}" == "java" ]]; then
    local build_args=(
      -f "${JAVA_APP_DIR}/Dockerfile"
      --build-arg "SPLUNK_OTEL_JAVAAGENT_VERSION=${SPLUNK_OTEL_JAVAAGENT_VERSION:-2.27.0}"
    )
    if [[ -n "${SPLUNK_OTEL_JAVAAGENT_URL:-}" ]]; then
      build_args+=(--build-arg "SPLUNK_OTEL_JAVAAGENT_URL=${SPLUNK_OTEL_JAVAAGENT_URL}")
    fi
    docker build "${build_args[@]}" -t "${image}" "${UNIFIED_ROOT}"
  else
    docker build -t "${image}" "${dir}"
  fi
}

build_loadgen_runner() {
  if $DO_SKIP_BUILD; then
    log "Skipping build for ${LOADGEN_IMAGE}"
    return 0
  fi
  log "Building ${LOADGEN_IMAGE} from ${LOADGEN_DIR}..."
  docker build -t "${LOADGEN_IMAGE}" "${LOADGEN_DIR}"
}

build_image java "${JAVA_APP_DIR}"
build_image python "${PYTHON_APP_DIR}"
build_image node "${NODE_APP_DIR}"
build_loadgen_runner

if [[ -n "${K3D_CLUSTER}" ]] && $K3D_IMPORT; then
  require_cmd k3d
  for img in "${JAVA_IMAGE}" "${PYTHON_IMAGE}" "${NODE_IMAGE}" "${LOADGEN_IMAGE}"; do
    log "Importing ${img} into k3d ${K3D_CLUSTER}..."
    k3d image import "${img}" -c "${K3D_CLUSTER}"
  done
fi

mkdir -p "${GENERATED_DIR}"

cp "${LOADGEN_DIR}/loadgen.sh" "${LOADGEN_DIR}/loadgen-entries.sh" "${LOADGEN_DIR}/datagen-once.sh" \
  "${GENERATED_DIR}/"

COLLECTOR_CONFIG_FILE="${GENERATED_DIR}/collector-otelcol-config.yaml"
write_collector_otel_config "${COLLECTOR_CONFIG_FILE}" "${DUAL_REALM_ENABLED}" "${REALM_SECONDARY}"

SECRET_LITERALS="      - INGEST_TOKEN=${INGEST_TOKEN}"
if $DUAL_REALM_ENABLED; then
  SECRET_LITERALS+=$'\n      - INGEST_TOKEN_SECONDARY='"${INGEST_TOKEN_SECONDARY}"
fi

SHARED_CONFIG_LITERALS="      - REALM=${REALM}"
if $DUAL_REALM_ENABLED; then
  SHARED_CONFIG_LITERALS+=$'\n      - REALM_SECONDARY='"${REALM_SECONDARY}"
fi

cat >"${GENERATED_DIR}/kustomization.yaml" <<EOF
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization

namespace: unified-secureapp

resources:
  - ../base

secretGenerator:
  - name: secureapp-secrets
    literals:
${SECRET_LITERALS}

configMapGenerator:
  - name: collector-config
    behavior: replace
    files:
      - otelcol-config.yaml=collector-otelcol-config.yaml
  - name: secureapp-config-shared
    literals:
${SHARED_CONFIG_LITERALS}
      - ATTACK_ENABLED_SCENARIOS=${ATTACK_ENABLED_SCENARIOS}
      - ATTACK_LOOP_START_DELAY_SECONDS=${ATTACK_LOOP_START_DELAY_SECONDS}
      - WORKSPACE_SYNC_ENABLED=${WORKSPACE_SYNC_ENABLED}
      - DEPLOY_ENV=${DEPLOY_ENV}
      - FLAGD_HOST=${FLAGD_HOST}
      - FLAGD_OFREP_PORT=${FLAGD_OFREP_PORT}
      - FLAG_CHECK_INTERVAL=${FLAG_CHECK_INTERVAL}
      - LOADGEN_PACE=${LOADGEN_PACE}
  - name: datagen-scripts
    behavior: replace
    files:
      - loadgen.sh
      - loadgen-entries.sh
      - datagen-once.sh
  - name: secureapp-config-java
    literals:
      - SERVICE_NAME=${JAVA_SERVICE_NAME}
      - OTEL_RESOURCE_ATTRIBUTES=${JAVA_OTEL_RESOURCE_ATTRIBUTES}
      - OTEL_SERVICE_NAMESPACE=${JAVA_OTEL_SERVICE_NAMESPACE}
      - LOADGEN_ENABLED=${JAVA_BUILTIN_LOADGEN_ENABLED}
      - SHIPPING_ADDR=${JAVA_SHIPPING_ADDR}
      - SHIPPING_API=${JAVA_SHIPPING_API}
      - VA_RUNTIME_MODE=${VA_RUNTIME_MODE}
      - VA_STAGGER_INTERVAL_SECONDS=${VA_STAGGER_INTERVAL_SECONDS}
  - name: secureapp-config-python
    literals:
      - SERVICE_NAME=${PYTHON_SERVICE_NAME}
      - DEPLOY_ENV=${DEPLOY_ENV}
      - OTEL_RESOURCE_ATTRIBUTES=${PYTHON_OTEL_RESOURCE_ATTRIBUTES}
      - SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY=${SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY}
      - SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL=${PYTHON_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL}
      - VA_RUNTIME_MODE=${VA_RUNTIME_MODE}
      - VA_STAGGER_INTERVAL_SECONDS=${VA_STAGGER_INTERVAL_SECONDS}
  - name: secureapp-config-node
    literals:
      - SERVICE_NAME=${NODE_SERVICE_NAME}
      - DEPLOY_ENV=${DEPLOY_ENV}
      - OTEL_RESOURCE_ATTRIBUTES=${NODE_OTEL_RESOURCE_ATTRIBUTES}
      - SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY=${SPLUNK_SECUREAPP_DEPENDENCY_INITIAL_DELAY}
      - SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL=${NODE_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL}

images:
  - name: secureapp-java-app
    newName: ${IMAGE_REGISTRY}/java-app
    newTag: ${IMAGE_TAG}
  - name: secureapp-python-app
    newName: ${IMAGE_REGISTRY}/python-app
    newTag: ${IMAGE_TAG}
  - name: secureapp-node-app
    newName: ${IMAGE_REGISTRY}/node-app
    newTag: ${IMAGE_TAG}
  - name: secureapp-loadgen-runner
    newName: ${IMAGE_REGISTRY}/loadgen-runner
    newTag: ${IMAGE_TAG}

patches:
  - path: patch-java-service.yaml
  - path: patch-python-service.yaml
  - path: patch-node-service.yaml
EOF

if $DUAL_REALM_ENABLED; then
  cat >"${GENERATED_DIR}/patch-collector-dual-realm.yaml" <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: collector
spec:
  template:
    spec:
      containers:
        - name: collector
          env:
            - name: SPLUNK_ACCESS_TOKEN_SECONDARY
              valueFrom:
                secretKeyRef:
                  name: secureapp-secrets
                  key: INGEST_TOKEN_SECONDARY
EOF
  cat >>"${GENERATED_DIR}/kustomization.yaml" <<EOF
  - path: patch-collector-dual-realm.yaml
EOF
fi

write_service_patch() {
  local file="$1" name="$2" port="$3"
  cat >"${GENERATED_DIR}/${file}" <<EOF
apiVersion: v1
kind: Service
metadata:
  name: ${name}
spec:
  type: ${APP_SERVICE_TYPE}
  ports:
    - name: http
      port: 8080
      targetPort: http
EOF
  if [[ "${APP_SERVICE_TYPE}" == "NodePort" ]]; then
    cat >>"${GENERATED_DIR}/${file}" <<EOF
      nodePort: ${port}
EOF
  fi
}

write_service_patch patch-java-service.yaml app-java "${JAVA_APP_NODE_PORT}"
write_service_patch patch-python-service.yaml app-python "${PYTHON_APP_NODE_PORT}"
write_service_patch patch-node-service.yaml app-node "${NODE_APP_NODE_PORT}"

case "${DATAGEN_MODE}" in
  once)
    cat >"${GENERATED_DIR}/patch-delete-datagen-loops.yaml" <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: datagen-python-loop
$patch: delete
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: datagen-node-loop
$patch: delete
EOF
    echo "  - path: patch-delete-datagen-loops.yaml" >>"${GENERATED_DIR}/kustomization.yaml"
    ;;
  loop)
    cat >"${GENERATED_DIR}/patch-delete-datagen-jobs.yaml" <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: datagen-java-once
$patch: delete
---
apiVersion: batch/v1
kind: Job
metadata:
  name: datagen-python-once
$patch: delete
---
apiVersion: batch/v1
kind: Job
metadata:
  name: datagen-node-once
$patch: delete
EOF
    echo "  - path: patch-delete-datagen-jobs.yaml" >>"${GENERATED_DIR}/kustomization.yaml"
    log "DATAGEN_MODE=loop — java in-container; python_attack=${PYTHON_ATTACK_DATAGEN_ENABLED} node_attack=${NODE_ATTACK_DATAGEN_ENABLED}"
    ;;
  off)
    cat >"${GENERATED_DIR}/patch-delete-all-datagen.yaml" <<'EOF'
apiVersion: batch/v1
kind: Job
metadata:
  name: datagen-java-once
$patch: delete
---
apiVersion: batch/v1
kind: Job
metadata:
  name: datagen-python-once
$patch: delete
---
apiVersion: batch/v1
kind: Job
metadata:
  name: datagen-node-once
$patch: delete
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: datagen-python-loop
$patch: delete
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: datagen-node-loop
$patch: delete
EOF
    echo "  - path: patch-delete-all-datagen.yaml" >>"${GENERATED_DIR}/kustomization.yaml"
    ;;
  *)
    die "Invalid DATAGEN_MODE='${DATAGEN_MODE}' (use off, once, or loop)"
    ;;
esac

write_attack_datagen_patches

if $USE_K3D; then
  cat >"${GENERATED_DIR}/patch-apps-k3d.yaml" <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-java
spec:
  template:
    spec:
      containers:
        - name: app
          imagePullPolicy: Never
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-python
spec:
  template:
    spec:
      containers:
        - name: app
          imagePullPolicy: Never
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-node
spec:
  template:
    spec:
      containers:
        - name: app
          imagePullPolicy: Never
EOF
  if [[ "${DATAGEN_MODE}" == "loop" ]]; then
    if datagen_lang_enabled "${PYTHON_ATTACK_DATAGEN_ENABLED}"; then
      cat >>"${GENERATED_DIR}/patch-apps-k3d.yaml" <<'EOF'
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: datagen-python-loop
spec:
  template:
    spec:
      initContainers:
        - name: wait-for-stack
          imagePullPolicy: Never
      containers:
        - name: datagen
          imagePullPolicy: Never
EOF
    fi
    if datagen_lang_enabled "${NODE_ATTACK_DATAGEN_ENABLED}"; then
      cat >>"${GENERATED_DIR}/patch-apps-k3d.yaml" <<'EOF'
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: datagen-node-loop
spec:
  template:
    spec:
      initContainers:
        - name: wait-for-stack
          imagePullPolicy: Never
      containers:
        - name: datagen
          imagePullPolicy: Never
EOF
    fi
  fi
  echo "  - path: patch-apps-k3d.yaml" >>"${GENERATED_DIR}/kustomization.yaml"
fi

cat >>"${GENERATED_DIR}/kustomization.yaml" <<EOF

generatorOptions:
  disableNameSuffixHash: true
EOF

log "Generated overlay: ${GENERATED_DIR}/kustomization.yaml"
if $DUAL_REALM_ENABLED; then
  log "REALM=${REALM} + REALM_SECONDARY=${REALM_SECONDARY} (dual-realm fan-out enabled)"
else
  log "REALM=${REALM} (single realm)"
fi
log "DEPLOY_ENV=${DEPLOY_ENV} scan_interval=${SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL_SECONDS}s (node=${NODE_SPLUNK_SECUREAPP_DEPENDENCY_SCAN_INTERVAL}ms)"
log "JAVA=${JAVA_SERVICE_NAME} PYTHON=${PYTHON_SERVICE_NAME} NODE=${NODE_SERVICE_NAME}"
log "Loadgen DATAGEN_MODE=${DATAGEN_MODE} java_builtin=${JAVA_BUILTIN_LOADGEN_ENABLED} python_attack=${PYTHON_ATTACK_DATAGEN_ENABLED} node_attack=${NODE_ATTACK_DATAGEN_ENABLED} FLAGD_HOST=${FLAGD_HOST:-<unset>} LOADGEN_PACE=${LOADGEN_PACE:-<flagd>}"

if $DO_SKIP_DEPLOY; then
  log "Skipping kubectl apply (--skip-deploy)"
  exit 0
fi

kubectl_cluster_ready || die "kubectl cannot reach cluster"

log "Applying manifests..."
kubectl apply -k "${GENERATED_DIR}"
prune_disabled_attack_datagen

log "Waiting for collector..."
kubectl -n unified-secureapp rollout status deployment/collector --timeout=180s
for app in app-java app-python app-node; do
  log "Waiting for ${app}..."
  kubectl -n unified-secureapp rollout status deployment/"${app}" --timeout=180s
done

if [[ "${DATAGEN_MODE}" == "loop" ]]; then
  if datagen_lang_enabled "${PYTHON_ATTACK_DATAGEN_ENABLED}"; then
    kubectl -n unified-secureapp rollout status deployment/datagen-python-loop --timeout=60s || true
  fi
  if datagen_lang_enabled "${NODE_ATTACK_DATAGEN_ENABLED}"; then
    kubectl -n unified-secureapp rollout status deployment/datagen-node-loop --timeout=60s || true
  fi
elif [[ "${DATAGEN_MODE}" == "once" ]]; then
  kubectl -n unified-secureapp wait --for=condition=complete job/datagen-java-once --timeout=120s || true
  kubectl -n unified-secureapp logs job/datagen-java-once || true
  if datagen_lang_enabled "${PYTHON_ATTACK_DATAGEN_ENABLED}"; then
    kubectl -n unified-secureapp wait --for=condition=complete job/datagen-python-once --timeout=120s || true
    kubectl -n unified-secureapp logs job/datagen-python-once || true
  fi
  if datagen_lang_enabled "${NODE_ATTACK_DATAGEN_ENABLED}"; then
    kubectl -n unified-secureapp wait --for=condition=complete job/datagen-node-once --timeout=120s || true
    kubectl -n unified-secureapp logs job/datagen-node-once || true
  fi
fi

log "Deploy complete."
log "  Java:   curl http://localhost:${JAVA_APP_NODE_PORT}/health"
log "  Python: curl http://localhost:${PYTHON_APP_NODE_PORT}/health"
log "  Node:   curl http://localhost:${NODE_APP_NODE_PORT}/health"
log "  Splunk service.name: ${JAVA_SERVICE_NAME} / ${PYTHON_SERVICE_NAME} / ${NODE_SERVICE_NAME}"
log "  Status: ./status.sh"
log "  Teardown: ./teardown.sh"
