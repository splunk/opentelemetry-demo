#!/bin/bash
# Copy the git-tracked values.yaml into a staging dir with release provenance
# stamped into its header. The git-tracked file in kubernetes/ stays untouched;
# the changes only land on the release asset copy.
#
# Usage: stage-values-with-header.sh <VERSION> [STAGING_DIR]
# Prints the staged file path on stdout (empty if source values.yaml missing).
#
# The in-repo values file carries a `# Version:` comment header (see the top of
# kubernetes/splunk-astronomy-shop-*-values.yaml). When present, this script
# stamps the release VERSION onto that line and injects Generated/Source
# provenance right after it — reusing the existing header instead of prepending
# a second one. Older values files without the header get a header prepended
# (legacy behaviour). Header lines are YAML `#` comments, so helm/kubectl ignore
# them.

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

if grep -qE '^# Version:' "$SRC"; then
  # Reuse the in-repo header: replace its `# Version:` line with the release
  # version and add Generated/Source provenance immediately after it.
  awk -v ver="$VERSION" -v ts="$GEN_TS" -v src="${SRC} @ ${GIT_SHA_SHORT}" '
    /^# Version:/ && !done {
      print "# Version:    " ver
      print "# Generated:  " ts
      print "# Source:     " src
      done = 1
      next
    }
    { print }
  ' "$SRC" > "$DEST"
else
  # Legacy: source has no header — prepend one.
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
fi

echo "$DEST"
