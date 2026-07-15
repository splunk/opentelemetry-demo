#!/bin/bash
# Remove unified-secureapp from the current kubectl context.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GENERATED_DIR="${SCRIPT_DIR}/generated"

if [[ -f "${GENERATED_DIR}/kustomization.yaml" ]]; then
  kubectl delete -k "${GENERATED_DIR}" --ignore-not-found
else
  kubectl delete namespace unified-secureapp --ignore-not-found
fi

echo "[k8s/teardown] Removed unified-secureapp"
