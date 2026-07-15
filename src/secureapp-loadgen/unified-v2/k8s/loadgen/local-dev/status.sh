#!/bin/bash
# Quick status for the unified SecureApp k8s stack.
set -euo pipefail

NS=unified-secureapp

echo "=== kubectl context ==="
kubectl config current-context 2>&1 || { echo "kubectl not configured"; exit 1; }

echo ""
echo "=== namespace ${NS} ==="
if ! kubectl get namespace "${NS}" >/dev/null 2>&1; then
  echo "Namespace ${NS} not found. Run: ./deploy.sh --create-k3d"
  exit 1
fi

echo ""
echo "=== pods ==="
kubectl -n "${NS}" get pods -o wide 2>&1

echo ""
echo "=== deployments ==="
kubectl -n "${NS}" get deploy 2>&1

echo ""
echo "=== services ==="
kubectl -n "${NS}" get svc 2>&1

echo ""
echo "=== recent events ==="
kubectl -n "${NS}" get events --sort-by='.lastTimestamp' 2>&1 | tail -12

missing=0
for dep in app-java app-python app-node collector; do
  if ! kubectl -n "${NS}" get deployment "${dep}" >/dev/null 2>&1; then
    echo ""
    echo "MISSING deployment: ${dep}"
    missing=1
  fi
done

if [[ "${missing}" -eq 1 ]]; then
  echo ""
  echo "Fix: cd k8s && ./deploy.sh"
  exit 1
fi

ready=$(kubectl -n "${NS}" get pods -l 'app.kubernetes.io/name in (app-java,app-python,app-node,collector)' \
  --field-selector=status.phase=Running --no-headers 2>/dev/null | wc -l | tr -d ' ')
if [[ "${ready}" -lt 4 ]]; then
  echo ""
  echo "Not all app/collector pods Running. Check: kubectl -n ${NS} describe pod"
  exit 1
fi

echo ""
echo "OK — java, python, node apps and collector running."
