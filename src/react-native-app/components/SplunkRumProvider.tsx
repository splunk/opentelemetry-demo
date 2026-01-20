// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

/**
 * Splunk RUM Provider Component
 * Wraps the app with OtelWrapper following official Splunk documentation
 */

import React, { useEffect, useState } from 'react';
import { OtelWrapper, startNavigationTracking } from '@splunk/otel-react-native';
import type { ReactNativeConfiguration } from '@splunk/otel-react-native';
import { useNavigationContainerRef } from 'expo-router';
import { buildSplunkRumConfig } from '../config/SplunkRumConfig';

interface SplunkRumProviderProps {
  children: React.ReactNode;
}

/**
 * Provider component that initializes Splunk RUM using OtelWrapper
 * Following the official Splunk RUM setup pattern for React Native
 */
export function SplunkRumProvider({ children }: SplunkRumProviderProps) {
  const [rumConfig, setRumConfig] = useState<ReactNativeConfiguration | null>(null);
  const [configError, setConfigError] = useState<Error | null>(null);
  const navigationRef = useNavigationContainerRef();

  // Build RUM configuration on mount
  useEffect(() => {
    buildSplunkRumConfig()
      .then((config) => {
        setRumConfig(config);
        console.log('✅ Splunk RUM configuration loaded successfully');
      })
      .catch((error) => {
        console.error('❌ Failed to build Splunk RUM configuration:', error);
        setConfigError(error);
      });
  }, []);

  // Start navigation tracking once RUM is initialized and navigation ref is ready
  useEffect(() => {
    if (rumConfig && navigationRef) {
      console.log('🧭 Starting React Navigation tracking for RUM');
      startNavigationTracking(navigationRef);
    }
  }, [rumConfig, navigationRef]);

  // Show error if configuration failed
  if (configError) {
    console.error('Splunk RUM configuration error:', configError);
    // Still render children even if RUM fails - don't block the app
    return <>{children}</>;
  }

  // Wait for configuration to be ready
  if (!rumConfig) {
    // Return null to show splash screen while loading
    return null;
  }

  // Wrap children with OtelWrapper using the official Splunk pattern
  return (
    <OtelWrapper configuration={rumConfig}>
      {children}
    </OtelWrapper>
  );
}
