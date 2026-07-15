#!/usr/bin/env bash
# Per-language attack entries for shared loadgen.
# Format: path|label|minimal_min|minimal_max|targeted_min|targeted_max|max_min|max_max

path_to_scenario() {
  case "$1" in
    /api/v1/documents/convert) echo rce ;;
    /api/v1/links/preview) echo ssrf ;;
    /api/v1/users/search) echo sqli ;;
    /api/v1/auth/login) echo log4j ;;
    /api/v1/sessions/import) echo deserial ;;
    /api/v1/workspace/sync) echo workspace ;;
    *) echo "" ;;
  esac
}

scenario_enabled() {
  local scen="$1"
  local filter="${ATTACK_ENABLED_SCENARIOS:-}"
  if [[ -z "${filter}" ]]; then
    return 0
  fi
  echo "${filter}" | tr ',' '\n' | tr '[:upper:]' '[:lower:]' | tr -d ' ' | grep -qx "${scen}"
}

workspace_sync_enabled() {
  case "$(echo "${WORKSPACE_SYNC_ENABLED:-false}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

load_schedule_entries() {
  case "${LOADGEN_LANGUAGE:-java}" in
    python)
      SCHEDULE_ENTRIES=(
        "/health|Health check|120|240|120|240|120|240"
        "/api/v1/documents/convert|RCE/SSTI (Jinja2 CVE-2024-22195)|10800|28800|10800|28800|180|600"
        "/api/v1/users/search|SQL Injection (SQLAlchemy CVE-2022-21698)|14400|36000|600|900|240|600"
        "/api/v1/links/preview|SSRF (urllib3 CVE-2021-33503)|18000|39600|18000|39600|180|540"
        "/api/v1/auth/login|PyYAML unsafe load (CVE-2020-14343)|21600|43200|600|900|240|720"
        "/api/v1/sessions/import|Deserialization (Pillow CVE-2022-45199)|25200|43200|25200|43200|300|720"
        "/api/v1/workspace/sync|All attacks combined|28800|43200|28800|43200|300|900"
      )
      ;;
    node)
      SCHEDULE_ENTRIES=(
        "/health|Health check|120|240|120|240|120|240"
        "/api/v1/documents/convert|RCE/SSTI (ejs CVE-2022-29078)|10800|28800|10800|28800|180|600"
        "/api/v1/users/search|SQL Injection (better-sqlite3 CVE-2022-25897)|14400|36000|600|900|240|600"
        "/api/v1/links/preview|SSRF (axios CVE-2021-3749)|18000|39600|18000|39600|180|540"
        "/api/v1/auth/login|js-yaml unsafe load (CVE-2020-14343)|21600|43200|600|900|240|720"
        "/api/v1/sessions/import|Deserialization (node-serialize CVE-2017-5941)|25200|43200|25200|43200|300|720"
        "/api/v1/workspace/sync|All attacks combined|28800|43200|28800|43200|300|900"
      )
      ;;
    java|*)
      SCHEDULE_ENTRIES=(
        "/health|Health check|120|240|120|240|120|240"
        "/api/v1/documents/convert|RCE (Struts2 CVE-2017-5638)|10800|28800|10800|28800|180|600"
        "/api/v1/users/search|SQL Injection|14400|36000|600|900|240|600"
        "/api/v1/links/preview|SSRF (cloud metadata)|18000|39600|18000|39600|180|540"
        "/api/v1/auth/login|Log4Shell (CVE-2021-44228)|21600|43200|600|900|240|720"
        "/api/v1/sessions/import|Deserialization (CVE-2020-1714)|25200|43200|25200|43200|300|720"
        "/api/v1/workspace/sync|All attacks combined|28800|43200|28800|43200|300|900"
      )
      ;;
  esac
}

build_all_entries() {
  load_schedule_entries
  ALL_ENTRIES=()
  local entry path label _intervals scen
  for entry in "${SCHEDULE_ENTRIES[@]}"; do
    IFS='|' read -r path label _intervals <<< "${entry}"
    if [[ "${path}" == "/api/v1/workspace/sync" ]] && ! workspace_sync_enabled; then
      continue
    fi
    scen=$(path_to_scenario "${path}")
    if [[ -n "${scen}" && "${scen}" != "workspace" ]] && ! scenario_enabled "${scen}"; then
      continue
    fi
    ALL_ENTRIES+=("${entry}")
  done
  NUM_ENDPOINTS=${#ALL_ENTRIES[@]}
}
