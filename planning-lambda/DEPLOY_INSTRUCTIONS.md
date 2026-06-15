# AWS Lambda Deployment Instructions

## Prerequisites
- AWS CLI installed (`aws --version`)
- SAM CLI installed (`sam --version`)
- AWS credentials configured (`aws sts get-caller-identity` to verify)

## Deployment Steps

### 1. Build the Lambda
```bash
cd planning-lambda/Planning_Init
sam build
```

### 2. Deploy to AWS

**Important:** Splunk corporate AWS accounts require these tags on all resources, otherwise deployment will be denied by the Service Control Policy:

```bash
sam deploy --guided --tags "splunkit_data_classification=public splunkit_environment_type=non-prd"
```

For subsequent deploys (after `--guided` saves your config):
```bash
sam deploy --tags "splunkit_data_classification=public splunkit_environment_type=non-prd"
```

When using `--guided`, you'll be prompted for these parameters:

| Parameter | Description | Suggested Value |
|-----------|-------------|-----------------|
| **Stack Name** | CloudFormation stack name | `splunk-astronomy-planning` |
| **AWS Region** | Deployment region | Your preferred region |
| **Stage** | Deployment stage (dev/staging/prod) | `demo` |
| **OtelCollectorEndpoint** | OpenTelemetry collector URL | Leave blank (set later) |
| **DownstreamLambdaArn** | ARN of downstream Lambda | Leave blank (set later) |

Then you'll see these prompts:

| Prompt | Recommended | Notes |
|--------|-------------|-------|
| **Confirm changes before deploy** | `N` | Skips the manual changeset review |
| **Allow SAM CLI IAM role creation** | `Y` | Required -- SAM creates the Lambda execution role (CloudWatch Logs + Lambda invoke permissions) |
| **Disable rollback** | `N` | Keep rollback enabled for safety |
| **PlanningInitFunction has no authentication** | `Y` | Expected -- demo app uses open API Gateway endpoint |
| **Save arguments to configuration file** | `Y` | Saves to `samconfig.toml` so future deploys just need `sam deploy` |
| **SAM configuration file** | Enter (default) | Uses `samconfig.toml` |
| **SAM configuration environment** | Enter (default) | Uses `default` environment |

### 3. Capture the Deployment Outputs
After deployment, SAM will output several values. **Save these -- you'll need them later** for testing, K8s configuration, and log viewing:

```
Key                        Value
-------------------------  -------------------------------------------------------
PlanningApiEndpoint        https://<unique-id>.execute-api.<region>.amazonaws.com/<stage>
PlanningInitFunctionArn    arn:aws:lambda:<region>:<account-id>:function:<function-name>
PlanningInitFunctionName   splunk-astronomy-<stage>-planning-init
```

The API endpoint URL is unique to each deployment -- it changes if you delete and recreate the stack.

### 4. Test the Lambda Directly
```bash
# Test with curl
curl -X POST https://<YOUR-API-ENDPOINT>/orders \
  -H "Content-Type: application/json" \
  -d '{
    "service": "test",
    "timestamp": "2024-01-15T10:30:00Z",
    "orders_count": 1,
    "orders": [
      {
        "order_id": "TEST-001",
        "items_count": 2,
        "shipping_address": {"country": "US"},
        "shipping_cost": {"units": 25, "currency_code": "USD"}
      }
    ]
  }'
```

### 5. Configure K8s Planning Service
Update the planning service with the Lambda endpoint URL from step 3.

In `src/planning/planning-k8s.yaml`, set the `LAMBDA_ENDPOINT` env var:
```yaml
- name: LAMBDA_ENDPOINT
  value: "https://<unique-id>.execute-api.<region>.amazonaws.com/<stage>/orders"
```

The planning service injects a `traceparent` header when calling the Lambda, which connects the K8s trace to the Lambda trace for end-to-end distributed tracing.

If the service is already running, you can update it without redeploying:
```bash
kubectl set env deployment/planning LAMBDA_ENDPOINT=https://<YOUR-API-ENDPOINT>/orders
```

### 6. View Lambda Logs
```bash
sam logs -n PlanningInitFunction --stack-name splunk-astronomy-planning --tail
```

### 7. Enable Debug Logging
By default `LOG_LEVEL` is `INFO`. To see all received data (headers, body, raw event), set it to `DEBUG`:

```bash
aws lambda update-function-configuration \
  --function-name splunk-astronomy-demo-planning-init \
  --environment "Variables={LOG_LEVEL=DEBUG,OTEL_SERVICE_NAME=Planning_Init}" \
  --region eu-west-1
```

To switch back to INFO:
```bash
aws lambda update-function-configuration \
  --function-name splunk-astronomy-demo-planning-init \
  --environment "Variables={LOG_LEVEL=INFO,OTEL_SERVICE_NAME=Planning_Init}" \
  --region eu-west-1
```

