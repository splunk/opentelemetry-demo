# Splunk OpenTelemetry Demo - Architecture

## Overview

This repository is a Splunk-enhanced fork of the [OpenTelemetry Astronomy Shop Demo](https://github.com/open-telemetry/opentelemetry-demo), a microservice-based distributed system designed to demonstrate OpenTelemetry instrumentation and Splunk Observability features in a realistic environment.

**Purpose:**
- Demonstrate Splunk Observability Cloud capabilities with OpenTelemetry
- Provide a working example of hybrid cloud-datacenter architectures
- Show dual APM monitoring (AppDynamics + Splunk Observability)
- Illustrate enterprise modernization patterns and observability best practices

## High-Level Architecture

The demo consists of multiple microservices representing an e-commerce astronomy shop, with additional Splunk-specific services that simulate hybrid enterprise environments.

```
+-----------------------------------------------------------------+
|                      Cloud Environment                           |
|                                                                   |
|  +----------+    +----------+    +----------+                   |
|  | Frontend |--->|  Cart    |--->| Checkout |                   |
|  | (Next.js)|    | (Redis)  |    |  (Go)    |                   |
|  +----------+    +----------+    +----------+                   |
|                                        |                          |
|                   +--------------------+----------------+         |
|                   v                    v                v         |
|            +----------+        +----------+    +----------+     |
|            | Payment  |        | Shipping |    |  Email   |     |
|            | (Node.js)|        |   (Go)   |    |  (Ruby)  |     |
|            +----------+        +----------+    +----------+     |
|                   |                                               |
|                   v                                               |
|            +--------------+                                      |
|            | Accounting   |  (Splunk Enhanced)                   |
|            |  (Node.js)   |                                      |
|            +--------------+                                      |
|                                                                   |
|  +--------------------------------------------------+            |
|  |    Supporting Services                           |            |
|  |  * Product Catalog (Go)                          |            |
|  |  * Recommendation (Python)                       |            |
|  |  * Ad Service (Java)                             |            |
|  |  * Currency (C++)                                |            |
|  |  * Quote (PHP)                                   |            |
|  |  * Fraud Detection (Java + SQL Server)           |            |
|  |  * Load Generator (Python)                       |            |
|  |  * Feature Flags (OpenFeature)                   |            |
|  +--------------------------------------------------+            |
|                                                                   |
|  +--------------------------------------------------+            |
|  |         Splunk Observability Stack                |            |
|  |  * Splunk OTel Collector Agent                   |            |
|  |  * Metrics, Traces, Logs                         |            |
|  +--------------------------------------------------+            |
+-----------------------------------------------------------------+
                             ^
                             | gRPC
                             |
+----------------------------+------------------------------------+
|                Datacenter Environment (B01)                      |
|               deployment.environment: datacenter-b01             |
|                                                                   |
|  +---------------------+          +--------------------------+  |
|  |  Shop DC Shim       |----------|  Shop DC Shim DB         |  |
|  |  (Java Spring Boot) |          |  (SQL Server)            |  |
|  |                     |          |                          |  |
|  |  * REST API         |          |  * Transaction Storage   |  |
|  |  * gRPC Client      |          |  * Audit Logs            |  |
|  |  * N-Tier Legacy    |          |                          |  |
|  +---------------------+          +--------------------------+  |
|            |                                                      |
|            v                                                      |
|  +---------------------+                                         |
|  | DC Load Generator   |                                         |
|  |    (Python)         |                                         |
|  +---------------------+                                         |
|                                                                   |
|  +--------------------------------------------------+            |
|  |    Dual APM Monitoring                           |            |
|  |  * AppDynamics Java Agent                        |            |
|  |  * Splunk OTel Java Agent                        |            |
|  |  * Dual instrumentation mode                     |            |
|  +--------------------------------------------------+            |
+-----------------------------------------------------------------+
```

## Complete Service Reference

This table provides a quick reference for all services in the deployment, including their status and purpose.

| Service | Description | Technology | Status |
|---------|-------------|------------|--------|
| **flagd** | Feature flag daemon | Go | Used |
| **flagd-ui** | Feature flag management UI | TypeScript | Used |
| **image-provider** | Product image management | Python | Used |
| **frontend** | User-facing web application | Next.js | Used |
| **frontend-proxy** | Frontend load balancer and proxy | Envoy | Used |
| **product-catalog** | Product inventory and catalog | Go | Used |
| **cart** | Shopping cart management | .NET | Used |
| **checkout** | Order checkout workflow | Go | Used |
| **ad** | Advertisement serving | Java | Used |
| **email** | Order confirmation emails | Ruby | Used |
| **payment** | Payment processing (dual versions) | Node.js | Used |
| **shipping** | Shipping cost calculation | Go | Used |
| **quote** | Price quotations | PHP | Used |
| **accounting** | Order accounting and reporting | Node.js | Used (Splunk) |
| **currency** | Currency conversion | C++ | Used |
| **recommendation** | Product recommendations | Python | Used |
| **product-reviews** | Product review analysis with LLM | Python | Used (Splunk) |
| **fraud-detection** | Transaction fraud detection | Java | Used (Splunk) |
| **sql-server-fraud** | Fraud detection database | SQL Server | Used |
| **shop-dc-shim** | Datacenter hybrid service | Java Spring Boot | Used (Splunk) |
| **shop-dc-shim-db** | Datacenter transaction database | SQL Server | Used (Splunk) |
| **shop-dc-loadgenerator** | Datacenter load simulator | Python | Used (Splunk) |
| **react-native-app** | Mobile app for Astronomy Shop | React Native | NOT Used |
| **valkey-cart** | Redis cache for cart | Valkey | Used |
| **postgres** | Primary database | PostgreSQL | Used |
| **llm** | LLM proxy (not instrumented) | Python | Used |
| **kafka** | Message bus service | Apache Kafka | Used |
| **thousandeyes** | ThousandEyes monitoring agent | ThousandEyes | Used |
| **astronomy-loadgen** | Puppeteer-based load generator | Python/Puppeteer | Used |
| **demo-namespace** | Namespace configuration | Kubernetes | Used |
| **demo-service-account** | Service account for demo | Kubernetes | Used |
| **ingress** | External access (DIAB variant only) | Traefik | DIAB only |

**Notes:**
- **Splunk** indicates Splunk-specific enhancements or additions
- **DIAB only** indicates included only in DIAB manifest variant
- **NOT Used** indicates services in the repository but not deployed in standard configurations

## Core Service Components

### Frontend Services

| Service | Technology | Purpose | Splunk Enhanced |
|---------|-----------|---------|-----------------|
| **frontend** | Next.js, TypeScript | User-facing web application | Yes Yes |
| **frontend-proxy** | Envoy | Proxy and routing | Yes Yes |
| **image-provider** | Python | Product image serving | Yes Yes |

### Backend Services

| Service | Technology | Purpose | Splunk Enhanced |
|---------|-----------|---------|-----------------|
| **cart** | .NET | Shopping cart management | Yes Yes |
| **checkout** | Go | Order processing and coordination | Original |
| **payment** | Node.js | Payment processing with A/B testing | Yes Yes (dual versions) |
| **shipping** | Go | Shipping calculations | Original |
| **email** | Ruby | Email notifications | Original |
| **accounting** | Node.js | Financial reconciliation | Yes Splunk-added |

### Product & Recommendation Services

| Service | Technology | Purpose | Splunk Enhanced |
|---------|-----------|---------|-----------------|
| **product-catalog** | Go | Product information | Original |
| **recommendation** | Python | ML-based product recommendations | Yes Yes |
| **ad** | Java | Advertisement service | Yes Yes |
| **quote** | PHP | Price quotations | Original |

### Data Services

| Service | Technology | Purpose | Splunk Enhanced |
|---------|-----------|---------|-----------------|
| **currency** | C++ | Currency conversion | Original |
| **fraud-detection** | Java, SQL Server | Fraud detection with Kafka | Yes Splunk-added |
| **product-reviews** | LangChain, Python | Product review analysis | Yes Splunk-added |

### Datacenter Hybrid Services

| Service | Technology | Purpose | Splunk Enhanced |
|---------|-----------|---------|-----------------|
| **shop-dc-shim** | Java Spring Boot | On-premises POS system simulator | Yes Splunk-added |
| **shop-dc-shim-db** | SQL Server | Datacenter transaction database | Yes Splunk-added |
| **shop-dc-loadgenerator** | Python | Datacenter load simulation | Yes Splunk-added |

### Supporting Services

| Service | Technology | Purpose |
|---------|-----------|---------|
| **kafka** | Apache Kafka | Message broker for async events |
| **redis** | Redis | Session and cart storage |
| **postgres** | PostgreSQL | Primary database for some services |
| **flagd** | OpenFeature | Feature flag management |
| **load-generator** | Locust, Python | Cloud traffic simulation |

## Deployment Environments

### Cloud Environment (Default)

**Attributes:**
- `deployment.environment`: `(workshop-name)`
- `service.namespace`: Service-specific
- **Monitoring**: Splunk Observability Cloud via OTel Collector
- **Network**: Kubernetes default networking

### Datacenter Environment (Hybrid Demo)

**Attributes:**
- `deployment.environment.name`: `datacenter-b01`
- `service.namespace`: `datacenter`
- **Monitoring**:
  - AppDynamics Java Agent (traditional APM)
  - Splunk OTel Java Agent (modern observability)
  - Dual instrumentation mode
- **Network**: Separate network with bridge to cloud services
- **Use Case**: Simulates on-premises retail systems integrating with cloud checkout

## Observability Architecture

### Telemetry Collection

```
+-------------+      +------------------+      +---------------------+
|  Services   |----->|  OTel Collector  |----->| Splunk Observability|
|             |      |     Agent         |      |       Cloud         |
|             |      |                   |      |                     |
|  * Traces   |      |  * Receives OTLP |      |  * APM              |
|  * Metrics  |      |  * Processes      |      |  * Infrastructure   |
|  * Logs     |      |  * Exports        |      |  * RUM              |
+-------------+      +------------------+      |  * Log Observer     |
                                                 +---------------------+
```

### Instrumentation Patterns

**Automatic Instrumentation:**
- Java services: Splunk OTel Java Agent
- Node.js services: @splunk/otel auto-instrumentation
- .NET services: Splunk OTel .NET Agent
- Python services: Splunk OTel Python Agent

**Manual Instrumentation:**
- Go services: OpenTelemetry Go SDK
- C++ services: OpenTelemetry C++ SDK
- Frontend: OpenTelemetry JavaScript SDK + Splunk RUM

**Dual Instrumentation (Datacenter Services):**
- AppDynamics Java Agent + Splunk OTel Java Agent
- Demonstrates migration from traditional APM to modern observability

## Key Architectural Patterns

### 1. Hybrid Cloud-Datacenter Architecture

The shop-dc-shim service demonstrates:
- **On-premises N-Tier application** (presentation, business, data layers)
- **gRPC integration** with cloud checkout service
- **Separate monitoring environments** (AppDynamics + Splunk)
- **Network isolation** with controlled connectivity

**Transaction Flow:**
1. Customer purchase at datacenter POS terminal
2. Local validation and database storage
3. gRPC call to cloud checkout service
4. Cloud payment and fulfillment processing
5. Confirmation back to datacenter
6. Local reconciliation and audit

### 2. Feature Flag-Driven Behavior

Services use OpenFeature for:
- A/B testing (payment service has v1/v2 variants)
- Gradual rollouts
- Emergency kill switches
- Demo scenario control

### 3. Async Event Processing

Kafka-based patterns:
- Order events published by checkout
- Fraud detection consumes orders
- Accounting reconciliation
- Email notifications

### 4. Database Monitoring

Multiple database types demonstrate observability:
- **PostgreSQL**: Product catalog, orders
- **SQL Server**: Fraud detection, datacenter transactions
- **Redis**: Session storage, cart data
- **Monitoring**: Splunk DB Query Performance

## Service Communication

### Synchronous (gRPC)

```
Frontend -> Product Catalog
Frontend -> Recommendation
Frontend -> Ad Service
Checkout -> Payment
Checkout -> Shipping
Checkout -> Email
Checkout -> Currency
Shop DC Shim -> Checkout (hybrid)
```

### Asynchronous (Kafka)

```
Checkout -> [orders topic] -> Fraud Detection
Checkout -> [orders topic] -> Accounting
Checkout -> [orders topic] -> Email Service
```

### REST APIs

```
Frontend Proxy -> Backend Services (HTTP)
Shop DC Shim -> REST API for POS terminals
Load Generators -> All services
```

## Splunk-Specific Enhancements

### Added Services

1. **Accounting Service**: Financial reconciliation and reporting
2. **Fraud Detection**: Real-time fraud analysis with SQL Server
3. **Shop DC Shim**: On-premises datacenter simulation
4. **Product Reviews**: LLM-powered review analysis

### Enhanced Services

1. **Frontend**: Splunk RUM integration, custom instrumentation
2. **Payment**: Dual-version deployment (v1/v2) for A/B testing
3. **Recommendation**: Enhanced ML telemetry
4. **Ad Service**: Custom metrics and traces

### Configuration Features

- **Workshop Secrets**: Environment-specific configuration via K8s secrets
- **AppDynamics Integration**: Optional dual monitoring
- **Custom Resource Attributes**: Enhanced context for traces
- **Profiling**: AlwaysOn Profiling for Java services
- **Database Monitoring**: SQL query performance tracking

## Container Registry

**Production Images:**
- Registry: `ghcr.io/splunk/opentelemetry-demo`
- Naming: `otel-{service}:{version}`
- Versions: Managed via `SPLUNK-VERSION` file

**Development Images:**
- Registry: `ghcr.io/{your-username}/opentelemetry-demo-splunk`
- Configured via `dev-repo.yaml` (generated by `setup-fork.sh`)

## Deployment Variants

### Standard Deployment
- All cloud services
- Standard networking
- Default configuration
- Manifest: `splunk-astronomy-shop-{version}.yaml`

### DIAB (Demo In A Box) Deployment
- All services + Ingress configuration
- Simplified external access via Traefik
- Optimized for single-node demo environments
- Manifest: `splunk-astronomy-shop-{version}-diab.yaml`

### Hybrid Deployment
- Standard deployment + datacenter services
- Dual environment monitoring
- Demonstrates enterprise modernization
- Requires both cloud and datacenter manifests

## Network Architecture

### Kubernetes Networking

**Cloud Services:**
- Namespace: `default` (or custom)
- Service Discovery: K8s DNS
- Ingress: Optional (DIAB variant includes Traefik)

**Datacenter Services:**
- Network: `datacenter-b01` (172.20.0.0/16)
- Bridge connectivity to cloud services
- Simulates datacenter-to-cloud hybrid

### Service Mesh (Optional)

The demo can be enhanced with:
- Istio for advanced traffic management
- Service mesh observability
- mTLS between services

## Scaling Considerations

### Load Configuration

**TPM (Transactions Per Minute):**
- Controls both request frequency and processing intensity
- Default: 25 TPM (100% baseline load)
- Configurable per service (shop-dc-shim, load generators)
- Scales resources proportionally

**Memory Optimization:**
- Audit log disable: `-8,000-15,000 DB writes/day`
- Transaction retention: Configurable cleanup intervals
- Recommended for memory-constrained environments

### Resource Requirements

**Minimum:**
- 8 CPU cores
- 16 GB RAM
- Kubernetes cluster (minikube, k3s, or cloud)

**Recommended:**
- 16 CPU cores
- 32 GB RAM
- Multi-node cluster for realistic performance

**With Datacenter Services:**
- +4 CPU cores
- +8 GB RAM
- Additional SQL Server resources

## Security Considerations

- **Secrets Management**: K8s secrets for sensitive data
- **Database Passwords**: Stored in secrets, not manifests
- **API Tokens**: Workshop secrets for AppDynamics, Splunk
- **Network Policies**: Configurable for production-like isolation
- **Service Accounts**: Dedicated K8s service accounts per component

## Related Documentation

- [DEVELOPING.md](./DEVELOPING.md) - Development, testing, and build instructions
- [PRODUCTION-WORKFLOW-GUIDE.md](./PRODUCTION-WORKFLOW-GUIDE.md) - Version management and releases
- [WORKFLOWS.md](./WORKFLOWS.md) - GitHub Actions workflows
- [SPLUNK-BUILD.md](./SPLUNK-BUILD.md) - Building individual services
- [REGISTRY-CONFIG.md](./REGISTRY-CONFIG.md) - Container registry configuration
