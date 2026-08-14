# order-ledger

Minimal Java support service for **accounting**. Demonstrates
**database-query ↔ APM-trace correlation** (Splunk DB Query Performance ↔ APM).

## What it does

Accounting fire-and-forgets `POST /validate/{orderId}` for every Kafka order it
consumes (its `ORDER_VALIDATION_ADDR` env). This service looks that order up in
the `accounting."order"` table and returns whether it exists:

```
POST /validate/{orderId}   ->  {"orderId":"...","found":true|false}
GET  /health               ->  {"ok":true}
```

## How the correlation works

The Splunk OpenTelemetry Java agent (baked into the image, applied via
`JAVA_TOOL_OPTIONS`) instruments both the incoming HTTP request and the JDBC
call. With `OTEL_INSTRUMENTATION_SPLUNK_JDBC_ENABLED=true` the DB statement
carries trace context, so the query correlates with the APM trace — and the
server span is created from accounting's `traceparent`, nesting the lookup under
the order's trace.

## Build & deploy

Standard service — defined in `services.yaml` (`build: true`, `manifest: true`,
`group: order-ledger`). It builds to
`ghcr.io/splunk/opentelemetry-demo/otel-order-ledger` and stitches into its own
opt-in manifest variant `splunk-astronomy-shop-<VERSION>-order-ledger.yaml`.

## Activating the accounting call

Set on the **accounting** deployment:

```
ORDER_VALIDATION_ADDR=http://order-ledger:8080
```

> This shares accounting's single validation hook with
> `order-validation`/throttle-demo — only one target can be wired at a time.

## Config

| Env | Default | Purpose |
|-----|---------|---------|
| `PG_URL` | `jdbc:postgresql://postgresql:5432/astroshop` | DB connection |
| `PG_USER` / `PG_PASS` | `otelu` / `otelp` | has SELECT on `accounting` schema |
| `PORT` | `8080` | HTTP listen port |
