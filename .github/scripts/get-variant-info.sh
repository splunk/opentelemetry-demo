#!/bin/bash

# Helper script to get variant-specific information
# Usage: ./get-variant-info.sh <variant> <info_type>
#   variant: "BASE", "Payment Error", or "dc-shop"
#   info_type: "slug", "config-desc", "flagd-setting", "excludes", "includes"

set -e

VARIANT="$1"
INFO_TYPE="$2"

case "$VARIANT" in
  "BASE")
    case "$INFO_TYPE" in
      "slug") echo "base" ;;
      "config-desc") echo "Excludes shop-dc-* services, paymentFailure OFF" ;;
      "flagd-setting") echo "paymentFailure defaultVariant = off" ;;
      "excludes") echo "shop-dc-shim, shop-dc-shim-db, shop-dc-loadgenerator" ;;
      "includes") echo "none" ;;
    esac
    ;;
  "Payment Error")
    case "$INFO_TYPE" in
      "slug") echo "payment-error" ;;
      "config-desc") echo "Excludes shop-dc-* services, paymentFailure 50%" ;;
      "flagd-setting") echo "paymentFailure defaultVariant = 50%" ;;
      "excludes") echo "shop-dc-shim, shop-dc-shim-db, shop-dc-loadgenerator" ;;
      "includes") echo "none" ;;
    esac
    ;;
  "dc-shop")
    case "$INFO_TYPE" in
      "slug") echo "dc-shop" ;;
      "config-desc") echo "Includes shop-dc-* services, paymentFailure OFF" ;;
      "flagd-setting") echo "paymentFailure defaultVariant = off" ;;
      "excludes") echo "none" ;;
      "includes") echo "shop-dc-shim, shop-dc-shim-db, shop-dc-loadgenerator" ;;
    esac
    ;;
  "All")
    case "$INFO_TYPE" in
      "slug") echo "all" ;;
      "config-desc") echo "All three variants (BASE, Payment Error, dc-shop)" ;;
      "flagd-setting") echo "Multiple configurations" ;;
      "excludes") echo "varies by variant" ;;
      "includes") echo "varies by variant" ;;
    esac
    ;;
  *)
    echo "Unknown variant: $VARIANT" >&2
    exit 1
    ;;
esac
