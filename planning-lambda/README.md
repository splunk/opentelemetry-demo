# Planning Lambda Services

AWS Lambda services for the planning domain of the OpenTelemetry Demo.

## Overview

This directory contains AWS Lambda functions that extend the demo into AWS serverless infrastructure. These services are designed to be:

1. **Easily deployable** - Simple SAM deployment for 3rd parties
2. **Fully instrumented** - OpenTelemetry tracing with trace context propagation
3. **Extensible** - Framework for adding more Lambda services

## Architecture

```
+-----------------+     HTTP/REST      +-----------------------------+
|  Planning       | ------------------>|  Planning_Init (Lambda)     |
|  Service (K8s)  |                    |  (API Gateway + Lambda)     |
+-----------------+                    +--------------+--------------+
                                                      |
                                       +--------------+--------------+
                                       v              v              v
                                   +-------+    +-------+    +-------+
                                   |Future |    |Future |    |Future |
                                   |Lambda |    |Lambda |    |Lambda |
                                   +-------+    +-------+    +-------+
```

## Directory Structure

```
planning-lambda/
|-- README.md                   # This file
|-- shared/                     # Shared utilities (reusable across all Lambdas)
|   |-- __init__.py
|   |-- tracing.py             # OpenTelemetry tracing utilities
|   |-- logging.py             # Structured JSON logging
|   +-- lambda_client.py       # Lambda-to-Lambda invocation
|
+-- Planning_Init/              # First Lambda service
    |-- lambda_function.py     # Main handler with routing
    |-- handlers/              # Request handlers
    |   |-- orders.py          # Order processing
    |   |-- analytics.py       # Analytics (stub)
    |   +-- forecasting.py     # Forecasting (stub)
    |-- requirements.txt       # Python dependencies
    |-- template.yaml          # AWS SAM template
    |-- samconfig.toml         # SAM configuration
    +-- README.md              # Service-specific docs
```

## Shared Utilities

### tracing.py
- `init_tracer()` - Initialize OpenTelemetry tracer
- `extract_context()` - Extract trace context from API Gateway events
- `create_span()` - Create spans with automatic error handling
- `inject_context()` - Inject trace context for outgoing requests

### logging.py
- `get_logger()` - Get JSON logger with automatic trace correlation
- All logs include `trace_id` and `span_id` for correlation

### lambda_client.py
- `invoke_lambda()` - Invoke downstream Lambda with trace propagation
- `invoke_lambda_async()` - Async Lambda invocation

## Available Services

| Service | Description | Status |
|---------|-------------|--------|
| Planning_Init | Entry point, receives orders from K8s planning service | [x] Active |
| (Future) | Additional planning/analytics services | Planned |

## Quick Start

See individual service READMEs for deployment instructions.

```bash
# Deploy Planning_Init
cd Planning_Init
sam build
sam deploy --guided
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OTEL_SERVICE_NAME` | Service name for tracing | Service-specific |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint | (none) |
| `LOG_LEVEL` | Logging level | INFO |
| `DOWNSTREAM_LAMBDA_ARN` | ARN for downstream Lambda calls | (none) |

## Trace Context Propagation

All services support W3C Trace Context propagation:
- Incoming: Extract `traceparent` header from API Gateway
- Outgoing: Inject trace context into downstream Lambda calls
- Logs: Automatic trace_id/span_id injection
