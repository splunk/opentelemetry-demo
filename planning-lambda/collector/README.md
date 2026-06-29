# Splunk OpenTelemetry Collector — Gateway Mode (Multi-Env Routing)

This directory holds the gateway-mode collector config that fronts the
`Planning_Init_Lambda` Lambda. A single EC2 instance runs the Splunk OTel
Collector, receives OTLP from one (or more) Lambdas in the same VPC, and
fans the telemetry out per-environment to the appropriate Splunk
Observability and Splunk Cloud (HEC) backends.

The K8s planning service in each cluster passes its environment name to
the Lambda; the Lambda stamps `deployment.environment = "<env>-lambda"`
on its spans/metrics/logs; the gateway promotes that signal attribute to
a resource attribute and routes telemetry via the `routing` connector to
four exporter sets — one per env plus a `default` catch-all.

```
+------------------+         +------------------+         +-----------------------+
|  K8s planning    | --HTTP--> |  AWS Lambda     | --OTLP--> |  EC2 gateway        |
|  (per cluster)   |  +env    |  Planning_Init_Lambda  |  :4317   |  splunk-otel-       |
|                  |          |  stamps env     |          |  collector          |
+------------------+          +------------------+          +-----------------------+
                                                                       |
                                routing connector (per signal: traces, metrics, logs)
                                matches resource.attributes["deployment.environment"]
                                                                       |
        +----------------------------+----------------------------+----------------------------+
        |                            |                            |                            |
   dev-astronomy-               astronomy-shop-             astronomy-shop-               (default)
   shop-demo-lambda             eu-lambda                  us-lambda                     unmatched
        |                            |                            |                            |
   otlp_http/dev                otlp_http/eu               otlp_http/us                 otlp_http/default
   splunk_hec/dev               splunk_hec/eu              splunk_hec/us                splunk_hec/default
```

## Files in this directory

| File | Purpose |
|---|---|
| `gateway-config.yaml` | Live multi-env collector config |
| `gateway-config.yaml.bak` | Original single-org config (delete post-validation) |
| `gateway-config-cloudwatch.yaml` | Older single-org variant with CloudWatch Logs receiver (multi-env rewrite is a TODO) |
| `env.template` | Reference template for the 20 per-env env vars |
| `README.md` | This file |

## Prerequisites

- EC2 instance in the same VPC and subnet as the Lambda
- Security group allowing inbound TCP **4317** (OTLP/gRPC), **4318** (OTLP/HTTP), **13133** (health check) from the Lambda security group
- Outbound HTTPS **443** to Splunk Observability and Splunk Cloud HEC
- Splunk Observability access tokens and realms for each target org (one per env plus default)
- Splunk Cloud HEC endpoints, tokens, and indexes for each target org

## Setup

### 1. Install the Splunk OTel Collector

```bash
curl -sSL https://dl.signalfx.com/splunk-otel-collector.sh > /tmp/splunk-otel-collector.sh
sudo sh /tmp/splunk-otel-collector.sh \
  --realm <bootstrap-realm> \
  --access-token <bootstrap-access-token> \
  --mode gateway
```

The `--realm` / `--access-token` flags here are used by the installer to
write a baseline `splunk-otel-collector.conf`. The real per-env values
overwrite them in the next step.

### 2. Install the multi-env config

```bash
sudo cp gateway-config.yaml /etc/otel/collector/gateway_config.yaml
sudo chown splunk-otel-collector:splunk-otel-collector /etc/otel/collector/gateway_config.yaml
sudo chmod 0644 /etc/otel/collector/gateway_config.yaml
```

Confirm the env file already points the systemd unit at this path:

```bash
sudo grep ^SPLUNK_CONFIG= /etc/otel/collector/splunk-otel-collector.conf
# expected: SPLUNK_CONFIG=/etc/otel/collector/gateway_config.yaml
```

If you prefer to keep the old config in place, install the new file
under a different name and update `SPLUNK_CONFIG` to point at it.
That makes rollback as simple as flipping the variable.

### 3. Populate the env file

The collector reads vars from `/etc/otel/collector/splunk-otel-collector.conf`.
Append the 20 multi-env vars from `env.template` to that file (or copy
the template and append it):

```bash
sudo tee -a /etc/otel/collector/splunk-otel-collector.conf >/dev/null < env.template
sudo nano /etc/otel/collector/splunk-otel-collector.conf
# Replace every <placeholder> with the real value for each env.
```

Required vars (5 per env, 20 total):

| Var (per env) | Description |
|---|---|
| `SPLUNK_REALM_<ENV>` | Splunk Observability realm (e.g. `us0`, `us1`, `eu0`) |
| `SPLUNK_TOKEN_<ENV>` | Splunk Observability access token for that realm |
| `SPLUNK_HEC_URL_<ENV>` | Splunk Cloud HEC endpoint (e.g. `https://http-inputs-<instance>.splunkcloud.com:443/services/collector`) |
| `SPLUNK_HEC_TOKEN_<ENV>` | Splunk Cloud HEC token |
| `SPLUNK_INDEX_<ENV>` | Splunk Cloud HEC target index |

`<ENV>` is one of `DEV`, `EU`, `US`, `DEFAULT`.

Also required:

```
SPLUNK_LISTEN_INTERFACE=0.0.0.0
```

The realm controls the URL the `otlp_http/<env>` exporter builds:

```
https://ingest.${SPLUNK_REALM_<ENV>}.signalfx.com/v2/trace/otlp
https://ingest.${SPLUNK_REALM_<ENV>}.signalfx.com/v2/datapoint/otlp
```

