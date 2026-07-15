#!/bin/bash
# Generate Splunk OTel collector config (single or dual-realm fan-out).
# Sourced by deploy.sh — do not run directly.

splunk_realm_ingest_url() {
  printf 'https://ingest.%s.signalfx.com' "$1"
}

splunk_realm_api_url() {
  printf 'https://api.%s.signalfx.com' "$1"
}

# write_collector_otel_config <output-file> <dual_realm:true|false> <secondary_realm>
write_collector_otel_config() {
  local out="$1"
  local dual="$2"
  local realm_secondary="$3"

  local secondary_ingest secondary_api
  if [[ "${dual}" == "true" ]]; then
    secondary_ingest="$(splunk_realm_ingest_url "${realm_secondary}")"
    secondary_api="$(splunk_realm_api_url "${realm_secondary}")"
  fi

  local trace_exporters metric_exporters metric_internal_exporters
  local logs_exporters secureapp_logs_exporters
  local secondary_exporters=""

  if [[ "${dual}" == "true" ]]; then
    secondary_exporters=$(cat <<EOF

      otlp_http/secondary:
        traces_endpoint: "${secondary_ingest}/v2/trace/otlp"
        headers:
          "X-SF-Token": "\${SPLUNK_ACCESS_TOKEN_SECONDARY}"
      signalfx/secondary:
        access_token: "\${SPLUNK_ACCESS_TOKEN_SECONDARY}"
        api_url: "${secondary_api}"
        ingest_url: "${secondary_ingest}"
        sync_host_metadata: true
      otlp_http/secureapp/secondary:
        logs_endpoint: "${secondary_ingest}/v3/event"
        headers:
          "X-SF-TOKEN": "\${SPLUNK_ACCESS_TOKEN_SECONDARY}"
          "X-Splunk-Instrumentation-Library": secureapp
EOF
)
    trace_exporters="[debug, otlp_http, otlp_http/secondary]"
    metric_exporters="[debug, signalfx, signalfx/secondary]"
    metric_internal_exporters="[signalfx, signalfx/secondary]"
    logs_exporters="[debug, signalfx, signalfx/secondary]"
    secureapp_logs_exporters="[debug, otlp_http/secureapp, signalfx, otlp_http/secureapp/secondary, signalfx/secondary]"
  else
    trace_exporters="[debug, otlp_http]"
    metric_exporters="[debug, signalfx]"
    metric_internal_exporters="[signalfx]"
    logs_exporters="[debug, signalfx]"
    secureapp_logs_exporters="[debug, otlp_http/secureapp, signalfx]"
  fi

  cat >"${out}" <<EOF
extensions:
  headers_setter:
    headers:
      - action: upsert
        key: X-SF-TOKEN
        from_context: X-SF-TOKEN
        default_value: "\${SPLUNK_ACCESS_TOKEN}"
  health_check:
    endpoint: "\${SPLUNK_LISTEN_INTERFACE}:13133"

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "\${SPLUNK_LISTEN_INTERFACE}:4317"
      http:
        endpoint: "\${SPLUNK_LISTEN_INTERFACE}:4318"
  host_metrics:
    collection_interval: 10s
    root_path: /hostfs
    scrapers:
      cpu:
      disk:
      filesystem:
        include_mount_points:
          match_type: strict
          mount_points:
            - "/"
      memory:
      network:
      load:
      paging:
      processes:
  kubeletstats:
    collection_interval: 10s
    auth_type: serviceAccount
    endpoint: \${env:K8S_NODE_IP}:10250
    insecure_skip_verify: true
    metric_groups:
      - container
      - pod
      - node
    extra_metadata_labels:
      - container.id
  prometheus/internal:
    config:
      scrape_configs:
        - job_name: otel-collector
          scrape_interval: 10s
          static_configs:
            - targets: ["0.0.0.0:8888"]
          metric_relabel_configs:
            - source_labels: [__name__]
              regex: "promhttp_metric_handler_errors.*"
              action: drop
            - source_labels: [__name__]
              regex: "otelcol_processor_batch_.*"
              action: drop

processors:
  batch:
    metadata_keys:
      - X-SF-Token
  memory_limiter:
    check_interval: 2s
    limit_mib: \${SPLUNK_MEMORY_LIMIT_MIB}
  resourcedetection:
    detectors: [system]
    override: true
  resource/add_mode:
    attributes:
      - action: insert
        value: "agent"
        key: otelcol.service.mode

exporters:
  otlp_http:
    traces_endpoint: "\${SPLUNK_INGEST_URL}/v2/trace/otlp"
    headers:
      "X-SF-Token": "\${SPLUNK_ACCESS_TOKEN}"
    auth:
      authenticator: headers_setter
  signalfx:
    access_token: "\${SPLUNK_ACCESS_TOKEN}"
    api_url: "\${SPLUNK_API_URL}"
    ingest_url: "\${SPLUNK_INGEST_URL}"
    sync_host_metadata: true
  otlp_http/secureapp:
    logs_endpoint: "\${SPLUNK_INGEST_URL}/v3/event"
    headers:
      "X-SF-TOKEN": "\${SPLUNK_ACCESS_TOKEN}"
      "X-Splunk-Instrumentation-Library": secureapp
  debug:
    verbosity: basic
${secondary_exporters}

connectors:
  routing/logs:
    default_pipelines: [logs]
    table:
      - context: log
        condition: instrumentation_scope.name == "secureapp"
        pipelines: [logs/secureapp]

service:
  extensions: [headers_setter, health_check]
  telemetry:
    logs:
      level: info
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: ${trace_exporters}
    metrics:
      receivers: [host_metrics, kubeletstats, otlp]
      processors: [memory_limiter, batch, resourcedetection]
      exporters: ${metric_exporters}
    metrics/internal:
      receivers: [prometheus/internal]
      processors: [memory_limiter, batch, resourcedetection, resource/add_mode]
      exporters: ${metric_internal_exporters}
    logs/split:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [routing/logs]
    logs:
      receivers: [routing/logs]
      exporters: ${logs_exporters}
    logs/secureapp:
      receivers: [routing/logs]
      processors: [memory_limiter, batch]
      exporters: ${secureapp_logs_exporters}
EOF
}
