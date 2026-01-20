// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

/**
 * Splunk RUM Configuration Builder
 * Following official Splunk documentation for React Native RUM setup
 */

import type { ReactNativeConfiguration } from '@splunk/otel-react-native';
import { getRegionConfig, getAppName } from '../utils/RegionSettings';
import { getSplunkGlobalAttributes } from '../utils/UserAttributes';
import { APP_VERSION } from '../constants/AppVersion';

/**
 * Build Splunk RUM configuration based on selected region
 * This follows the official Splunk RUM setup pattern
 */
export async function buildSplunkRumConfig(): Promise<ReactNativeConfiguration> {
  // Get region-specific configuration based on toggle
  const regionConfig = await getRegionConfig();
  const appName = getAppName();

  // Determine which region toggle is selected
  const regionName = regionConfig.realm === 'eu0' ? 'EU' : 'US';
  console.log(`🌍 Building RUM Config for Region: ${regionName} (realm: ${regionConfig.realm})`);

  // Validate required configuration
  if (!regionConfig.realm || !regionConfig.rumToken || !appName) {
    console.warn(
      'Splunk RUM configuration incomplete - missing required values',
      {
        realm: regionConfig.realm || 'missing',
        token: regionConfig.rumToken ? 'present' : 'missing',
        appName: appName || 'missing'
      }
    );
    throw new Error('Splunk RUM configuration incomplete');
  }

  // Generate global attributes based on session
  const globalAttributes = await getSplunkGlobalAttributes();

  // Build configuration following Splunk's official format
  const rumConfig: ReactNativeConfiguration = {
    realm: regionConfig.realm,
    rumAccessToken: regionConfig.rumToken,
    applicationName: appName,
    environment: regionConfig.rumEnv || 'development',
    globalAttributes: {
      ...globalAttributes,
      'app.version': APP_VERSION,
    },
    // Enable debug logging to see RUM data being sent
    debug: true,
  };

  console.log('📝 Splunk RUM Configuration:', JSON.stringify(rumConfig, null, 2));
  console.log(`🚀 RUM Beacon URL: https://rum-ingest.${regionConfig.realm}.signalfx.com/v1/rum`);

  return rumConfig;
}
