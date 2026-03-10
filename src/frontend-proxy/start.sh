#!/bin/sh
# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

# Startup script for frontend-proxy service
# Sets default values for environment variables if not provided

# Set default values if environment variables are empty
# Auth is disabled by default - only enable if explicitly set to "true"
export FEATURE_AUTH_ENABLED="${FEATURE_AUTH_ENABLED:-false}"
export FEATURE_USER="${FEATURE_USER:-}"
export FEATURE_PASS="${FEATURE_PASS:-}"

# Run envsubst to generate config from template, then start envoy
envsubst < envoy.tmpl.yaml > envoy.yaml && envoy -c envoy.yaml
