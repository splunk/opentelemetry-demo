#!/bin/bash
# Build both payment service versions from single codebase
# Usage: ./build-payment-versions.sh [VERSION] [push]
#   VERSION: Version tag (default: from SPLUNK-VERSION file or 1.7.0)
#   push: If specified, push images to registry

set -e

# Configuration
REGISTRY="ghcr.io/splunk/opentelemetry-demo"
SERVICE="otel-payment"

# Determine version
if [ -n "$1" ] && [ "$1" != "push" ]; then
  VERSION="$1"
  PUSH_ARG="$2"
elif [ -f "../../SPLUNK-VERSION" ]; then
  VERSION=$(cat ../../SPLUNK-VERSION)
  PUSH_ARG="$1"
else
  VERSION="1.7.0"
  PUSH_ARG="$1"
fi

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}🏗️  Building Payment Service - Dual Version Strategy${NC}"
echo "Registry: $REGISTRY"
echo "Service: $SERVICE"
echo "Version: $VERSION"
echo ""

# Navigate to repo root
cd "$(dirname "$0")/../.."

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${YELLOW}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi

# Build Version A
echo -e "${GREEN}📦 Building Version A (${VERSION}-a)...${NC}"
docker build \
  --build-arg VERSION=A \
  -t ${REGISTRY}/${SERVICE}:${VERSION}-a \
  -t ${REGISTRY}/${SERVICE}:latest-a \
  --label "git.commit=$(git rev-parse HEAD 2>/dev/null || echo 'unknown')" \
  --label "git.branch=$(git branch --show-current 2>/dev/null || echo 'unknown')" \
  -f src/payment/Dockerfile \
  .

echo -e "${GREEN}✅ Version A built successfully${NC}"
echo ""

# Build Version B
echo -e "${GREEN}📦 Building Version B (${VERSION}-b)...${NC}"
docker build \
  --build-arg VERSION=B \
  -t ${REGISTRY}/${SERVICE}:${VERSION}-b \
  -t ${REGISTRY}/${SERVICE}:latest-b \
  --label "git.commit=$(git rev-parse HEAD 2>/dev/null || echo 'unknown')" \
  --label "git.branch=$(git branch --show-current 2>/dev/null || echo 'unknown')" \
  -f src/payment/Dockerfile \
  .

echo -e "${GREEN}✅ Version B built successfully${NC}"
echo ""

# Display images
echo -e "${BLUE}📋 Built Images:${NC}"
docker images | grep ${SERVICE} | grep -E "${VERSION}-(a|b)"

echo ""
echo -e "${GREEN}✅ Build complete!${NC}"
echo ""
echo "Images built:"
echo "  ${REGISTRY}/${SERVICE}:${VERSION}-a"
echo "  ${REGISTRY}/${SERVICE}:${VERSION}-b"
echo ""
echo "To inspect version metadata:"
echo "  docker run --rm ${REGISTRY}/${SERVICE}:${VERSION}-a cat /app/version.json"
echo "  docker run --rm ${REGISTRY}/${SERVICE}:${VERSION}-b cat /app/version.json"
echo ""

# Optional push
if [ "$PUSH_ARG" == "push" ]; then
    echo -e "${BLUE}📤 Pushing images to registry...${NC}"
    docker push ${REGISTRY}/${SERVICE}:${VERSION}-a
    docker push ${REGISTRY}/${SERVICE}:${VERSION}-b
    docker push ${REGISTRY}/${SERVICE}:latest-a
    docker push ${REGISTRY}/${SERVICE}:latest-b
    echo -e "${GREEN}✅ Images pushed successfully${NC}"
else
    echo "To push to registry:"
    echo "  ./build-payment-versions.sh ${VERSION} push"
    echo ""
    echo "Or manually:"
    echo "  docker push ${REGISTRY}/${SERVICE}:${VERSION}-a"
    echo "  docker push ${REGISTRY}/${SERVICE}:${VERSION}-b"
fi
