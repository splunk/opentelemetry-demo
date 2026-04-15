#!/bin/bash
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0
set -e

REGISTRY="quay.io"
NAMESPACE="jeremyh"
LOAD_GEN_IMAGE="${REGISTRY}/${NAMESPACE}/shop-dc-load-generator:0.0.5"


# Build load generator
docker buildx build --platform linux/amd64 -t ${LOAD_GEN_IMAGE} -f ./load-generator/Dockerfile --push --progress=plain .

echo "Load generator: ${LOAD_GEN_IMAGE}"