Or change `LOG_LEVEL` in `template.yaml` and redeploy.

## Sending Telemetry to Splunk Observability Cloud

The Lambda functions send traces, metrics, and logs to a **Splunk OpenTelemetry Collector running in gateway mode** within the same VPC. The gateway collector receives OTLP from all Lambda functions and forwards to Splunk via HEC.

### Architecture

```
Lambda Functions --OTLP/gRPC--> OTel Collector (Gateway) --HEC--> Splunk Cloud / O11y
                                  (EC2 in VPC)
```

### Prerequisites
- An EC2 instance (or ECS/Fargate task) in the same VPC as the Lambda functions
- Splunk Observability Cloud access token and realm
- Splunk Cloud/Enterprise HEC endpoint and token (for logs)
- Security group allowing inbound gRPC (port 4317) and HTTP (port 4318) from Lambda

### 1. Set Up the EC2 Gateway Instance

Launch an EC2 instance in the same VPC and subnet as your Lambda functions:

1. **AMI:** Amazon Linux 2023 (or Ubuntu 22.04+)
2. **Instance type:** `t3.small` (sufficient for demo workloads)
3. **VPC/Subnet:** Same VPC as the Lambda; use a private subnet
4. **Security group:** Create or use one that allows:
   - Inbound TCP **4317** (gRPC) and **4318** (HTTP) from the Lambda security group
   - Inbound TCP **13133** (health check) for monitoring
   - Outbound HTTPS **443** to Splunk endpoints
5. **IAM role:** No special permissions needed -- the collector talks to Splunk, not AWS services

SSH into the instance and install the Splunk OTel Collector:

```bash
curl -sSL https://dl.signalfx.com/splunk-otel-collector.sh > /tmp/splunk-otel-collector.sh
sudo sh /tmp/splunk-otel-collector.sh \
  --realm <your-realm> \
  --access-token <your-access-token> \
  --mode gateway
```

Replace the default config with the gateway config from this repo:

```bash
sudo cp planning-lambda/collector/gateway-config.yaml /etc/otel/collector/splunk-otel-collector.conf
```

Set the required environment variables in `/etc/otel/collector/splunk-otel-collector.conf.d/env`.

The gateway now routes telemetry per env (`deployment.environment` resource
attribute) to one of four Splunk Observability + HEC orgs based on the
`workshop-secret.env` value in each cluster:

  - `dev-astronomy-shop-demo-lambda`  → DEV exporters
  - `astronomy-shop-eu-lambda`        → EU exporters
  - `astronomy-shop-us-lambda`        → US exporters
  - anything else                     → DEFAULT exporters

Lambdas stamp `deployment.environment = "<WORKSHOP_ENV>-lambda"` per
invocation; the gateway promotes that signal attribute to a resource
attribute and matches it in a routing connector.

Four sets of five vars (20 total):

```bash
SPLUNK_LISTEN_INTERFACE=0.0.0.0

# --- dev-astronomy ---
SPLUNK_REALM_DEV=<realm>
SPLUNK_TOKEN_DEV=<o11y-access-token>
SPLUNK_HEC_URL_DEV=https://http-inputs-<instance>.splunkcloud.com:443/services/collector
SPLUNK_HEC_TOKEN_DEV=<hec-token>
SPLUNK_INDEX_DEV=main

# --- astronomy-shop-eu ---
SPLUNK_REALM_EU=<realm>
SPLUNK_TOKEN_EU=<o11y-access-token>
SPLUNK_HEC_URL_EU=https://http-inputs-<instance>.splunkcloud.com:443/services/collector
SPLUNK_HEC_TOKEN_EU=<hec-token>
SPLUNK_INDEX_EU=main

# --- astronomy-shop-us ---
SPLUNK_REALM_US=<realm>
SPLUNK_TOKEN_US=<o11y-access-token>
SPLUNK_HEC_URL_US=https://http-inputs-<instance>.splunkcloud.com:443/services/collector
SPLUNK_HEC_TOKEN_US=<hec-token>
SPLUNK_INDEX_US=main

# --- default (catch-all for unmatched env) ---
SPLUNK_REALM_DEFAULT=<realm>
SPLUNK_TOKEN_DEFAULT=<o11y-access-token>
SPLUNK_HEC_URL_DEFAULT=https://http-inputs-<instance>.splunkcloud.com:443/services/collector
SPLUNK_HEC_TOKEN_DEFAULT=<hec-token>
SPLUNK_INDEX_DEFAULT=main
```

Tokens live in the env file for initial rollout. AWS Secrets Manager / SSM
Parameter Store integration is a follow-up after multi-env is validated.

Routing flow:
```
Lambda OTLP --> gateway:4317 --> transform/promote_env_* (attr->resource)
                              --> routing/{traces,metrics,logs}
                              --> per-env pipeline
                              --> otlphttp/<env> + splunk_hec/<env>
```

