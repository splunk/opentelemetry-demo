#!/bin/bash

# Script to stitch together Kubernetes manifests for BASE version
# Based on stitch-manifests.sh but with modifications:
# - Excludes shop-dc-* services
# - Uses modified flagd-config with paymentFailure defaultVariant = "off"
#
# ⚠️ IMPORTANT: This script does NOT update version tags in manifests
# It uses the EXISTING version tags from the *-k8s.yaml files as-is
# Run this AFTER building and testing your images
#
# Usage: ./stitch-manifests-base.sh [registry_env]
#   registry_env: Optional - 'dev' or 'prod' to use registry from services.yaml
#                 If not specified, uses original registry URLs from manifests

set -e

# Parse optional registry environment argument
REGISTRY_ENV="${1:-}"

# Get version from SPLUNK-VERSION file
VERSION=$(cat SPLUNK-VERSION)
echo "Creating BASE manifest for version: $VERSION"

# Load services from services.yaml
# ALWAYS includes ALL services with manifest: true
echo "Reading services from services.yaml..."
if command -v python3 &> /dev/null; then
    # Use Python helper to parse YAML
    SERVICES_LIST=$(python3 .github/scripts/get-services.py --manifest)
    if [ $? -ne 0 ]; then
        echo "Error: Failed to read services.yaml"
        exit 1
    fi
    # Convert space-separated list to array
    read -ra ALL_SERVICES <<< "$SERVICES_LIST"
else
    echo "Error: python3 is required to parse services.yaml"
    echo "Please install Python 3 or manually update the SERVICES array in this script"
    exit 1
fi

# Filter out shop-dc-* services for Base version
SERVICES=()
EXCLUDED=()
for SERVICE in "${ALL_SERVICES[@]}"; do
    if [[ "$SERVICE" == shop-dc-* ]]; then
        EXCLUDED+=("$SERVICE")
        echo "Excluding shop-dc service: $SERVICE"
    else
        SERVICES+=("$SERVICE")
    fi
done

echo "Found ${#SERVICES[@]} services for BASE manifest (${#EXCLUDED[@]} shop-dc services excluded)"

# Get registry URL if registry environment is specified
REGISTRY_URL=""
if [ -n "$REGISTRY_ENV" ]; then
    if command -v python3 &> /dev/null; then
        REGISTRY_URL=$(python3 -c "import yaml; config = yaml.safe_load(open('services.yaml')); print(config.get('registry', {}).get('$REGISTRY_ENV', ''))" 2>/dev/null || echo "")
        if [ -n "$REGISTRY_URL" ]; then
            echo "Using registry environment: $REGISTRY_ENV"
            echo "Registry URL: $REGISTRY_URL"
        else
            echo "Warning: Registry environment '$REGISTRY_ENV' not found in services.yaml, using default"
        fi
    fi
fi

# Output directory and file
OUTPUT_DIR="kubernetes"
OUTPUT_FILE="$OUTPUT_DIR/splunk-astronomy-shop-base-${VERSION}.yaml"

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Create header for the combined manifest
cat > "$OUTPUT_FILE" << EOF
# Splunk Astronomy Shop Kubernetes Manifest - BASE Version
# Version: $VERSION
# Generated on: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
#
# This is the BASE configuration variant:
# - Excludes shop-dc-* services (shop-dc-shim, shop-dc-shim-db, shop-dc-loadgenerator)
# - Uses modified flagd-config with paymentFailure defaultVariant = "off"
#
# Services are defined in services.yaml
---
EOF

# Counter for found manifests
FOUND=0
MISSING=()

# Loop through each service and append its manifest
for SERVICE in "${SERVICES[@]}"; do
    MANIFEST_FILE="src/${SERVICE}/${SERVICE}-k8s.yaml"

    if [ -f "$MANIFEST_FILE" ]; then
        # Check if service has replace_registry flag set to false
        SHOULD_REPLACE="true"
        if [ -n "$REGISTRY_URL" ] && command -v python3 &> /dev/null; then
            SHOULD_REPLACE=$(python3 -c "
import yaml
config = yaml.safe_load(open('services.yaml'))
for svc in config.get('services', []):
    if svc.get('name') == '$SERVICE':
        print(str(svc.get('replace_registry', True)).lower())
        break
" 2>/dev/null || echo "true")
        fi

        # ⚠️ IMPORTANT: We do NOT modify version tags
        # This script uses whatever version tags are already in the *-k8s.yaml files
        # Version tags should be set by the build workflows BEFORE running this

        echo "Adding manifest for: $SERVICE (using existing version tags)"
        echo "" >> "$OUTPUT_FILE"
        echo "# === $SERVICE ===" >> "$OUTPUT_FILE"

        # Process manifest: ONLY replace registry URLs if needed
        # Version tags are preserved as-is from the source files
        if [ -n "$REGISTRY_URL" ] && [ "$SHOULD_REPLACE" = "true" ]; then
            # Replace ONLY registry URLs - preserve all version tags
            # Pattern matches: ghcr.io/{org}/{repo} and replaces with ${REGISTRY_URL}
            sed -e "s|ghcr.io/[^/]*/[^/]*|${REGISTRY_URL}|g" \
                "$MANIFEST_FILE" >> "$OUTPUT_FILE"
            echo "  (registry replaced, versions preserved)"
        else
            # Keep manifest completely as-is (no registry replacement, no version replacement)
            cat "$MANIFEST_FILE" >> "$OUTPUT_FILE"
            echo "  (using original file as-is)"
        fi

        echo "" >> "$OUTPUT_FILE"
        echo "---" >> "$OUTPUT_FILE"
        FOUND=$((FOUND + 1))
    else
        echo "Warning: Manifest not found for $SERVICE at $MANIFEST_FILE"
        MISSING+=("$SERVICE")
    fi
done

# Summary
echo ""
echo "=========================================="
echo "BASE Manifest stitching complete!"
echo "=========================================="
echo "Version: $VERSION"
echo "Output file: $OUTPUT_FILE"
echo "Services included: $FOUND"
echo "Services excluded: ${#EXCLUDED[@]} (shop-dc-*)"
echo "Services missing: ${#MISSING[@]}"
if [ -n "$REGISTRY_URL" ]; then
    echo "Registry: $REGISTRY_URL ($REGISTRY_ENV)"
fi

if [ ${#EXCLUDED[@]} -gt 0 ]; then
    echo ""
    echo "Excluded shop-dc services:"
    for SERVICE in "${EXCLUDED[@]}"; do
        echo "  - $SERVICE"
    done
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    echo "Missing manifests for:"
    for SERVICE in "${MISSING[@]}"; do
        echo "  - $SERVICE"
    done
fi

echo ""
echo "To add a new service, edit services.yaml in the repository root."
