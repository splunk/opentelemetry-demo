#!/usr/bin/env bash
# Single-pass datagen — fire all enabled endpoints once (DATAGEN_MODE=once).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=loadgen-entries.sh
source "${SCRIPT_DIR}/loadgen-entries.sh"

if [[ -n "${APP_BASE_URL:-}" ]]; then
  _base="${APP_BASE_URL#http://}"
  _base="${_base#https://}"
  ATTACK_HOST="${ATTACK_HOST:-${_base%%/*}}"
fi

HOST="${ATTACK_HOST:-localhost:8080}"
BASE="http://${HOST}"
LOADGEN_LANGUAGE="${LOADGEN_LANGUAGE:-java}"

curl_one() {
  local path="$1"
  local label="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 "${BASE}${path}" 2>/dev/null || echo "ERR")
  printf "  %-40s %s\n" "${label}" "${code}"
}

build_all_entries

echo "=== Datagen once $(date '+%Y-%m-%d %H:%M:%S') lang=${LOADGEN_LANGUAGE} target=${BASE} ==="

for entry in "${ALL_ENTRIES[@]}"; do
  IFS='|' read -r path label _rest <<< "${entry}"
  curl_one "${path}" "${label}"
done

echo "=== Done ==="
