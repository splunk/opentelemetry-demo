#!/bin/bash

# Script to prepare configuration for Payment Error version
# - Modifies flagd-config to set paymentFailure defaultVariant to "50%"
# - Note: This is actually the default value, but we set it explicitly

set -e

echo "Preparing Payment Error configuration..."

FLAGD_CONFIG="src/flagd-config/flagd-config-k8s.yaml"

if [ ! -f "$FLAGD_CONFIG" ]; then
    echo "Error: $FLAGD_CONFIG not found"
    exit 1
fi

# Create a backup
cp "$FLAGD_CONFIG" "${FLAGD_CONFIG}.backup"

# Modify paymentFailure defaultVariant to "50%"
# This uses sed to find the paymentFailure section and ensure defaultVariant is "50%"
sed -i.tmp '/"paymentFailure":/,/"defaultVariant":/ {
    s/"defaultVariant": "[^"]*"/"defaultVariant": "50%"/
}' "$FLAGD_CONFIG"

# Remove temporary file
rm -f "${FLAGD_CONFIG}.tmp"

echo "✅ Set paymentFailure defaultVariant to '50%' in $FLAGD_CONFIG"

# Verify the change
if grep -A 15 '"paymentFailure"' "$FLAGD_CONFIG" | grep -q '"defaultVariant": "50%"'; then
    echo "✅ Verification passed: paymentFailure defaultVariant is '50%'"
else
    echo "❌ Warning: Could not verify the change"
    # Restore backup
    mv "${FLAGD_CONFIG}.backup" "$FLAGD_CONFIG"
    exit 1
fi

# Remove backup on success
rm -f "${FLAGD_CONFIG}.backup"

echo "Payment Error configuration prepared successfully"
