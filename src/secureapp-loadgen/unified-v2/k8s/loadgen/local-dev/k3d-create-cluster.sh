#!/bin/bash
# Create a k3d cluster with localhost ports for all three SecureApp test apps.
set -euo pipefail

CLUSTER_NAME="${1:-secapp-default}"
JAVA_PORT="${JAVA_APP_NODE_PORT:-30080}"
PYTHON_PORT="${PYTHON_APP_NODE_PORT:-30081}"
NODE_PORT="${NODE_APP_NODE_PORT:-30082}"

if k3d cluster list | awk 'NR>1 {print $1}' | grep -qx "${CLUSTER_NAME}"; then
  echo "[k3d] Cluster '${CLUSTER_NAME}' already exists."
  echo "      Delete first: k3d cluster delete ${CLUSTER_NAME}"
  exit 1
fi

echo "[k3d] Creating cluster '${CLUSTER_NAME}'..."
echo "      localhost:${JAVA_PORT}   -> java   (NodePort)"
echo "      localhost:${PYTHON_PORT} -> python (NodePort)"
echo "      localhost:${NODE_PORT}   -> node   (NodePort)"

k3d cluster create "${CLUSTER_NAME}" \
  --agents 0 \
  -p "${JAVA_PORT}:${JAVA_PORT}@server:0" \
  -p "${PYTHON_PORT}:${PYTHON_PORT}@server:0" \
  -p "${NODE_PORT}:${NODE_PORT}@server:0"

echo ""
echo "[k3d] Cluster ready. Deploy with:"
echo "  cd k8s && cp values.env.example values.env   # set INGEST_TOKEN"
echo "  ./deploy.sh --create-k3d"
echo ""
echo "Then:"
echo "  curl http://localhost:${JAVA_PORT}/health"
echo "  curl http://localhost:${PYTHON_PORT}/health"
echo "  curl http://localhost:${NODE_PORT}/health"
