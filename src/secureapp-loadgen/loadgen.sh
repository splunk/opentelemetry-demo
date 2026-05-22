#!/usr/bin/env bash
# SecureApp attack loadgen — fires each vulnerability endpoint on its own
# independent schedule, never at the same time.  Pace controlled by flagd
# feature flag "secureappAttack" (minimal | targeted | max).
#
# Shipping calls run at a fixed ~4 min interval regardless of pace to
# keep the api-service → shipping trace link alive.
#
# Environment variables:
#   ATTACK_HOST        Target host:port (default: localhost:8080)
#   FLAGD_HOST         Flagd hostname (default: flagd)
#   FLAGD_OFREP_PORT   Flagd OFREP port (default: 8016)

set -euo pipefail

HOST="${ATTACK_HOST:-localhost:8080}"
FLAGD_HOST="${FLAGD_HOST:-flagd}"
FLAGD_PORT="${FLAGD_OFREP_PORT:-8016}"
BASE="http://${HOST}"
FLAGD_URL="http://${FLAGD_HOST}:${FLAGD_PORT}/ofrep/v1/evaluate/flags/secureappAttack"

CURRENT_PACE=""

# --- Interval definitions per pace ---
# Format: path|label|minimal_min|minimal_max|targeted_min|targeted_max|max_min|max_max
#
# targeted = minimal background + SQLi & Log4Shell every ~10-15 min
# (the two most recognizable attack signatures)
SHIPPING_ENTRY="/api/v1/shipping/estimate|Shipping quote|180|300|180|300|180|300"

ATTACK_ENTRIES=(
  "/health|Health check|7200|14400|7200|14400|120|300"
  "/api/v1/documents/convert|RCE (Struts2 CVE-2017-5638)|10800|28800|10800|28800|180|600"
  "/api/v1/users/search|SQL Injection|14400|36000|600|900|240|600"
  "/api/v1/links/preview|SSRF (cloud metadata)|18000|39600|18000|39600|180|540"
  "/api/v1/auth/login|Log4Shell (CVE-2021-44228)|21600|43200|600|900|240|720"
  "/api/v1/sessions/import|Deserialization (CVE-2020-1714)|25200|43200|25200|43200|300|720"
  "/api/v1/workspace/sync|All attacks combined|28800|43200|28800|43200|300|900"
)

# Combine into single array (shipping first)
ALL_ENTRIES=("$SHIPPING_ENTRY" "${ATTACK_ENTRIES[@]}")
NUM_ENDPOINTS=${#ALL_ENTRIES[@]}

# Random integer in [min, max]
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

# Query flagd for current pace. Falls back to "minimal" if unreachable.
get_pace() {
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
  echo "minimal"
}

# Get min/max interval for an endpoint given current pace
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

  http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "${BASE}${path}" 2>/dev/null) || true
  if [[ -z "$http_code" ]] || [[ "$http_code" == "000" ]]; then
    status="ERR"
  else
    status="$http_code"
  fi
  printf "[%s] %-40s %s  (pace=%s)\n" "$(date '+%Y-%m-%d %H:%M:%S')" "${label}" "${status}" "$CURRENT_PACE"
}

print_schedule() {
  echo "--- Schedule (pace=$CURRENT_PACE) ---"
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

# --- Initialize ---
echo "SecureApp loadgen starting"
CURRENT_PACE=$(get_pace)
echo "  flagd pace: $CURRENT_PACE"
echo "  flagd url:  $FLAGD_URL"

# --- Immediate first shot: fire one random attack endpoint ---
# Skip index 0 (shipping) and 1 (health) — pick from real attacks (indices 2-7)
initial_idx=$(rand_between 2 $((NUM_ENDPOINTS - 1)))
echo ""
echo "=== Initial attack ==="
fire_endpoint "$initial_idx"
echo ""

# --- Schedule subsequent fires based on pace ---
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

# --- Main loop ---
fire_count=0
last_flag_check=$(date +%s)
FLAG_CHECK_INTERVAL=60  # Re-check flagd every 60 seconds

while true; do
  # Find endpoint with earliest next_fire
  earliest_idx=0
  earliest_time=${next_fire[0]}
  for i in $(seq 1 $((NUM_ENDPOINTS - 1))); do
    if (( next_fire[i] < earliest_time )); then
      earliest_idx=$i
      earliest_time=${next_fire[i]}
    fi
  done

  # Sleep until it's time
  now=$(date +%s)
  wait_secs=$((earliest_time - now))
  if (( wait_secs > 0 )); then
    sleep "$wait_secs"
  fi

  # Check flagd for pace changes (at most every FLAG_CHECK_INTERVAL seconds)
  now=$(date +%s)
  if (( now - last_flag_check >= FLAG_CHECK_INTERVAL )); then
    new_pace=$(get_pace)
    last_flag_check=$now
    if [[ "$new_pace" != "$CURRENT_PACE" ]]; then
      echo "*** Pace changed: $CURRENT_PACE -> $new_pace ***"
      CURRENT_PACE="$new_pace"
      # Reschedule all attack endpoints (not shipping) with new intervals
      for i in $(seq 1 $((NUM_ENDPOINTS - 1))); do
        read -r mn mx <<< "$(get_intervals "${ALL_ENTRIES[$i]}" "$CURRENT_PACE")"
        next_fire[$i]=$(( now + $(rand_between "$mn" "$mx") ))
      done
      print_schedule
    fi
  fi

  # Fire
  fire_endpoint "$earliest_idx"
  hit_count[$earliest_idx]=$(( hit_count[earliest_idx] + 1 ))
  fire_count=$((fire_count + 1))

  # Reschedule fired endpoint
  read -r mn mx <<< "$(get_intervals "${ALL_ENTRIES[$earliest_idx]}" "$CURRENT_PACE")"
  next_fire[$earliest_idx]=$(( $(date +%s) + $(rand_between "$mn" "$mx") ))

  # Periodic summary
  summary_interval=$( [[ "$CURRENT_PACE" == "minimal" ]] && echo 5 || echo 20 )
  if (( fire_count % summary_interval == 0 )); then
    print_schedule
  fi
done
