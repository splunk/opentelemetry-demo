# Shop Datacenter Load Generator

A Python-based load generator that simulates realistic on-premises retail store transactions hitting the datacenter shim service. This generator creates purchase traffic patterns that would originate from datacenter-deployed point-of-sale systems calling cloud checkout services.

## Features

- Simulates 5 store locations across the East Coast (NYC, Brooklyn, Boston, Philadelphia, DC)
- Generates realistic customer data and purchase patterns
- Supports multiple terminals per store
- Configurable transaction rates
- Circuit breaker pattern for status polling
- Continuous and burst load modes

## Configuration

### Transaction Rate Control

The load generator's transaction rate can be easily controlled via the `TPM` environment variable:

**TPM (Transactions Per Minute)**: Request rate only. Does **not** change shop-dc-shim CPU/memory work per purchase.

#### Examples

| TPM | Interval | Transactions/Hour | Use Case |
|-----|----------|-------------------|----------|
| 1 | 60 seconds | 60 | Sparse demo traffic |
| **2** | **30 seconds** | **120** | **Deployed default** — quieter traces, shim stays heavy |
| 5 | 12 seconds | 300 | Moderate POS traffic |
| 10 | 6 seconds | 600 | Previous default (too chatty for the DC demo) |

### Kubernetes Configuration

Edit the `TPM` environment variable in your kubernetes manifest:

```yaml
containers:
  - name: load-generator
    image: ghcr.io/splunk/opentelemetry-demo/otel-shop-dc-loadgenerator:1.5.0
    env:
      - name: TPM
        value: "2"  # Request rate only; leave shop-dc-shim TPM at 10
    args: ["--url", "http://shop-dc-shim:8070", "--mode", "continuous", "--duration", "0"]
```

### Command Line Usage

```bash
# Use environment variable
export TPM=2
python shop_load_generator.py --url http://localhost:8070 --mode continuous

# Or use command line argument (overrides env var if both are set)
python shop_load_generator.py --url http://localhost:8070 --mode continuous --tpm 2
```

## Modes

### Continuous Mode (Default)
Runs indefinitely at a steady rate:
```bash
python shop_load_generator.py --mode continuous --tpm 2 --duration 0
```

### Burst Mode
Generates a burst of concurrent transactions:
```bash
python shop_load_generator.py --mode burst --concurrent 20 --total 100
```

### Single Transaction
Executes one transaction for testing:
```bash
python shop_load_generator.py --mode single
```

## What Gets Called

Each transaction:
1. Selects a random store and terminal
2. Creates a realistic purchase with 1-5 items
3. Generates customer and shipping information
4. POSTs to: `http://shop-dc-shim:8070/api/shop/purchase`

## Error Handling

The load generator implements intelligent circuit breaker logic:
- Purchase requests are **never throttled** - they continue at configured rate
- Status polling implements exponential backoff on 500 errors
- After 10 consecutive status failures, circuit breaker opens for 10 minutes
- Prevents overwhelming the service during degraded states

## Monitoring

The generator logs:
- Transaction success/failure rates
- Response times
- Circuit breaker status
- Progress updates every minute

