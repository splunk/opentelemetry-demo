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
| **Allow SAM CLI IAM role creation** | `Y` | Required — SAM creates the Lambda execution role (CloudWatch Logs + Lambda invoke permissions) |
| **Disable rollback** | `N` | Keep rollback enabled for safety |
| **PlanningInitFunction has no authentication** | `Y` | Expected — demo app uses open API Gateway endpoint |
| **Save arguments to configuration file** | `Y` | Saves to `samconfig.toml` so future deploys just need `sam deploy` |
| **SAM configuration file** | Enter (default) | Uses `samconfig.toml` |
| **SAM configuration environment** | Enter (default) | Uses `default` environment |

### 3. Capture the Deployment Outputs
After deployment, SAM will output several values. **Save these — you'll need them later** for testing, K8s configuration, and log viewing:

```
Key                        Value
-------------------------  -------------------------------------------------------
PlanningApiEndpoint        https://<unique-id>.execute-api.<region>.amazonaws.com/<stage>
PlanningInitFunctionArn    arn:aws:lambda:<region>:<account-id>:function:<function-name>
PlanningInitFunctionName   splunk-astronomy-<stage>-planning-init
```

The API endpoint URL is unique to each deployment — it changes if you delete and recreate the stack.

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
Update the planning service with the Lambda endpoint:

```bash
# Edit the K8s manifest
vim src/planning/planning-k8s.yaml

# Change LAMBDA_ENDPOINT from "" to your API Gateway URL:
# - name: LAMBDA_ENDPOINT
#   value: "https://xxxxxx.execute-api.<region>.amazonaws.com/dev/orders"
```

Or set via kubectl:
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

## Troubleshooting

### "Parameter 'Stage' must be one of AllowedValues"
The `Stage` parameter in `template.yaml` is restricted to `dev`, `staging`, `prod`, or `demo`. If you used a different value during `--guided`, either re-run with an allowed value or add your value to the `AllowedValues` list in `template.yaml`.

### Changeset error after modifying `template.yaml`
If you edit `template.yaml` (e.g., adding a new allowed Stage value) but `sam deploy` still fails with the old error, you need to **rebuild first**. SAM caches the template — run:
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
