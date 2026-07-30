#!/bin/bash
# Copy the git-tracked values.yaml into a staging dir with a version header
# prepended. The git-tracked file in kubernetes/ stays untouched; the header
# only lands on the release asset copy.
#
# Usage: stage-values-with-header.sh <VERSION> [STAGING_DIR]
# Prints the staged file path on stdout (empty if source values.yaml missing).
#
# Header is YAML `#` comments so helm / kubectl ignore it.

set -e

VERSION="${1:?VERSION required}"
STAGING_DIR="${2:-release-staging}"

SRC="kubernetes/splunk-astronomy-shop-${VERSION}-values.yaml"

if [ ! -f "$SRC" ]; then
  echo "stage-values-with-header: no values file at $SRC — skipping" >&2
  exit 0
fi

mkdir -p "$STAGING_DIR"
DEST="${STAGING_DIR}/$(basename "$SRC")"

GIT_SHA_SHORT="${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}"
GIT_SHA_SHORT="${GIT_SHA_SHORT:0:7}"
GEN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

{
  echo "# splunk-astronomy-shop helm values"
  echo "# Version:    ${VERSION}"
  echo "# Generated:  ${GEN_TS}"
  echo "# Source:     ${SRC} @ ${GIT_SHA_SHORT}"
  echo "#"
  echo "# Deploy:"
  echo "#   helm upgrade --install splunk-otel-collector \\"
  echo "#     splunk-otel-collector-chart/splunk-otel-collector \\"
  echo "#     -f splunk-astronomy-shop-${VERSION}-values.yaml"
  echo "#"
  cat "$SRC"
} > "$DEST"

echo "$DEST"
