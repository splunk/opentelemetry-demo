# Original vs Current Payment Token & Version Comparison

## Original Single-Service Implementation

From commit `14947a1b` - "feat: Change payment failure to be consistent per request with 4-8s duration"

### Constants Used

```javascript
const SUCCESS_VERSION = 'v350.9';
const FAILURE_VERSION = 'v350.10';
const API_TOKEN_SUCCESS_TOKEN = 'prod-a8cf28f9-1a1a-4994-bafa-cd4b143c3291';
const API_TOKEN_FAILURE_TOKEN = 'test-20e26e90-356b-432e-a2c6-956fc03f5609';
```

### Behavior

**Single service** with probabilistic failure based on `paymentFailure` flag:
- If flag value = 0 → Always use SUCCESS token/version
- If flag value > 0 → Random chance to use FAILURE token/version

### Logs

**Success:**
```json
{
  "token": "prod-a8cf28f9-1a1a-4994-bafa-cd4b143c3291",
  "version": "v350.9",
  "message": "Charging through ButtercupPayments"
}
```

**Failure:**
```json
{
  "token": "test-20e26e90-356b-432e-a2c6-956fc03f5609",
  "version": "v350.10",
  "message": "Failed payment processing through ButtercupPayments: Invalid API Token (test-20e26e90-356b-432e-a2c6-956fc03f5609)"
}
```

---

## Current Dual-Service Implementation

### Version A (Stable) - `vA-config.js`

```javascript
displayVersion: '1.7.0-a'
defaultTokenPrefix: 'prod-vA'
defaultToken: 'prod-vA-a8cf28f9-1a1a-4994-bafa-cd4b143c3291'
alwaysFail: false
```

### Version B (Error Pod) - `vB-config.js`

```javascript
displayVersion: '1.7.0-b'
defaultTokenPrefix: 'prod-vB'
defaultToken: 'prod-vB-3f2e4d9c-8b7a-4c3d-9e2f-1a4b5c6d7e8f'
alwaysFail: true
```

### Behavior

**Two separate services** with routing based on `paymentFailure` flag:
- Version A: Always succeeds, gets token from `payment-va-secret`
- Version B: Always fails, gets token from `payment-vb-secret`
- Checkout routes between them probabilistically

### Current Logs

**Version A (Success):**
```json
{
  "token": "prod-vA-a8cf28f9-1a1a-4994-bafa-cd4b143c3291",
  "version": "vA",
  "message": "Charging through ButtercupPayments"
}
```

**Version B (Failure):**
```json
{
  "token": "prod-vB-3f2e4d9c-8b7a-4c3d-9e2f-1a4b5c6d7e8f",
  "version": "vB",
  "message": "Failed payment processing through ButtercupPayments: Invalid API Token (prod-vB-3f2e4d9c-...)"
}
```

---

## Key Differences

| Aspect | Original | Current |
|--------|----------|---------|
| **Architecture** | Single service | Two services (A & B) |
| **Success Token** | `prod-a8cf28f9...` | `prod-vA-a8cf28f9...` |
| **Failure Token** | `test-20e26e90...` | `prod-vB-3f2e4d9c...` |
| **Success Version** | `v350.9` | `vA` or `1.7.0-a` |
| **Failure Version** | `v350.10` | `vB` or `1.7.0-b` |
| **Token Prefix** | `prod-` vs `test-` | `prod-vA-` vs `prod-vB-` |
| **UUID Suffix** | Same base UUID | Version A: same, Version B: different |
| **Routing** | Probabilistic within service | Probabilistic at checkout |

---

## Analysis

### Token Format

**Original:**
- Success: `prod-{uuid}`
- Failure: `test-{uuid}` (different UUID)
- Clear distinction: `prod` vs `test` prefix

**Current:**
- Version A: `prod-vA-{uuid}` (same base UUID as original success)
- Version B: `prod-vB-{uuid}` (completely different UUID)
- Both use `prod` prefix

### Version String

**Original:**
- Success: `v350.9` (Buttercup Payments API version?)
- Failure: `v350.10`
- Sequential version numbers

**Current:**
- Version A: `vA` or `1.7.0-a`
- Version B: `vB` or `1.7.0-b`
- Variant-based versioning

---

## Recommendations

### Option 1: Match Original Behavior (for compatibility)

Update Version B to use original failure token format:

```javascript
// vB-config.js
displayVersion: '1.7.0-b'
defaultToken: 'test-vB-20e26e90-356b-432e-a2c6-956fc03f5609'  // test- prefix
```

**Pros:**
- Matches original failure token pattern
- Logs show `test-` prefix indicating test/error pod
- Maintains some backward compatibility

**Cons:**
- Mixes `test-` and `prod-` prefixes
- May confuse if deployed to production

### Option 2: Keep Current Dual-Prod Format (recommended)

Keep both as `prod-*` with variant suffixes:

```javascript
// Current implementation
// vA: prod-vA-a8cf28f9-1a1a-4994-bafa-cd4b143c3291
// vB: prod-vB-3f2e4d9c-8b7a-4c3d-9e2f-1a4b5c6d7e8f
```

**Pros:**
- Clear A/B variant identification
- Both can be "production" deployments
- Version B is explicitly a canary/error testing variant, not a test environment

**Cons:**
- Different from original pattern
- Loses the `prod` vs `test` semantic distinction

### Option 3: Use Original Tokens Exactly

Use the exact original tokens from the single-service implementation:

```javascript
// vA-config.js
defaultToken: 'prod-a8cf28f9-1a1a-4994-bafa-cd4b143c3291'  // Original success

// vB-config.js
defaultToken: 'test-20e26e90-356b-432e-a2c6-956fc03f5609'  // Original failure
```

**Pros:**
- Exact match to original behavior
- Clear `prod` vs `test` distinction
- Logs would match historical data

**Cons:**
- Doesn't distinguish between A/B variants in the token
- Both services would use same tokens as the old single service

---

## Current Deployment (test-payment-ab-deployment.yaml)

The test deployment manifest uses:

```yaml
# payment-va-secret
api-token: "prod-vA-a8cf28f9-1a1a-4994-bafa-cd4b143c3291"

# payment-vb-secret
api-token: "prod-vB-3f2e4d9c-8b7a-4c3d-9e2f-1a4b5c6d7e8f"
```

These match the current config files (Option 2).

---

## Recommendation

**Keep Option 2 (Current Implementation)**

The current dual-prod format is better for the A/B architecture because:

1. **Clarity**: Both variants are production-grade, one is just configured to fail
2. **Traceability**: Token clearly identifies which variant (vA vs vB)
3. **Flexibility**: Version B can be deployed to production as a canary without "test" semantics
4. **OTEL Tags**: Combined with `payment.variant=A/B`, makes filtering easy

The original used `test-` because it was a simulated failure within a single service. With dual services, Version B is a real production deployment configured for error testing, not a "test" environment.
