// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

/**
 * App version - read from environment variable
 * Update EXPO_PUBLIC_APP_VERSION in .env file when creating new builds
 */
export const APP_VERSION = process.env.EXPO_PUBLIC_APP_VERSION || "1.0.0";
