// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

/**
 * Region Settings for EU/US Splunk RUM Configuration
 * Manages region selection and provides appropriate environment variables
 */

import AsyncStorage from '@react-native-async-storage/async-storage';

export type Region = 'EU' | 'US';

const REGION_KEY = '@astronomy_shop:region';
const DEFAULT_REGION: Region = 'EU';

/**
 * Get the current selected region (defaults to EU)
 */
export async function getRegion(): Promise<Region> {
  try {
    const region = await AsyncStorage.getItem(REGION_KEY);
    return (region as Region) || DEFAULT_REGION;
  } catch (error) {
    console.error('Error getting region:', error);
    return DEFAULT_REGION;
  }
}

/**
 * Set the selected region
 */
export async function setRegion(region: Region): Promise<void> {
  try {
    await AsyncStorage.setItem(REGION_KEY, region);
    console.log('Region set to:', region);
  } catch (error) {
    console.error('Error setting region:', error);
  }
}

/**
 * Get region-specific configuration
 */
export interface RegionConfig {
  realm: string;
  rumToken: string;
  rumEnv: string;
  frontendProxyUrl: string;
}

export async function getRegionConfig(): Promise<RegionConfig> {
  const region = await getRegion();

  if (region === 'EU') {
    return {
      realm: 'eu0',
      rumToken: process.env.EXPO_PUBLIC_SPLUNK_RUM_TOKEN_EU || '',
      rumEnv: process.env.EXPO_PUBLIC_SPLUNK_RUM_ENV_EU || '',
      frontendProxyUrl: process.env.EXPO_PUBLIC_FRONTEND_PROXY_URL_EU || '',
    };
  } else {
    return {
      realm: 'us1',
      rumToken: process.env.EXPO_PUBLIC_SPLUNK_RUM_TOKEN_US || '',
      rumEnv: process.env.EXPO_PUBLIC_SPLUNK_RUM_ENV_US || '',
      frontendProxyUrl: process.env.EXPO_PUBLIC_FRONTEND_PROXY_URL_US || '',
    };
  }
}

/**
 * Get the app name (same for both regions)
 */
export function getAppName(): string {
  return process.env.EXPO_PUBLIC_SPLUNK_APP_NAME || 'astronomy-shop-mobile';
}
