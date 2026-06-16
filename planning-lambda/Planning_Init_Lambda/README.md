# Planning_Init Lambda Service

Entry point Lambda for the AWS planning services. Receives orders from the K8s planning service and routes to appropriate handlers.

## Overview

This Lambda function serves as the primary landing point for the AWS portion of the OpenTelemetry Demo. It:

1. Receives HTTP requests from the K8s planning service
2. Extracts W3C Trace Context for distributed tracing continuity
3. Routes requests to appropriate handlers (orders, analytics, forecasting)
4. Optionally forwards to downstream Lambda functions

## Prerequisites

- AWS CLI configured with appropriate credentials
- AWS SAM CLI installed (`pip install aws-sam-cli`)
- Python 3.12+

## Deployment

### Quick Start

```bash
# Navigate to this directory
cd Planning_Init

# Build the Lambda package
sam build

# Deploy with guided setup (first time)
sam deploy --guided

# Subsequent deployments
sam deploy
```

### Deployment Environments

```bash
# Development
sam deploy --config-env dev

# Staging
sam deploy --config-env staging

# Production (default)
sam deploy
```

### Deployment Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `Stage` | Deployment stage (dev/staging/prod) | prod |
| `OtelCollectorEndpoint` | OTLP collector endpoint | (none) |
| `DownstreamLambdaArn` | ARN for downstream Lambda calls | (none) |

Example with parameters:
```bash
sam deploy --parameter-overrides \
  Stage=dev \
  OtelCollectorEndpoint=http://your-collector:4317 \
  DownstreamLambdaArn=arn:aws:lambda:us-west-2:123456789:function:downstream
```

## API Endpoints

After deployment, the API Gateway URL will be output. The following endpoints are available:

| Method | Path | Handler | Description |
|--------|------|---------|-------------|
| POST | `/` | orders | Default route, processes orders |
| POST | `/orders` | orders | Process order data from planning service |
| POST | `/analytics` | analytics | Analytics operations (stub) |
| POST | `/forecast` | forecasting | Forecasting operations (stub) |

## Testing Locally

### Using SAM Local

```bash
# Start local API
sam local start-api

# Test with curl
curl -X POST http://localhost:3000/orders \
  -H "Content-Type: application/json" \
  -H "traceparent: 00-12345678901234567890123456789012-1234567890123456-01" \
  -d '{"orders": [{"id": "order-123", "items": [{"product_id": "OLJCESPC7Z", "quantity": 2}]}]}'
```

### Invoke Directly

```bash
sam local invoke PlanningInitFunction -e events/sample-order.json
```

## Sample Request

```json
{
  "orders": [
    {
      "id": "order-123",
      "customer_id": "customer-456",
      "items": [
        {
          "product_id": "OLJCESPC7Z",
          "quantity": 2,
          "cost": 19.99
        }
      ],
      "shipping_address": {
        "country": "US",
        "state": "CA"
      }
    }
  ]
}
```

## Sample Response

```json
{
  "status": "processed",
  "orders_received": 1,
  "orders": [
    {
      "order_id": "order-123",
      "status": "received",
      "region": "us-west",
      "priority": "standard",
      "forwarded_to_downstream": false
    }
  ],
  "trace_id": "12345678901234567890123456789012"
}
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging verbosity | INFO |
| `OTEL_SERVICE_NAME` | Service name for traces | Planning_Init |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP exporter endpoint | (none) |
| `DOWNSTREAM_LAMBDA_ARN` | Downstream Lambda ARN | (none) |
| `STAGE` | Deployment stage | prod |

## Trace Context

The service extracts W3C Trace Context from incoming requests:

- **traceparent**: Primary trace context header
- **tracestate**: Additional vendor-specific trace state

All responses include `X-Trace-Id` header for correlation.

## Logs

Logs are JSON formatted with automatic trace correlation:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "level": "INFO",
  "logger": "Planning_Init.orders",
  "message": "Processing orders",
  "trace_id": "12345678901234567890123456789012",
  "span_id": "1234567890123456",
  "order_count": 5
}
```

## Cleanup

```bash
# Delete the stack
sam delete --stack-name planning-init-lambda

# Or for specific environment
sam delete --stack-name planning-init-lambda-dev
```

## Extending

To add new handlers:

1. Create `handlers/your_handler.py` following the existing pattern
2. Import in `handlers/__init__.py`
3. Add route in `lambda_function.py` ROUTES dict
4. Add API Gateway event in `template.yaml`

## Troubleshooting

### Common Issues

**"Module not found" errors:**
```bash
sam build --use-container
```

**Permission denied on Lambda invoke:**
Check IAM role has `lambda:InvokeFunction` permission for downstream Lambda.

**No traces appearing:**
Verify `OTEL_EXPORTER_OTLP_ENDPOINT` is set and collector is reachable.
