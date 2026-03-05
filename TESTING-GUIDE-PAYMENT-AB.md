# Testing Guide: Payment A/B Service Deployment

## 🎯 What's New

We've deployed a **dual-version payment service** with A/B testing capabilities. The checkout service now routes payment requests between two versions based on a feature flag:

- **Payment Version A (Stable)**: Normal production behavior - payments succeed quickly
- **Payment Version B (Error Pod)**: Configured to always fail for error testing - useful for testing error handling, retry logic, and monitoring

## 🌐 Access URLs

- **Frontend (Astronomy Shop)**: http://lambda-test.splunko11y.com
- **Feature Flags UI**: http://lambda-test.splunko11y.com/feature

## 🚀 How to Test

### 1. Access the Feature Flag UI

Navigate to: **http://lambda-test.splunko11y.com/feature**

Find the **`paymentFailure`** flag and set it to one of these values:

| Flag Value | Behavior | Use Case |
|------------|----------|----------|
| **off** (0%) | 100% → Version A (stable) | Normal operation - all payments succeed |
| **10%** | 10% → Version B, 90% → Version A | Light canary testing - see occasional errors |
| **25%** | 25% → Version B, 75% → Version A | Medium error rate testing |
| **50%** | 50% → Version B, 50% → Version A | Equal split for comparison |
| **75%** | 75% → Version B, 25% → Version A | High error rate testing |
| **90%** | 90% → Version B, 10% → Version A | Very high error rate |
| **100%** | 100% → Version B (error pod) | Full error mode - all payments fail |

### 2. Test Payment Flows

1. Go to http://lambda-test.splunko11y.com
2. Browse products and add items to cart
3. Proceed to checkout
4. Complete the payment form
5. Observe the behavior based on your flag setting

## 📊 Expected Behaviors

### Version A (Stable) - When flag is "off" or partial routing to A

✅ **Success Indicators:**
- Payment completes immediately (~100ms)
- Order confirmation page shows
- Transaction ID displayed
- Log shows: `token: "prod-a8cf28f9-1a1a-4994-bafa-cd4b143c3291"`
- Log shows: `version: "v350.9"`

### Version B (Error Pod) - When flag is "100%" or partial routing to B

❌ **Expected Failure Indicators:**
- Payment takes 4-10 seconds to fail
- Error message displayed on frontend
- 4 retry attempts made (visible in logs/traces)
- Log shows: `token: "test-20e26e90-356b-432e-a2c6-956fc03f5609"`
- Log shows: `version: "v350.10"`
- Error message: `"Failed payment processing through ButtercupPayments: Invalid API Token (test-20e26e90-...)"`

## 🧪 Testing Scenarios

### Scenario 1: Normal Operations (Baseline)
**Flag**: `off`
**Expected**: All payments succeed quickly
**Purpose**: Verify baseline functionality

### Scenario 2: Canary Testing (10% Error Rate)
**Flag**: `10%`
**Expected**: ~1 in 10 payments fails after 4-10 seconds
**Purpose**: Test how the system handles occasional errors with realistic traffic

### Scenario 3: High Error Rate (50-50 Split)
**Flag**: `50%`
**Expected**: Half of payments succeed, half fail
**Purpose**: Good for comparing metrics between versions in Splunk APM

### Scenario 4: Full Error Mode
**Flag**: `100%`
**Expected**: All payments fail with retry behavior
**Purpose**: Test error handling, timeouts, user experience with failures

## 📈 Observability in Splunk APM

After testing, view the results in Splunk APM:

### Filter by Service Name:
- `service.name=payment-va` - Version A (stable)
- `service.name=payment-vb` - Version B (error pod)
- `service.name=checkout` - Checkout service

### Filter by Payment Variant:
- `payment.variant=A` - Version A traces
- `payment.variant=B` - Version B traces

### Compare Success vs Errors:
```spl
service.name=payment-va OR service.name=payment-vb
| stats count by service.name, error
```

### Version B Timing Analysis:
```spl
service.name=payment-vb
| stats avg(duration), min(duration), max(duration)
```

**Expected Timing for Version B:**
- Min: ~4000ms (4 seconds)
- Max: ~10000ms (10 seconds)
- Avg: ~6500ms

### Token Visibility in Logs:
```spl
index=logs service.name=payment-vb error=true
| rex field=message "(?<token>test-[a-f0-9-]+)"
| stats count by token
```

Should show: `test-20e26e90-356b-432e-a2c6-956fc03f5609`

## 🔍 What to Look For

### Frontend Experience:
- ✅ Fast successful payments (Version A)
- ⏱️ Delayed failures with error messages (Version B)
- 🔄 Retry behavior visible in browser network tab

### Traces in Splunk APM:
- Version A: Single span, quick duration, no errors
- Version B: Multiple spans (4 retry attempts), 4-10 second total duration, error tags

### Logs:
- Version A: Success logs with `prod-a8cf28f9...` token and `v350.9` version
- Version B: Error logs with `test-20e26e90...` token and `v350.10` version, 4 per failed payment

## ⚠️ Known Behaviors

1. **Probabilistic Routing**: With partial flags (like 10%), the routing is random. You may need to make multiple purchases to see both versions.

2. **Error Messages**: Version B errors are intentional and expected for testing purposes.

3. **Timing Variability**: Version B failure duration is randomized between 4-10 seconds - this is by design.

4. **Retry Attempts**: Version B always makes 4 attempts before giving up - you'll see 4 error log entries per failed payment.

## 🐛 Troubleshooting

### Not seeing any Version B errors even with 100% flag?
- Verify flagd is running: Check feature flag UI is accessible
- Check flag value was saved: Reload the feature flag UI page
- Clear browser cache and retry

### Payments taking forever?
- This is expected with Version B (4-10 seconds)
- Check flag setting - set to "off" for fast payments

### Want to see both versions in action?
- Set flag to `50%` and make multiple purchases
- Check Splunk APM to see both service names

## 📞 Support

If you encounter unexpected behavior:
1. Note the flag setting you're using
2. Capture any error messages from the frontend
3. Note the approximate time of the test
4. Check Splunk APM for traces with the timestamp

---

## Summary for Quick Testing

**Quick Test (5 minutes):**
1. Set flag to `off` → Make a purchase → Should succeed quickly ✅
2. Set flag to `100%` → Make a purchase → Should fail after 4-10 seconds ❌
3. Check Splunk APM for traces showing both versions

**Detailed Test (15 minutes):**
1. Test each flag value (off, 10%, 50%, 100%)
2. Make 3-5 purchases at each setting
3. Observe timing differences
4. Review traces in Splunk APM
5. Compare error rates and durations

Happy Testing! 🎉
