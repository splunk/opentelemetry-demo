// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import AsyncStorage from "@react-native-async-storage/async-storage";
import getLocalhost from "@/utils/Localhost";

const FRONTEND_PROXY_URL_SETTING = 'frontend_proxy_url';

export const getFrontendProxyURL = async (): Promise<string> => {
  // Priority 1: Region-specific environment variable
  const { getRegionConfig } = require('./RegionSettings');
  const regionConfig = await getRegionConfig();
  if (regionConfig.frontendProxyUrl) {
    return regionConfig.frontendProxyUrl;
  }

  // Priority 2: Localhost with port (for local development)
  const localhost = await getLocalhost();
  return `http://${localhost}:${process.env.EXPO_PUBLIC_FRONTEND_PROXY_PORT}`;
};

export const setFrontendProxyURL = async (url: string) => {
  await AsyncStorage.setItem(FRONTEND_PROXY_URL_SETTING, url);
}

export default getFrontendProxyURL;
