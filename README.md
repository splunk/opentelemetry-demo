<!-- markdownlint-disable-next-line -->
# <img src="https://opentelemetry.io/img/logos/opentelemetry-logo-nav.png" alt="OTel logo" width="45"> Splunk OpenTelemetry Demo — Astronomy Shop

[![Slack](https://img.shields.io/badge/slack-@cncf/otel/demo-brightgreen.svg?logo=slack)](https://cloud-native.slack.com/archives/C03B4CWV4DA)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg?color=red)](./LICENSE)

> This is **Splunk's fork** of the [OpenTelemetry Demo](https://github.com/open-telemetry/opentelemetry-demo),
> maintained by the Splunk Observability field/demo team as a
> **Kubernetes-only distribution** with deep Splunk Observability Cloud-specific
> instrumentation and demo scenarios, built for field demos and workshops.

## Welcome to the Splunk Astronomy Shop

This repository contains the OpenTelemetry Astronomy Shop, a microservice-based
distributed system intended to illustrate the implementation of OpenTelemetry in
a near real-world environment — extended with Splunk Observability Cloud
integrations, additional demo services, and fault-injection scenarios built
for live demos and hands-on workshops.

## How this distribution differs from upstream

| Aspect | Upstream OTel Demo | This fork |
| --- | --- | --- |
| Deployment | Docker Compose or Kubernetes | **Kubernetes only** — Docker Compose is inherited from upstream, unmaintained, and known-broken (issues #298/#299) |
| Collector | Bundled OpenTelemetry Collector | **Splunk OTel Collector Helm chart**, swapped in entirely |
| Backends | Jaeger, Prometheus, OpenSearch (generic OTLP fan-out) | Splunk Observability Cloud (APM, IM, RUM, Log Observer) via signalfx/otlp_http/splunk_hec exporters |
| Load generation | Locust-based | **Custom Puppeteer-based load generator** — chosen for better RUM compatibility and easier scripted fault conditions |
| CI/CD | GitHub Actions targeting Docker Hub images | Splunk-specific build/promote/release pipeline publishing to `ghcr.io/splunk/opentelemetry-demo` |

None of the Splunk-specific functionality below ships in the upstream demo.

## Splunk-specific features & enhancements

### Collector & pipeline

- **Splunk backends** — signalfx, otlp_http, and splunk_hec (×2, for metrics/traces and logs) exporters
- **Database Monitoring (DBMon)** — Postgres/MySQL/Oracle/SQL Server auto-discovery, query-sample and top-query collection
- **Kafka metrics scraper**
- **SecureApp log routing** — dedicated event pipeline for attack-simulation telemetry
- **Cardinality control** — `strip_verbose` (enforces SignalFx's 36-dimension cap), `add_environment`
- **Noise reduction** — strips flagd's noisy EventStream/Resolve spans; reclassifies Envoy DC/canceled as not-error
- **Kubernetes infra telemetry** — kubelet stats, cluster events, syslog/auth_log tagged with `com.splunk.*`
- **Async trace continuity across Kafka** — span-link-based propagation into accounting and planning, and trace correlation into fraud-detection (solves the classic broken-trace-across-async-messaging problem)
- **Pipeline tuning** — signalfx traces disabled where redundant, cluster-receiver memory limits (500Mi/1Gi)

### App & instrumentation

- **Splunk RUM** — full Real User Monitoring with sourcemap upload for de-minified browser stack traces
- **Continuous profiling** — CPU + memory, across all supported languages, ~14 services
- **SecureApp** — dedicated attack load generator + telemetry for security-focused demos
- **Custom Puppeteer load generator** — replaces upstream's generator for better RUM fidelity and scriptable fault conditions

### Demo scenarios

- Database Monitoring (slow query detection, query-to-trace correlation)
- RUM (panic-mode incident, blue/green deploy comparison)
- Continuous profiling (CPU hotspot investigation)
- Order-validation CPU throttling
- GenAI failures (inaccurate LLM output, rate limiting)
- SecureApp attack simulation
- Payment unreachable / A-B testing
- AWS Lambda (planning service, serverless)
- Hybrid on-prem datacenter (`shop-dc-shim`, dual AppDynamics + Splunk instrumentation)

> **Note:** a couple of additional scenarios are in active development and not
> yet part of a release — a logging-workshop scenario (checkout promo-discount
> bug) and an improved Database Monitoring "slow query" scenario. They'll be
> added here once merged.

## Kubernetes architecture & requirements

This distribution deploys exclusively via Kubernetes manifests (no Helm chart
for the demo app itself; the collector uses the official Splunk Helm chart).
See [ARCHITECTURE.md](./ARCHITECTURE.md) for the full service inventory and
[DEPLOYMENT.md](./DEPLOYMENT.md) for cluster/account prerequisites.

## Forking this repository

**If you're forking this Splunk-specific repository**, run the setup script after cloning:

```bash
./setup-fork.sh
```

This script will:

- Configure your development registry (`dev-repo.yaml`)
- Prevent accidental production version file commits
- Set up your fork for test builds

See [PRODUCTION-WORKFLOW-GUIDE.md](./PRODUCTION-WORKFLOW-GUIDE.md) for workflow documentation.

## Quick start

**This Splunk fork deploys on Kubernetes using released manifests.** See
**[HOW-TO-DEPLOY-AND-RUN.md](HOW-TO-DEPLOY-AND-RUN.md)** for the short path and
**[DEPLOYMENT.md](DEPLOYMENT.md)** for the full Splunk Observability Cloud setup.

> **Note:** Docker Compose (`make start` / `docker-compose*.yml`) is inherited
> from upstream, is **not maintained** in this fork, and is known-broken on a
> fresh clone (issues #298/#299). Use the Kubernetes manifests instead.

Upstream (generic, non-Splunk) deployment docs:

- [Docker](https://opentelemetry.io/docs/demo/docker_deployment/)
- [Kubernetes](https://opentelemetry.io/docs/demo/kubernetes_deployment/)

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — service inventory, deployment topology, telemetry patterns
- [DEPLOYMENT.md](./DEPLOYMENT.md) — Splunk Observability Cloud + collector setup
- [HOW-TO-DEPLOY-AND-RUN.md](./HOW-TO-DEPLOY-AND-RUN.md) — shortest path to a running demo
- [DEVELOPING.md](./DEVELOPING.md) — local dev, fork setup, contributing a service
- [PRODUCTION-WORKFLOW-GUIDE.md](./PRODUCTION-WORKFLOW-GUIDE.md) — release/promotion workflow

For upstream OpenTelemetry Demo documentation not specific to this fork, see the
[Demo Documentation][docs].

## Demos featuring the Astronomy Shop

We welcome any vendor to fork the project to demonstrate their services and
adding a link below. The community is committed to maintaining the project and
keeping it up to date for you.

|                           |                |                                  |
|---------------------------|----------------|----------------------------------|
| [AlibabaCloud LogService] | [Grafana Labs] | [Sentry]                         |
| [Apache Doris]            | [Guance]       | [ServiceNow Cloud Observability] |
| [AppDynamics]             | [Honeycomb.io] | [SigNoz]                         |
| [Aspecto]                 | [Instana]      | [SolarWinds Observability]       |
| [Axiom]                   | [Kloudfuse]    | [Splunk]                         |
| [Axoflow]                 | [Kopai]        | [Sumo Logic]                     |
| [Azure Data Explorer]     | [Last9]        | [TelemetryHub]                   |
| [Causely]                 | [Liatrio]      | [Teletrace]                      |
| [ClickStack]              | [Logz.io]      | [Tinybird]                       |
| [Coralogix]               | [New Relic]    | [Tracetest]                      |
| [Dash0]                   | [Oodle]        | [Tsuga]                          |
| [Datadog]                 | [OpenObserve]  | [Uptrace]                        |
| [Dynatrace]               | [OpenSearch]   | [VictoriaMetrics]                |
| [Elastic]                 | [Oracle]       |                                  |
| [Google Cloud]            | [Parseable]    |                                  |

## Contributing

To get involved with this fork, see [CONTRIBUTING](CONTRIBUTING.md) and
[DEVELOPING.md](./DEVELOPING.md). For the upstream community project, our
[SIG Calls](CONTRIBUTING.md#join-a-sig-call) are every other Wednesday at
8:30 AM PST and anyone is welcome.

### Maintainers

- [Cyrille Le Clerc](https://github.com/cyrille-leclerc), Grafana Labs
- [Juliano Costa](https://github.com/julianocosta89), Datadog
- [Pierre Tessier](https://github.com/puckpuck), Honeycomb
- [Roger Coll](https://github.com/rogercoll), Elastic

For more information about the maintainer role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#maintainer).

### Approvers

- [Cedric Ziel](https://github.com/cedricziel), Grafana Labs
- [Mikko Viitanen](https://github.com/mviitane), Dynatrace
- [Piotr Kie&#x142;kowicz](https://github.com/Kielek), Splunk
- [Shenoy Pratik](https://github.com/ps48), AWS OpenSearch

For more information about the approver role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#approver).

### Emeritus

- [Austin Parker](https://github.com/austinlparker)
- [Carter Socha](https://github.com/cartersocha)
- [Michael Maxwell](https://github.com/mic-max)
- [Morgan McLean](https://github.com/mtwo)
- [Penghan Wang](https://github.com/wph95)
- [Reiley Yang](https://github.com/reyang)
- [Ziqi Zhao](https://github.com/fatsheep9146)

For more information about the emeritus role, see the [community repository](https://github.com/open-telemetry/community/blob/main/guides/contributor/membership.md#emeritus-maintainerapprovertriager).

### Thanks to all the people who have contributed

[![contributors](https://contributors-img.web.app/image?repo=open-telemetry/opentelemetry-demo)](https://github.com/open-telemetry/opentelemetry-demo/graphs/contributors)

[docs]: https://opentelemetry.io/docs/demo/

<!-- Links for Demos featuring the Astronomy Shop section -->

[AlibabaCloud LogService]: https://github.com/aliyun-sls/opentelemetry-demo
[AppDynamics]: https://community.splunk.com/t5/AppDynamics-Knowledge-Base/How-to-observe-Kubernetes-deployment-of-OpenTelemetry-demo-app/ta-p/741454
[Apache Doris]: https://github.com/apache/doris-opentelemetry-demo
[Aspecto]: https://github.com/aspecto-io/opentelemetry-demo
[Axiom]: https://play.axiom.co/axiom-play-qf1k/dashboards/otel.traces.otel-demo-traces
[Axoflow]: https://axoflow.com/opentelemetry-support-in-more-detail-in-axosyslog-and-syslog-ng/
[Azure Data Explorer]: https://github.com/Azure/Azure-kusto-opentelemetry-demo
[Causely]: https://github.com/causely-oss/otel-demo
[ClickStack]: https://github.com/ClickHouse/opentelemetry-demo
[Coralogix]: https://coralogix.com/blog/configure-otel-demo-send-telemetry-data-coralogix
[Dash0]: https://github.com/dash0hq/opentelemetry-demo
[Datadog]: https://docs.datadoghq.com/opentelemetry/guide/otel_demo_to_datadog
[Dynatrace]: https://www.dynatrace.com/news/blog/opentelemetry-demo-application-with-dynatrace/
[Elastic]: https://github.com/elastic/opentelemetry-demo
[Google Cloud]: https://github.com/GoogleCloudPlatform/opentelemetry-demo
[Grafana Labs]: https://github.com/grafana/opentelemetry-demo
[Guance]: https://github.com/GuanceCloud/opentelemetry-demo
[Honeycomb.io]: https://github.com/honeycombio/opentelemetry-demo
[Instana]: https://github.com/instana/opentelemetry-demo
[Kloudfuse]: https://github.com/kloudfuse/opentelemetry-demo
[Kopai]: https://github.com/kopai-app/opentelemetry-demo/tree/main/kopai
[Last9]: https://last9.io/docs/integrations-opentelemetry-demo/
[Liatrio]: https://github.com/liatrio/opentelemetry-demo
[Logz.io]: https://logz.io/learn/how-to-run-opentelemetry-demo-with-logz-io/
[New Relic]: https://github.com/newrelic/opentelemetry-demo
[Oodle]: https://blog.oodle.ai/meet-oodle-unified-and-ai-native-observability/
[OpenSearch]: https://github.com/opensearch-project/opentelemetry-demo
[OpenObserve]: https://openobserve.ai/blog/opentelemetry-astronomy-shop-demo/
[Oracle]: https://github.com/oracle-quickstart/oci-o11y-solutions/blob/main/knowledge-content/opentelemetry-demo
[Parseable]: https://www.parseable.com/blog/open-telemetry-demo-with-parseable-a-complete-observability-setup
[Sentry]: https://github.com/getsentry/opentelemetry-demo
[ServiceNow Cloud Observability]: https://docs.lightstep.com/otel/quick-start-operator#send-data-from-the-opentelemetry-demo
[SigNoz]: https://signoz.io/blog/opentelemetry-demo/
[SolarWinds Observability]: https://github.com/solarwinds/opentelemetry-demo
[Splunk]: https://github.com/splunk/opentelemetry-demo
[Sumo Logic]: https://www.sumologic.com/blog/common-opentelemetry-demo-application/
[TelemetryHub]: https://github.com/TelemetryHub/opentelemetry-demo/tree/telemetryhub-backend
[Teletrace]: https://github.com/teletrace/opentelemetry-demo
[Tinybird]: https://github.com/tinybirdco/opentelemetry-demo
[Tracetest]: https://github.com/kubeshop/opentelemetry-demo
[Tsuga]: https://github.com/tsuga-dev/opentelemetry-demo
[Uptrace]: https://github.com/uptrace/uptrace/tree/master/example/opentelemetry-demo
[VictoriaMetrics]: https://github.com/VictoriaMetrics-Community/opentelemetry-demo