Unmatched envs (or pre-rollout Lambdas without the `env` payload field) fall
through to `default` pipelines and also fan out to the `debug` exporter for
visibility during cutover.

DIAB note: DIAB deployments may require a parallel `gateway-config-diab.yaml`
with the same routing-connector shape plus DIAB-specific exporter/auth
quirks. Flagged as a follow-up; does not block initial multi-env rollout.

Restart the collector:

```bash
sudo systemctl restart splunk-otel-collector
```

Verify it's running:

```bash
curl http://localhost:13133  # health check
sudo systemctl status splunk-otel-collector
```

See `planning-lambda/collector/gateway-config.yaml` for the full pipeline configuration (receivers, processors, exporters).

### 2. Configure the Lambda

Set the `OtelCollectorEndpoint` parameter during deployment to the gateway's private IP or DNS:

```bash
sam deploy --guided \
  --parameter-overrides OtelCollectorEndpoint=http://<gateway-private-ip>:4317 \
  --tags "splunkit_data_classification=public splunkit_environment_type=non-prd"
```

Or update an existing deployment:
```bash
aws lambda update-function-configuration \
  --function-name splunk-astronomy-demo-planning-init \
  --environment "Variables={LOG_LEVEL=INFO,OTEL_SERVICE_NAME=Planning_Init,OTEL_EXPORTER_OTLP_ENDPOINT=http://<gateway-private-ip>:4317}" \
  --region eu-west-1
```

### 3. VPC Configuration for Lambda

**The Lambda must be in the same VPC as the gateway collector.** The collector listens on a private IP (e.g., `10.0.134.189:4317`), which is only reachable from within the VPC. Without VPC configuration, the Lambda runs on AWS's shared network and cannot reach private IPs.

The `template.yaml` already includes a `VpcConfig` block under the function properties. Update the security group and subnet IDs to match the gateway collector's EC2 instance:

```yaml
VpcConfig:
  SecurityGroupIds:
    - sg-xxxxxxxx    # Same SG as the collector, or one that allows egress to it
  SubnetIds:
    - subnet-xxxxxxxx  # Same subnet as the collector (must be a private subnet)
```

To find the collector's VPC details, SSH into the EC2 instance and run:
```bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
MAC=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/network/interfaces/macs/ | head -1)
echo "VPC: $(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/network/interfaces/macs/${MAC}vpc-id)"
echo "Subnet: $(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/network/interfaces/macs/${MAC}subnet-id)"
echo "SG: $(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/network/interfaces/macs/${MAC}security-group-ids)"
```

The SAM template also requires the `AWSLambdaVPCAccessExecutionRole` policy (already included) which grants the Lambda permission to create ENIs in the VPC.

**Important considerations:**
- The security group must allow **outbound traffic on port 4317** (gRPC) to the collector's security group
- The collector's security group must allow **inbound traffic on port 4317** from the Lambda's security group
- Lambda functions in a VPC **lose internet access** unless the subnet has a route to a **NAT gateway**. Without a NAT gateway, the Lambda can reach the collector but not external services (API Gateway, S3, etc.)
- If you only have a single private subnet, place both the Lambda and the collector in it to avoid cross-AZ data transfer costs

## Troubleshooting

### "Parameter 'Stage' must be one of AllowedValues"
The `Stage` parameter in `template.yaml` is restricted to `dev`, `staging`, `prod`, or `demo`. If you used a different value during `--guided`, either re-run with an allowed value or add your value to the `AllowedValues` list in `template.yaml`.

### Changeset error after modifying `template.yaml`
If you edit `template.yaml` (e.g., adding a new allowed Stage value) but `sam deploy` still fails with the old error, you need to **rebuild first**. SAM caches the template -- run:
```bash
sam build && sam deploy
```

### "Binary validation failed for python"
SAM requires the Python version specified in `template.yaml` (currently `python3.13`) to be on your PATH. Install the matching version or update the `Runtime` in `template.yaml` to match what you have installed (`python3 --version`).

### "No authentication" warning during guided deploy
This is expected for a demo app. The API Gateway endpoint is intentionally open (no API key or IAM auth). Answer `Y` to proceed.

### AccessDenied / Service Control Policy error during deploy
Splunk corporate accounts require resource tags. Make sure you include the `--tags` flag:
```bash
sam deploy --tags "splunkit_data_classification=public splunkit_environment_type=non-prd"
```

## Files Reference
- SAM Template: `planning-lambda/Planning_Init/template.yaml`
- SAM Config: `planning-lambda/Planning_Init/samconfig.toml`
- Lambda Handler: `planning-lambda/Planning_Init/lambda_function.py`
- K8s Manifest: `src/planning/planning-k8s.yaml`
