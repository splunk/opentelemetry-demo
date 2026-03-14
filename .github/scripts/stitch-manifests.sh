#!/bin/bash

# Script to stitch together Kubernetes manifests from multiple services
# Usage: ./stitch-manifests.sh [registry_env] [diab] [output_dir] [suffix]
#   registry_env: Optional - 'dev' or 'prod' to use registry from services.yaml
#                 If not specified, uses original registry URLs from manifests
#   diab: Optional - 'diab' to enable DIAB scenario (includes ingress, adds -diab suffix)
#   output_dir: Optional - output directory (default: kubernetes)
#   suffix: Optional - additional suffix to add before .yaml (e.g., '-beta')
#
# This script reads service configuration from services.yaml
# ALWAYS stitches ALL services with manifest: true
# To add a new service, edit services.yaml instead of this script

set -e

# Parse optional arguments
REGISTRY_ENV="${1:-}"
DIAB_SCENARIO="${2:-}"
OUTPUT_DIR_ARG="${3:-}"
EXTRA_SUFFIX="${4:-}"

# Get version from SPLUNK-VERSION file
VERSION=$(cat SPLUNK-VERSION)
echo "Creating manifest for version: $VERSION"

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
    read -ra SERVICES <<< "$SERVICES_LIST"
else
    echo "Error: python3 is required to parse services.yaml"
    echo "Please install Python 3 or manually update the SERVICES array in this script"
    exit 1
fi

echo "Found ${#SERVICES[@]} services configured for manifest inclusion"

# Add ingress if DIAB scenario is enabled
if [ "$DIAB_SCENARIO" = "diab" ]; then
    echo "DIAB Scenario enabled - adding ingress to manifest"
    SERVICES+=("ingress")
fi

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
OUTPUT_DIR="${OUTPUT_DIR_ARG:-kubernetes}"
# Build filename with optional suffixes
# Format: splunk-astronomy-shop-{VERSION}[-diab][-beta].yaml
FILENAME="splunk-astronomy-shop-${VERSION}"
if [ "$DIAB_SCENARIO" = "diab" ]; then
    FILENAME="${FILENAME}-diab"
fi
if [ -n "$EXTRA_SUFFIX" ]; then
    FILENAME="${FILENAME}${EXTRA_SUFFIX}"
fi
OUTPUT_FILE="$OUTPUT_DIR/${FILENAME}.yaml"

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Create header for the combined manifest
cat > "$OUTPUT_FILE" << EOF
# Splunk Astronomy Shop Kubernetes Manifest
# Version: $VERSION
# Generated on: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
#
# This manifest combines all service deployments for the Splunk Astronomy Shop
# Services are defined in services.yaml
---
EOF

# Counter for found manifests
FOUND=0
MISSING=()

