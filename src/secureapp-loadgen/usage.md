# SecureApp Loadgen — Usage Guide

## Overview

This is a Java (Jetty 9.4) application that exercises vulnerability classes for Splunk SecureApp agent detection. It serves as both a **security test target** and a **configurable service impersonator** — it can appear as any service in the Splunk Observability APM dependency map by changing `OTEL_SERVICE_NAME`.

The app runs its own built-in loadgen (`loadgen.sh`) that hits the vulnerability endpoints on configurable schedules controlled by a flagd feature flag.

## Service Identity

The app is completely name-agnostic. Nothing in the Java code, endpoints, or responses changes based on the service name. The **only** thing that determines how this app appears in Splunk Observability APM is the `service.name` OpenTelemetry resource attribute, set via `OTEL_RESOURCE_ATTRIBUTES`:

```
OTEL_RESOURCE_ATTRIBUTES="service.name=shipping-api,service.namespace=opentelemetry-demo,service.version=2.1.3,deployment.environment=${DEPLOYMENT_ENVIRONMENT}"
```

The k8s manifest uses a helper env var `OTEL_SERVICE_NAME` that gets interpolated into this string at container startup. To change identity, change the `service.name` value — the app appears as a different service in APM. Same code, same endpoints, different identity. No code changes needed.

## Running as shipping-api (Astronomy Shop)

The default k8s manifest configures this app to appear as `shipping-api` in the Splunk Astronomy Shop's APM dependency map. This is purely a configuration choice — the app behavior is identical regardless of name. The following env vars shape how it integrates with the shop topology:

| Env Var | Value | What it does in APM |
|---------|-------|---------------------|
| `service.name` (in `OTEL_RESOURCE_ATTRIBUTES`) | `shipping-api` | Service identity — how it appears in APM service map and traces |
| `SHIPPING_ADDR` | `http://shipping:8080` | Enables outbound calls to shipping service → creates `shipping-api` -> `shipping` dependency edge |
| `SHIPPING_API` | `true` (from `workshop-secret`) | Registers `/api/v1/shipping/info` endpoint → enables inbound traffic from `frontend-proxy` -> `shipping-api` |
| `peer-service-mapping` | `shipping:8080=shipping` | Labels outbound dependency edge with friendly name `shipping` instead of raw `shipping:8080` |

Together, these create the following topology in the APM dependency map:
```
frontend-proxy  -->  shipping-api  -->  shipping
   (inbound via          (this app)        (outbound via
    /shipping/ route)                       /get-quote call)
```

All of this is driven by environment configuration, not code. To make this app appear as a different service (e.g. `inventory-api`), just change `service.name` in `OTEL_RESOURCE_ATTRIBUTES` — the endpoints, vulnerability tests, and loadgen behavior remain exactly the same.

### SHIPPING_ADDR

Controls outbound HTTP calls to the shop's shipping service (`/get-quote` endpoint):

| Setting | Behavior |
|---------|----------|
| `http://shipping:8080` (set in k8s) | ShippingQuoteServlet calls shipping, creating outbound dependency edge in APM |
| Not set / empty | ShippingQuoteServlet returns skip JSON, no outbound call, entrypoint skips shipping wait |

### SHIPPING_API

Controls the `/api/v1/shipping/info` delivery schedule endpoint:

| Setting | Behavior |
|---------|----------|
| `true` (from `workshop-secret.shipping_api`) | Endpoint registered, returns simulated delivery schedule JSON |
| Not set / empty / anything else | Endpoint not registered (404 from Jetty), defaults to `false` |

When enabled, the frontend-proxy routes `/shipping/` to this endpoint, and the astronomy-loadgen calls it every ~2 minutes. This creates inbound trace traffic visible in APM.

## JAVA_TOOL_OPTIONS Breakdown

The k8s manifest sets these JVM flags:

| Flag | Purpose | If Missing |
|------|---------|------------|
| `-javaagent:/app/splunk-otel-javaagent.jar` | Splunk OTel auto-instrumentation + SecureApp agent | No traces, no security events — app still runs but is invisible to APM |
| `-Dargento.allow.security.events=true` | Enable SecureApp security event detection | Agent loads but does not report vulnerability exploits |
| `-Dargento.wait.events.for.first.transaction=false` | Send security events immediately, don't wait for first HTTP transaction | Events delayed until first inbound request (matters for startup-time vulns) |
| `-Dotel.instrumentation.common.peer-service-mapping=shipping:8080=shipping` | Maps outbound calls to `shipping:8080` to peer service name `shipping` in APM | Outbound calls still traced, but APM dependency map shows raw `shipping:8080` instead of friendly name `shipping` |

## Endpoints

### Always registered

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check |
| `/api/v1/documents/convert` | GET | RCE via Struts2 CVE-2017-5638 |
| `/api/v1/links/preview` | GET | SSRF to cloud metadata (169.254.169.254) |
| `/api/v1/users/search` | GET | SQL injection (H2 in-memory DB) |
| `/api/v1/auth/login` | GET | Log4Shell CVE-2021-44228 via JNDI |
| `/api/v1/sessions/import` | GET | Deserialization CVE-2020-1714 via Keycloak |
| `/api/v1/workspace/sync` | GET | All 5 vuln classes + shipping call in one transaction |
| `/api/v1/shipping/estimate` | GET | Outbound HTTP to shipping service (skips if `SHIPPING_ADDR` not set) |

### Conditionally registered (SHIPPING_API=true)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/shipping/info?tracking=SHIP-XXXXX` | GET | Simulated delivery schedule JSON |

## Loadgen Behavior

The built-in `loadgen.sh` fires vulnerability endpoints on independent schedules, controlled by the `secureappAttack` flagd feature flag:

| Pace | Attack frequency | Shipping/Health |
|------|-----------------|-----------------|
| `minimal` (default) | Each vuln every ~3-12 hours | Every ~3-5 min |
| `targeted` | SQLi + Log4Shell every ~10-15 min, others minimal | Every ~3-5 min |
| `max` | All attacks every ~3-15 min | Every ~3-5 min |

Shipping and health calls run at fixed intervals regardless of attack pace.

## Standalone Deployment

To run outside the Astronomy Shop:
1. Remove or unset `SHIPPING_ADDR` — shipping calls will be skipped
2. Set `OTEL_SERVICE_NAME` to whatever service name you want in APM
3. Ensure `FLAGD_HOST` points to a reachable flagd instance, or loadgen falls back to `minimal` pace
4. Without `SHIPPING_ADDR`, the entrypoint skips the shipping wait entirely and starts immediately
