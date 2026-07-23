#!/bin/bash
# Entrypoint: start the Java secureapp test app, then launch the loadgen.
set -euo pipefail

# JAVA_TOOL_OPTIONS is set by k8s manifest (includes -javaagent and argento flags).
# When running standalone (docker run), set JAVA_TOOL_OPTIONS in env or it runs without agent.
echo "Starting SecureApp test app..."
echo "  JAVA_TOOL_OPTIONS=${JAVA_TOOL_OPTIONS:-<not set>}"
java -jar /app/java-secureapp-test-app.jar &
JAVA_PID=$!

# Wait for the app to become healthy
echo "Waiting for health check..."
retries=0
HEALTH_PORT="${SERVER_PORT:-8080}"
until curl -sf "http://localhost:${HEALTH_PORT}/health" > /dev/null 2>&1; do
  retries=$((retries + 1))
  if [ $retries -ge 60 ]; then
    echo "ERROR: App failed to start after 120s"
    exit 1
  fi
  sleep 2
done
echo "App is healthy."

# Wait for shipping service before starting loadgen (skip if SHIPPING_ADDR not set)
SHIPPING_ADDR="${SHIPPING_ADDR:-}"
if [ -n "$SHIPPING_ADDR" ]; then
  echo "Waiting for shipping service at ${SHIPPING_ADDR}..."
  retries=0
  until curl -sf "${SHIPPING_ADDR}/health" -o /dev/null --max-time 5 2>/dev/null; do
    retries=$((retries + 1))
    if [ $retries -ge 90 ]; then
      echo "WARNING: Shipping service not ready after 180s, starting loadgen anyway"
      break
    fi
    sleep 2
  done
else
  echo "SHIPPING_ADDR not set, skipping shipping wait."
fi
echo "Starting loadgen..."

# Launch the loadgen in background
/app/loadgen.sh &
LOADGEN_PID=$!

# If Java dies, kill loadgen and exit
trap "kill $LOADGEN_PID 2>/dev/null; exit" EXIT
wait $JAVA_PID
