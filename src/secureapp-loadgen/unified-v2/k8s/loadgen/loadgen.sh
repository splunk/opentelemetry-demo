#!/usr/bin/env bash
# Shared SecureApp attack loadgen — independent per-endpoint schedules with flagd pace control.
# Schedule entries (path, label, intervals) live in loadgen-entries.sh per language.
#
# Environment variables:
#   ATTACK_HOST              Target host:port (default: localhost:8080)
#   APP_BASE_URL             Alternative to ATTACK_HOST (e.g. http://app-python:8080)
#   LOADGEN_LANGUAGE         java | python | node (default: java)
#   FLAGD_HOST               Flagd hostname (empty = use LOADGEN_PACE or minimal)
#   FLAGD_OFREP_PORT         Flagd OFREP port (default: 8016)
#   FLAG_CHECK_INTERVAL      Seconds between flagd polls (default: 60)
#   LOADGEN_PACE             Pace override: minimal | targeted | max
#   ATTACK_ENABLED_SCENARIOS Comma-separated filter: rce, ssrf, sqli, log4j, deserial
#   ATTACK_LOOP_START_DELAY_SECONDS  Sleep before scheduling (default: 0)
#   WORKSPACE_SYNC_ENABLED   Include /api/v1/workspace/sync when true/1/on

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
FLAGD_PORT="${FLAGD_OFREP_PORT:-8016}"
FLAG_CHECK_INTERVAL="${FLAG_CHECK_INTERVAL:-60}"
LOADGEN_LANGUAGE="${LOADGEN_LANGUAGE:-java}"
BASE="http://${HOST}"
if [[ -n "${FLAGD_HOST:-}" ]]; then
  FLAGD_URL="http://${FLAGD_HOST}:${FLAGD_PORT}/ofrep/v1/evaluate/flags/secureappAttack"
else
  FLAGD_URL=""
fi

CURRENT_PACE=""

rand_between() {
  local min=$1 max=$2
  echo $(( RANDOM % (max - min + 1) + min ))
}

fmt_duration() {
  local secs=$1
  if (( secs >= 86400 )); then
    echo "$((secs / 3600))h (~$((secs / 86400))d)"
  elif (( secs >= 3600 )); then
    echo "$((secs / 3600))h$((secs % 3600 / 60))m"
  else
    echo "$((secs / 60))m"
  fi
}

get_pace() {
  local override="${LOADGEN_PACE:-}"
  if [[ "${override}" == "max" || "${override}" == "targeted" || "${override}" == "minimal" ]]; then
    echo "${override}"
    return
  fi

  if [[ -z "${FLAGD_HOST:-}" ]]; then
    echo "${override:-minimal}"
    return
  fi

  local resp
  resp=$(curl -sf -X POST "$FLAGD_URL" \
    -H "Content-Type: application/json" \
    -d '{"context":{}}' \
    --max-time 3 2>/dev/null) || true

  if [[ -n "$resp" ]]; then
    local val
    val=$(echo "$resp" | sed -n 's/.*"value"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
    if [[ "$val" == "max" || "$val" == "targeted" || "$val" == "minimal" ]]; then
      echo "$val"
      return
    fi
  fi
  echo "${override:-minimal}"
}

get_intervals() {
  local entry=$1 pace=$2
  IFS='|' read -r _path _label min_min min_max tgt_min tgt_max max_min max_max <<< "$entry"
  case "$pace" in
    max)      echo "$max_min $max_max" ;;
    targeted) echo "$tgt_min $tgt_max" ;;
    *)        echo "$min_min $min_max" ;;
  esac
}

fire_endpoint() {
  local idx=$1
  IFS='|' read -r path label _rest <<< "${ALL_ENTRIES[$idx]}"

  local http_code
  http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE}${path}" 2>/dev/null) || true
  local status
  if [[ -z "$http_code" ]] || [[ "$http_code" == "000" ]]; then
    status="ERR"
  else
    status="$http_code"
  fi
  printf "[%s] %-40s %s  (pace=%s lang=%s)\n" \
    "$(date '+%Y-%m-%d %H:%M:%S')" "${label}" "${status}" "$CURRENT_PACE" "$LOADGEN_LANGUAGE"
}

