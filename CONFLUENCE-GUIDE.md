# Splunk OpenTelemetry Astronomy Shop Demo

## Overview

The **Splunk OpenTelemetry Astronomy Shop Demo** is a microservices-based e-commerce application designed to demonstrate OpenTelemetry instrumentation and Splunk Observability Cloud capabilities in a realistic environment.

**Key Features:**
- 30+ microservices across 10+ programming languages
- OpenTelemetry instrumentation (traces, metrics, logs)
- Real User Monitoring (RUM) with Splunk Browser integration
- AlwaysOn Profiling for performance analysis
- Database Query Performance monitoring
- Hybrid cloud-datacenter architecture scenarios
- Feature flag-driven demo scenarios
- Fraud detection with SQL Server
- Mobile app integration (iOS/Android)

## Quick Links

| Resource | Purpose |
|----------|---------|
| **[GitHub Repository](https://github.com/splunk/opentelemetry-demo)** | Source code and manifests |
| **[Latest Releases](https://github.com/splunk/opentelemetry-demo/releases)** | Production-ready versions |
| **[GitHub Packages](https://github.com/orgs/splunk/packages?repo_name=opentelemetry-demo)** | Container images |

## Documentation

Complete documentation is maintained in the GitHub repository:

### 📚 Core Documentation

| Document | What You'll Learn | Who Should Read |
|----------|-------------------|-----------------|
| **[ARCHITECTURE.md](https://github.com/splunk/opentelemetry-demo/blob/main/ARCHITECTURE.md)** | System architecture, service components, deployment patterns, observability design | Architects, developers, demo engineers |
| **[DEVELOPING.md](https://github.com/splunk/opentelemetry-demo/blob/main/DEVELOPING.md)** | Fork setup, local testing, building services, GitHub workflows, version management | Developers, contributors |
| **[DEPLOYMENT.md](https://github.com/splunk/opentelemetry-demo/blob/main/DEPLOYMENT.md)** | Kubernetes deployment, Splunk O11y setup, collector config, Demo-in-a-Box, troubleshooting | Demo engineers, operators |

### 📋 Specialized Guides

| Document | What You'll Learn |
|----------|-------------------|
| **[PRODUCTION-WORKFLOW-GUIDE.md](https://github.com/splunk/opentelemetry-demo/blob/main/PRODUCTION-WORKFLOW-GUIDE.md)** | Production workflow scenarios, version management examples |
| **[WORKFLOWS.md](https://github.com/splunk/opentelemetry-demo/blob/main/WORKFLOWS.md)** | GitHub Actions workflows reference |
| **[ENVIRONMENT_SETUP.md](https://github.com/splunk/opentelemetry-demo/blob/main/ENVIRONMENT_SETUP.md)** | GitHub environment and secrets setup |
| **[SPLUNK-BUILD.md](https://github.com/splunk/opentelemetry-demo/blob/main/SPLUNK-BUILD.md)** | Quick reference for building services |

## Getting Started

### For Demo Engineers

**Want to deploy the demo?**

1. **Read:** [DEPLOYMENT.md](https://github.com/splunk/opentelemetry-demo/blob/main/DEPLOYMENT.md)
2. **Prerequisites:**
   - Kubernetes cluster (k3s, k3d, or cloud)
   - Splunk Observability Cloud account (realm, access token, RUM token)
3. **Quick Deploy:**
   ```bash
   # Download latest manifest
   curl -O https://github.com/splunk/opentelemetry-demo/releases/latest/download/splunk-astronomy-shop-{version}.yaml

   # Deploy
   kubectl apply -f splunk-astronomy-shop-{version}.yaml
   ```

**Using Demo-in-a-Box?**
- See [DEPLOYMENT.md - Demo-in-a-Box Section](https://github.com/splunk/opentelemetry-demo/blob/main/DEPLOYMENT.md#demo-in-a-box-deployment)
- Web interface on port 8083
- Automated deployment and teardown

### For Developers

**Want to contribute or customize?**

1. **Read:** [DEVELOPING.md](https://github.com/splunk/opentelemetry-demo/blob/main/DEVELOPING.md)
2. **Fork the repository**
3. **Run setup:** `./setup-fork.sh`
4. **Test locally:** k3d or minikube
5. **Build images:** GitHub Actions workflows

### For Understanding the System

**Want to learn the architecture?**

1. **Read:** [ARCHITECTURE.md](https://github.com/splunk/opentelemetry-demo/blob/main/ARCHITECTURE.md)
2. **Explore:**
   - Service component tables
   - Communication patterns (gRPC, REST, Kafka)
   - Observability architecture
   - Hybrid cloud-datacenter scenarios

## Demo Scenarios

The Astronomy Shop demonstrates:

### Cloud-Native Microservices
- **Frontend:** Next.js with Splunk RUM
- **Backend:** Go, Java, Node.js, Python, .NET, Ruby, C++, PHP
- **Data Stores:** PostgreSQL, SQL Server, Redis (Valkey)
- **Messaging:** Apache Kafka
- **Feature Flags:** OpenFeature with flagd

### Hybrid Cloud-Datacenter
- **shop-dc-shim:** On-premises Java service integrating with cloud checkout
- **Dual APM:** AppDynamics + Splunk Observability
- **Different environments:** `datacenter-b01` vs. cloud

### Advanced Observability
- **Distributed Tracing:** Full transaction visibility across services
- **Real User Monitoring:** Browser session replay and performance
- **AlwaysOn Profiling:** CPU and memory profiling for Java services
- **Database Monitoring:** SQL query performance tracking
- **Log Observer:** Unified log aggregation with Splunk Platform

## Architecture Highlights

```
┌─────────────────────────────────────────┐
│           Cloud Environment             │
│                                         │
│  Frontend → Cart → Checkout → Payment  │
│     ↓         ↓        ↓         ↓      │
│  Product   Email   Shipping  Accounting│
│  Catalog                                │
│                                         │
│  Splunk OTel Collector                 │
└─────────────────┬───────────────────────┘
                  │
                  │ gRPC
                  ↓
┌─────────────────────────────────────────┐
│      Datacenter Environment (B01)       │
│                                         │
│  Shop DC Shim → SQL Server DB          │
│  (Legacy POS)                           │
│                                         │
│  AppDynamics + Splunk Dual Monitoring  │
└─────────────────────────────────────────┘
```

## Service Count by Technology

| Language | Services | Examples |
|----------|----------|----------|
| **Java** | 3 | Ad Service, Fraud Detection, Shop DC Shim |
| **Node.js** | 3 | Payment, Accounting, Image Provider |
| **Go** | 4 | Checkout, Shipping, Product Catalog, Currency |
| **Python** | 4 | Recommendation, Load Gen, Product Reviews, LLM |
| **.NET** | 1 | Cart Service |
| **Ruby** | 1 | Email Service |
| **C++** | 1 | Currency Service |
| **PHP** | 1 | Quote Service |
| **TypeScript** | 2 | Frontend, Feature Flag UI |

## Deployment Variants

| Variant | Use Case | Includes |
|---------|----------|----------|
| **Standard** | Full cloud deployment | All cloud services + databases |
| **DIAB** | Demo-in-a-Box optimized | Standard + Ingress + simplified access |
| **Hybrid** | Cloud + Datacenter | Standard + shop-dc-shim services |

## Prerequisites

### For Deployment
- Kubernetes 1.24+ (8 CPU, 16GB RAM minimum)
- Splunk Observability Cloud account
- kubectl and helm CLI tools

### For Development
- Docker and Docker Buildx
- Python 3.8+
- Git and GitHub account

## Support & Resources

| Resource | Link |
|----------|------|
| **Issues & Bug Reports** | [GitHub Issues](https://github.com/splunk/opentelemetry-demo/issues) |
| **Source Code** | [GitHub Repository](https://github.com/splunk/opentelemetry-demo) |
| **Splunk O11y Docs** | [docs.splunk.com/observability](https://docs.splunk.com/observability) |
| **OpenTelemetry Docs** | [opentelemetry.io/docs/demo](https://opentelemetry.io/docs/demo/) |
| **Splunk Show** | [splunk.show](https://www.splunk.show) |

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](https://github.com/splunk/opentelemetry-demo/blob/main/CONTRIBUTING.md) for guidelines.

**Development workflow:**
1. Fork the repository
2. Create feature branch
3. Make changes and test locally
4. Submit pull request to `main` branch

## Version Information

**Latest Stable Version:** Check [Releases](https://github.com/splunk/opentelemetry-demo/releases)

**Container Registry:** `ghcr.io/splunk/opentelemetry-demo`

**Manifest Files:** `kubernetes/splunk-astronomy-shop-{version}.yaml`

## FAQ

**Q: Can I use this in production?**
A: This is a **demo application**. It's designed for learning, workshops, and demonstrations—not production workloads.

**Q: How do I update to the latest version?**
A: Download the latest manifest from [Releases](https://github.com/splunk/opentelemetry-demo/releases) and redeploy with `kubectl apply`.

**Q: What if I don't have AppDynamics?**
A: AppDynamics is optional. The demo works fully with just Splunk Observability Cloud. Services with `optional: true` for AppDynamics secrets will start without them.

**Q: Can I deploy just some services?**
A: Yes, but some services depend on others (e.g., checkout depends on payment, shipping, email). See [ARCHITECTURE.md](https://github.com/splunk/opentelemetry-demo/blob/main/ARCHITECTURE.md) for dependencies.

**Q: Where can I get Splunk Observability Cloud credentials?**
A: See [DEPLOYMENT.md - Splunk Observability Cloud Setup](https://github.com/splunk/opentelemetry-demo/blob/main/DEPLOYMENT.md#splunk-observability-cloud-setup) for detailed instructions.

---

**📖 For complete documentation, visit the [GitHub Repository](https://github.com/splunk/opentelemetry-demo)**

**Last Updated:** March 2026
