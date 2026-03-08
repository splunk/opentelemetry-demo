# Payment A/B Testing - Quick Reference

## 🔗 URLs
- **Shop**: http://lambda-test.splunko11y.com
- **Feature Flags**: http://lambda-test.splunko11y.com/feature

## 🎯 What Changed
We deployed **two payment service versions** that you can switch between using a feature flag:
- **Version A**: Normal production (payments succeed)
- **Version B**: Error testing pod (payments fail with retries)

## ⚡ Quick Test Instructions

1. **Open Feature Flags**: http://lambda-test.splunko11y.com/feature
2. **Find** the `paymentFailure` flag
3. **Set the value**:
   - `off` = All payments succeed (Version A)
   - `100%` = All payments fail after 4-10 seconds (Version B)
   - `10%`, `50%`, etc. = Mix of both versions

4. **Shop & Checkout**: http://lambda-test.splunko11y.com
5. **Make a purchase** and observe the behavior

## 📊 What You'll See

### Version A (flag = "off"):
✅ Fast payment (~100ms)
✅ Order completes successfully

### Version B (flag = "100%"):
❌ Payment fails after 4-10 seconds
❌ Error message shown
⏱️ Makes 4 retry attempts

## 🔍 Check Results in Splunk APM
- **Service Names**: `payment-va` (stable) or `payment-vb` (error pod)
- **Tags**: `payment.variant=A` or `payment.variant=B`
- **Logs**: Look for tokens:
  - Version A: `prod-a8cf28f9-1a1a-4994-bafa-cd4b143c3291`
  - Version B: `test-20e26e90-356b-432e-a2c6-956fc03f5609`

## 💡 Tips
- Use `50%` to see both behaviors randomly
- Use `100%` to force error testing
- Each Version B failure = 4 error logs (one per retry)

Questions? Check the full guide: `TESTING-GUIDE-PAYMENT-AB.md`