print_schedule() {
  echo "--- Schedule (pace=$CURRENT_PACE lang=$LOADGEN_LANGUAGE) ---"
  local i label _rest mn mx next_at
  for i in $(seq 0 $((NUM_ENDPOINTS - 1))); do
    IFS='|' read -r _p label _rest <<< "${ALL_ENTRIES[$i]}"
    read -r mn mx <<< "$(get_intervals "${ALL_ENTRIES[$i]}" "$CURRENT_PACE")"
    next_at=$(date -d "@${next_fire[$i]}" '+%Y-%m-%d %H:%M' 2>/dev/null \
      || date -r "${next_fire[$i]}" '+%Y-%m-%d %H:%M' 2>/dev/null \
      || echo "?")
    printf "  %-40s every %s–%s  hits: %-4d  next: %s\n" \
      "$label" "$(fmt_duration $mn)" "$(fmt_duration $mx)" "${hit_count[$i]}" "$next_at"
  done
  echo ""
}

build_all_entries
if (( NUM_ENDPOINTS < 1 )); then
  echo "No loadgen endpoints enabled (check ATTACK_ENABLED_SCENARIOS / WORKSPACE_SYNC_ENABLED)" >&2
  exit 1
fi

echo "SecureApp loadgen starting (language=${LOADGEN_LANGUAGE})"
echo "  target: ${BASE}"
CURRENT_PACE=$(get_pace)
echo "  flagd pace: $CURRENT_PACE"
if [[ -n "${FLAGD_HOST:-}" ]]; then
  echo "  flagd url:  $FLAGD_URL"
else
  echo "  flagd:      disabled (LOADGEN_PACE=${LOADGEN_PACE:-minimal})"
fi

delay="${ATTACK_LOOP_START_DELAY_SECONDS:-0}"
if [[ "${delay}" =~ ^[0-9]+$ ]] && (( delay > 0 )); then
  echo "ATTACK_LOOP_START_DELAY_SECONDS=${delay}: sleeping before loadgen..."
  sleep "${delay}"
fi

initial_min=1
for i in $(seq 0 $((NUM_ENDPOINTS - 1))); do
  IFS='|' read -r path _l _r <<< "${ALL_ENTRIES[$i]}"
  if [[ "${path}" != "/health" ]]; then
    initial_min=$i
    break
  fi
done
initial_idx=$(rand_between "${initial_min}" $((NUM_ENDPOINTS - 1)))
echo ""
echo "=== Initial attack ==="
fire_endpoint "$initial_idx"
echo ""

now=$(date +%s)
declare -a next_fire
declare -a hit_count
for i in $(seq 0 $((NUM_ENDPOINTS - 1))); do
  read -r mn mx <<< "$(get_intervals "${ALL_ENTRIES[$i]}" "$CURRENT_PACE")"
  next_fire[$i]=$(( now + $(rand_between "$mn" "$mx") ))
  hit_count[$i]=0
done
hit_count[$initial_idx]=1

print_schedule

fire_count=0
last_flag_check=$(date +%s)

while true; do
  earliest_idx=0
  earliest_time=${next_fire[0]}
  for i in $(seq 1 $((NUM_ENDPOINTS - 1))); do
    if (( next_fire[i] < earliest_time )); then
      earliest_idx=$i
      earliest_time=${next_fire[i]}
    fi
  done

  now=$(date +%s)
  wait_secs=$((earliest_time - now))
  if (( wait_secs > 0 )); then
    sleep "$wait_secs"
  fi

  now=$(date +%s)
  if (( now - last_flag_check >= FLAG_CHECK_INTERVAL )); then
    new_pace=$(get_pace)
    last_flag_check=$now
    if [[ "$new_pace" != "$CURRENT_PACE" ]]; then
      echo "*** Pace changed: $CURRENT_PACE -> $new_pace ***"
      CURRENT_PACE="$new_pace"
      for i in $(seq 0 $((NUM_ENDPOINTS - 1))); do
        IFS='|' read -r path _l _r <<< "${ALL_ENTRIES[$i]}"
        if [[ "${path}" == "/health" ]]; then
          continue
        fi
        read -r mn mx <<< "$(get_intervals "${ALL_ENTRIES[$i]}" "$CURRENT_PACE")"
        next_fire[$i]=$(( now + $(rand_between "$mn" "$mx") ))
      done
      print_schedule
    fi
  fi

  fire_endpoint "$earliest_idx"
  hit_count[$earliest_idx]=$((hit_count[$earliest_idx] + 1))
  fire_count=$((fire_count + 1))

  read -r mn mx <<< "$(get_intervals "${ALL_ENTRIES[$earliest_idx]}" "$CURRENT_PACE")"
  next_fire[$earliest_idx]=$(( $(date +%s) + $(rand_between "$mn" "$mx") ))

  summary_interval=$( [[ "$CURRENT_PACE" == "minimal" ]] && echo 5 || echo 20 )
  if (( fire_count % summary_interval == 0 )); then
    print_schedule
  fi
done