Note: tokens and realms must match. A token issued in one org will be
rejected by other realms with HTTP 401. See **Troubleshooting** below.

### 4. Restart and verify

```bash
sudo systemctl restart splunk-otel-collector
sudo systemctl is-active splunk-otel-collector
curl -fsS http://localhost:13133
```

Healthy output looks like:

```
active
{"status":"Server available","upSince":"...","uptime":"..."}
```

Watch for export errors in the log:

```bash
sudo journalctl -u splunk-otel-collector -f | grep -E "Exporting failed|warn|error"
```

## Routing keys

The Lambda stamps `deployment.environment = "<workshop-env>-lambda"`,
where `<workshop-env>` is the cluster's `workshop-secret.env` value.

| Cluster | `workshop-secret.env` | Routing key (resource attr) | Pipeline |
|---|---|---|---|
| dev-astronomy | `dev-astronomy-shop-demo` | `dev-astronomy-shop-demo-lambda` | `*/dev` |
| astronomy-shop-eu | `astronomy-shop-eu` | `astronomy-shop-eu-lambda` | `*/eu` |
| astronomy-shop-us | `astronomy-shop-us` | `astronomy-shop-us-lambda` | `*/us` |
| (anything else) | — | — | `*/default` |

If you add a new cluster, update both the cluster's `workshop-secret.env`
*and* the routing connector statements in `gateway-config.yaml`.

## Smoke test

After restart, call the Lambda directly for each env and confirm the
collector accepts the spans without error:

```bash
for env in dev-astronomy-shop-demo astronomy-shop-eu astronomy-shop-us xyz-unknown; do
  echo "=== $env ==="
  curl -sS -X POST 'https://<api-gateway-host>/<stage>/orders' \
    -H 'Content-Type: application/json' \
    -d "{\"service\":\"smoke\",\"env\":\"$env\",\"orders_count\":1,\"orders\":[{\"order_id\":\"SMOKE\",\"items_count\":1,\"shipping_address\":{\"country\":\"US\"},\"shipping_cost\":{\"units\":1,\"currency_code\":\"USD\"}}]}" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('env =',d.get('env'),'/ tagged =',d.get('lambda',{}).get('deployment.environment'))"
done
```

Each invocation should return HTTP 200 with `env` round-tripped and the
tagged value in `lambda.deployment.environment`. Then on the gateway:

```bash
sudo journalctl -u splunk-otel-collector --since "5 minutes ago" \
  | grep -c "Exporting failed"
# expected: 0
```

In each target Splunk Observability org, filter APM by
`service.name=Planning_Init_Lambda` and confirm spans tagged with the
corresponding `deployment.environment=<env>-lambda` value appear.

## Troubleshooting

### `Exporting failed ... HTTP Status Code 401`

The token does not belong to the configured realm. Verify which realm
the token is valid in:

```bash
for realm in us0 us1 us2 eu0 eu1 jp0 au0; do
  code=$(curl -sS -o /dev/null -w "%{http_code}" \
    -H "X-SF-TOKEN: <token>" \
    "https://api.${realm}.signalfx.com/v2/organization")
  printf "%-5s  HTTP %s\n" "$realm" "$code"
done
```

Whichever realm returns HTTP 200 is the correct value for
`SPLUNK_REALM_<ENV>`. Update the env file and restart.

### Logs pipeline drops events with HEC 404

The `splunk_hec` exporter expects a Splunk Cloud HEC endpoint such as
`https://http-inputs-<instance>.splunkcloud.com:443/services/collector`.
A Splunk Observability log ingest URL (e.g. `https://ingest.<realm>.signalfx.com/v1/log`)
returns 404 for `splunk_hec` payloads. Use the HEC URL.

### `"otlphttp" alias is deprecated`

Already addressed in the committed config (`otlphttp` → `otlp_http`). If
you see this warning on an older config, rename the exporter blocks
accordingly.

### OTTL paths warning ("one or more paths were modified")

The collector auto-rewrites pre-context-prefix paths in OTTL with a
warning. Already addressed by writing `span.attributes` /
`datapoint.attributes` / `log.attributes` explicitly in the
`transform/promote_env_*` processors. Warn only — telemetry still flows.

### Collector starts but no exports observed

The default Splunk OTel Collector log level does not emit success lines.
Confirm traffic is flowing in via:

```bash
sudo journalctl -u splunk-otel-collector --since "5 minutes ago" \
  | grep -iE "received|Exporting"
```

For deeper inspection, temporarily add `debug:` (with `verbosity: detailed`)
to a pipeline's exporters and restart.

## Rollback

```bash
sudo cp /etc/otel/collector/gateway_config.yaml.pre-multienv \
        /etc/otel/collector/gateway_config.yaml
sudo cp /etc/otel/collector/splunk-otel-collector.conf.pre-multienv \
        /etc/otel/collector/splunk-otel-collector.conf
sudo systemctl restart splunk-otel-collector
```

The `.pre-multienv` suffixes are written by the install steps above.
Confirm they exist before running:

```bash
sudo ls -la /etc/otel/collector/*.pre-multienv
```

## Related

- Lambda function source: `../Planning_Init_Lambda/`
- Lambda env contract: `../shared/env.py`
- Planning service (K8s) that sets the env: `../../src/planning/`
- Full deploy walk-through (Lambda + collector + cutover): `../DEPLOY_INSTRUCTIONS.md`
- Follow-up TODOs:
  - Rewrite `gateway-config-cloudwatch.yaml` for multi-env routing
  - Optional DIAB variant (`gateway-config-diab.yaml`)
  - Move tokens from env file to AWS Secrets Manager / SSM Parameter Store