# Loop through each service and append its manifest
for SERVICE in "${SERVICES[@]}"; do
    MANIFEST_FILE="src/${SERVICE}/${SERVICE}-k8s.yaml"

    # Special handling for payment service - check for A/B testing variants
    if [ "$SERVICE" = "payment" ]; then
        VARIANT_A="src/${SERVICE}/${SERVICE}-vA-k8s.yaml"
        VARIANT_B="src/${SERVICE}/${SERVICE}-vB-k8s.yaml"

        # If both A/B variants exist, use them instead of the base manifest
        if [ -f "$VARIANT_A" ] && [ -f "$VARIANT_B" ]; then
            echo "Payment service: Using A/B testing variants (vA and vB)"
            PAYMENT_MANIFESTS=("$VARIANT_A" "$VARIANT_B")
            PAYMENT_VARIANTS=("vA" "vB")
        else
            # Fall back to standard manifest
            PAYMENT_MANIFESTS=("$MANIFEST_FILE")
            PAYMENT_VARIANTS=("")
        fi
    fi

    # Process payment service with A/B variant support
    if [ "$SERVICE" = "payment" ]; then
        for i in "${!PAYMENT_MANIFESTS[@]}"; do
            CURRENT_MANIFEST="${PAYMENT_MANIFESTS[$i]}"
            VARIANT_SUFFIX="${PAYMENT_VARIANTS[$i]}"

            if [ -f "$CURRENT_MANIFEST" ]; then
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

                # Get version for this specific service
                # Priority: .hotfix.yaml > .service-versions.yaml > VERSION (SPLUNK-VERSION)
                SERVICE_VERSION="${VERSION}"

                # Check for hotfix first (production hotfixes)
                if command -v python3 &> /dev/null && [ -f ".github/scripts/manage-hotfix.py" ]; then
                    HOTFIX_VERSION=$(python3 .github/scripts/manage-hotfix.py get "$SERVICE" 2>/dev/null || echo "")
                    if [ -n "$HOTFIX_VERSION" ] && [ "$HOTFIX_VERSION" != "$VERSION" ]; then
                        SERVICE_VERSION="$HOTFIX_VERSION"
                    fi
                fi

                # Check for per-service version (test/dev builds)
                if [ "$SERVICE_VERSION" == "$VERSION" ] && command -v python3 &> /dev/null && [ -f ".github/scripts/get-service-version.py" ]; then
                    SERVICE_VERSION=$(python3 .github/scripts/get-service-version.py "$SERVICE" "$VERSION")
                fi

                if [ -n "$VARIANT_SUFFIX" ]; then
                    echo "Adding manifest for: $SERVICE-$VARIANT_SUFFIX (version: $SERVICE_VERSION)"
                    echo "" >> "$OUTPUT_FILE"
                    echo "# === $SERVICE-$VARIANT_SUFFIX ===" >> "$OUTPUT_FILE"
                else
                    echo "Adding manifest for: $SERVICE (version: $SERVICE_VERSION)"
                    echo "" >> "$OUTPUT_FILE"
                    echo "# === $SERVICE ===" >> "$OUTPUT_FILE"
                fi

                # Process manifest: replace registry URLs (if needed) and version numbers
                if [ -n "$REGISTRY_URL" ] && [ "$SHOULD_REPLACE" = "true" ]; then
                    # Replace registry URLs, image tags, and version numbers
                    # Pattern matches: ghcr.io/{org}/{repo} and replaces with ${REGISTRY_URL}
                    # Version replacement ONLY applies to images from ${REGISTRY_URL}, preserving third-party images
                    # Special handling: Preserves version suffixes (e.g., -a, -b) for A/B testing variants
                    sed -e "s|ghcr.io/[^/]*/[^/]*|${REGISTRY_URL}|g" \
                        -e "s|\(${REGISTRY_URL}/[^:]*\):[0-9][0-9.]*\([^[:space:]]*\)|\1:${SERVICE_VERSION}\2|" \
                        -e "s|app.kubernetes.io/version: [0-9][0-9.]*\([^\"[:space:]]*\)|app.kubernetes.io/version: ${SERVICE_VERSION}\1|g" \
                        -e "s|service.version=[0-9][0-9.]*\([^,[:space:]]*\)|service.version=${SERVICE_VERSION}\1|g" \
                        "$CURRENT_MANIFEST" >> "$OUTPUT_FILE"
                elif [ "$SHOULD_REPLACE" = "false" ]; then
                    # Keep manifest completely as-is (no registry replacement, no version replacement)
                    cat "$CURRENT_MANIFEST" >> "$OUTPUT_FILE"
                    echo "  (using original registry and versions)"
                else
                    # No registry specified, but replace version numbers in labels only
                    # Preserves version suffixes (e.g., -a, -b) for A/B testing variants
                    sed -e "s|app.kubernetes.io/version: [0-9][0-9.]*\([^\"[:space:]]*\)|app.kubernetes.io/version: ${SERVICE_VERSION}\1|g" \
                        -e "s|service.version=[0-9][0-9.]*\([^,[:space:]]*\)|service.version=${SERVICE_VERSION}\1|g" \
                        "$CURRENT_MANIFEST" >> "$OUTPUT_FILE"
                fi

                echo "" >> "$OUTPUT_FILE"
                echo "---" >> "$OUTPUT_FILE"
                FOUND=$((FOUND + 1))
            else
                if [ -n "$VARIANT_SUFFIX" ]; then
                    echo "Warning: Manifest not found for $SERVICE-$VARIANT_SUFFIX at $CURRENT_MANIFEST"
                    MISSING+=("$SERVICE-$VARIANT_SUFFIX")
                else
                    echo "Warning: Manifest not found for $SERVICE at $CURRENT_MANIFEST"
                    MISSING+=("$SERVICE")
                fi
            fi
        done
    else
        # Standard processing for all non-payment services
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

            # Get version for this specific service
            # Priority: .hotfix.yaml > .service-versions.yaml > VERSION (SPLUNK-VERSION)
            SERVICE_VERSION="${VERSION}"

            # Check for hotfix first (production hotfixes)
            if command -v python3 &> /dev/null && [ -f ".github/scripts/manage-hotfix.py" ]; then
                HOTFIX_VERSION=$(python3 .github/scripts/manage-hotfix.py get "$SERVICE" 2>/dev/null || echo "")
                if [ -n "$HOTFIX_VERSION" ] && [ "$HOTFIX_VERSION" != "$VERSION" ]; then
                    SERVICE_VERSION="$HOTFIX_VERSION"
                fi
            fi

            # Check for per-service version (test/dev builds)
            if [ "$SERVICE_VERSION" == "$VERSION" ] && command -v python3 &> /dev/null && [ -f ".github/scripts/get-service-version.py" ]; then
                SERVICE_VERSION=$(python3 .github/scripts/get-service-version.py "$SERVICE" "$VERSION")
            fi

            echo "Adding manifest for: $SERVICE (version: $SERVICE_VERSION)"
            echo "" >> "$OUTPUT_FILE"
            echo "# === $SERVICE ===" >> "$OUTPUT_FILE"

            # Process manifest: replace registry URLs (if needed) and version numbers
            if [ -n "$REGISTRY_URL" ] && [ "$SHOULD_REPLACE" = "true" ]; then
                # Replace registry URLs, image tags, and version numbers
                # Pattern matches: ghcr.io/{org}/{repo} and replaces with ${REGISTRY_URL}
                # Version replacement ONLY applies to images from ${REGISTRY_URL}, preserving third-party images
                # Special handling: Preserves version suffixes (e.g., -a, -b) for A/B testing variants
                sed -e "s|ghcr.io/[^/]*/[^/]*|${REGISTRY_URL}|g" \
                    -e "s|\(${REGISTRY_URL}/[^:]*\):[0-9][0-9.]*\([^[:space:]]*\)|\1:${SERVICE_VERSION}\2|" \
                    -e "s|app.kubernetes.io/version: [0-9][0-9.]*\([^\"[:space:]]*\)|app.kubernetes.io/version: ${SERVICE_VERSION}\1|g" \
                    -e "s|service.version=[0-9][0-9.]*\([^,[:space:]]*\)|service.version=${SERVICE_VERSION}\1|g" \
                    "$MANIFEST_FILE" >> "$OUTPUT_FILE"
            elif [ "$SHOULD_REPLACE" = "false" ]; then
                # Keep manifest completely as-is (no registry replacement, no version replacement)
                cat "$MANIFEST_FILE" >> "$OUTPUT_FILE"
                echo "  (using original registry and versions)"
            else
                # No registry specified, but replace version numbers in labels only
                # Preserves version suffixes (e.g., -a, -b) for A/B testing variants
                sed -e "s|app.kubernetes.io/version: [0-9][0-9.]*\([^\"[:space:]]*\)|app.kubernetes.io/version: ${SERVICE_VERSION}\1|g" \
                    -e "s|service.version=[0-9][0-9.]*\([^,[:space:]]*\)|service.version=${SERVICE_VERSION}\1|g" \
                    "$MANIFEST_FILE" >> "$OUTPUT_FILE"
            fi

            echo "" >> "$OUTPUT_FILE"
            echo "---" >> "$OUTPUT_FILE"
            FOUND=$((FOUND + 1))
        else
            echo "Warning: Manifest not found for $SERVICE at $MANIFEST_FILE"
            MISSING+=("$SERVICE")
        fi
    fi
done

# Summary
echo ""
echo "=========================================="
echo "Manifest stitching complete!"
echo "=========================================="
echo "Version: $VERSION"
if [ "$DIAB_SCENARIO" = "diab" ]; then
    echo "Scenario: DIAB (includes ingress)"
fi
if [ -n "$EXTRA_SUFFIX" ]; then
    echo "Suffix: $EXTRA_SUFFIX"
fi
echo "Output file: $OUTPUT_FILE"
echo "Services found: $FOUND"
echo "Services missing: ${#MISSING[@]}"
if [ -n "$REGISTRY_URL" ]; then
    echo "Registry: $REGISTRY_URL ($REGISTRY_ENV)"
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
