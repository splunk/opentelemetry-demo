#!/bin/bash

# Script to prepare configuration for dc-shop version
# - Modifies flagd-config to set paymentFailure defaultVariant to "off"
# - Same configuration as BASE, but dc-shop variant INCLUDES shop-dc-* services

set -e

echo "Preparing dc-shop configuration..."

FLAGD_CONFIG="src/flagd-config/flagd-config-k8s.yaml"

if [ ! -f "$FLAGD_CONFIG" ]; then
    echo "Error: $FLAGD_CONFIG not found"
    exit 1
fi

# Create a backup
cp "$FLAGD_CONFIG" "${FLAGD_CONFIG}.backup"

# Modify paymentFailure defaultVariant from "50%" to "off"
# This uses sed to find the paymentFailure section and change the defaultVariant
sed -i.tmp '/"paymentFailure":/,/"defaultVariant":/ {
    s/"defaultVariant": "50%"/"defaultVariant": "off"/
}' "$FLAGD_CONFIG"

# Remove temporary file
rm -f "${FLAGD_CONFIG}.tmp"

echo "✅ Modified paymentFailure defaultVariant to 'off' in $FLAGD_CONFIG"

# Verify the change
if grep -A 15 '"paymentFailure"' "$FLAGD_CONFIG" | grep -q '"defaultVariant": "off"'; then
    echo "✅ Verification passed: paymentFailure defaultVariant is now 'off'"
else
    echo "❌ Warning: Could not verify the change"
    # Restore backup
    mv "${FLAGD_CONFIG}.backup" "$FLAGD_CONFIG"
    exit 1
fi

# Remove backup on success
rm -f "${FLAGD_CONFIG}.backup"

echo "dc-shop configuration prepared successfully"
