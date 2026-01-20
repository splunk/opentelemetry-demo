// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { SplunkRum, startNavigationTracking } from "@splunk/otel-react-native";
import { getSplunkGlobalAttributes } from "../utils/UserAttributes";
import { getRegionConfig, getAppName } from "../utils/RegionSettings";
import { useNavigationContainerRef } from "expo-router";
import { APP_VERSION } from "../constants/AppVersion";

export interface SplunkRumResult {
  loaded: boolean;
  rum: ReturnType<typeof SplunkRum.init> | null;
  provider: any; // Expose the tracer provider for direct span creation
}

// NOTE: Removed fetch/XHR interceptors to avoid interfering with
// Splunk RUM SDK's automatic network instrumentation

const initializeSplunkRum = async () => {
  try {
    // Get region-specific configuration based on toggle
    const regionConfig = await getRegionConfig();
    const appName = getAppName();

    // Determine which region toggle is selected
    const regionName = regionConfig.realm === 'eu0' ? 'EU' : 'US';
    console.log(`🌍 Selected Region: ${regionName} (realm: ${regionConfig.realm})`);

    // Validate required configuration
    if (!regionConfig.realm || !regionConfig.rumToken || !appName) {
      console.warn(
        "Splunk RUM not initialized: missing required configuration",
        {
          realm: regionConfig.realm || 'missing',
          token: regionConfig.rumToken ? 'present' : 'missing',
          appName: appName || 'missing'
        }
      );
      return null;
    }

    // Generate global attributes based on session
    const globalAttributes = await getSplunkGlobalAttributes();

    console.log("Initializing Splunk RUM with configuration:", {
      region: regionName,
      realm: regionConfig.realm,
      appName,
      deploymentEnvironment: regionConfig.rumEnv,
      globalAttributes
    });

    const rumConfig = {
      realm: regionConfig.realm,
      rumAccessToken: regionConfig.rumToken,
      applicationName: appName,
      deploymentEnvironment: regionConfig.rumEnv || "development",
      globalAttributes: {
        ...globalAttributes,
        'app.version': APP_VERSION,
      },
      debug: true, // Enable debug logging to see RUM data being sent
      // Configure batch span processor for faster/immediate sending
      // Use correct parameter names from SDK source:
      bufferSize: 1, // Send spans immediately (batch size of 1)
      bufferTimeout: 500, // Flush every 500ms instead of default 3000ms
    };

    console.log("Splunk RUM Configuration:", JSON.stringify(rumConfig, null, 2));

    const rum = SplunkRum.init(rumConfig);

    console.log(`Splunk RUM initialized successfully for ${regionConfig.realm} region`);
    console.log(`RUM Beacon URL: https://rum-ingest.${regionConfig.realm}.signalfx.com/v1/rum`);
    return rum;
  } catch (error) {
    console.error("Failed to initialize Splunk RUM:", error);
    return null;
  }
};

export const useSplunkRum = (): SplunkRumResult => {
  const [loaded, setLoaded] = useState<boolean>(false);
  const [rum, setRum] = useState<ReturnType<typeof SplunkRum.init> | null>(
    null
  );
  const [provider, setProvider] = useState<any>(null);
  const navigationRef = useNavigationContainerRef();

  useEffect(() => {
    if (!loaded) {
      initializeSplunkRum().then((rumInstance) => {
        setRum(rumInstance);
        // Expose the provider from SplunkRum for direct span creation
        setProvider(SplunkRum.provider);
        setLoaded(true);
      });
    }
  }, [loaded]);

  // Start navigation tracking once RUM is loaded and navigation ref is ready
  useEffect(() => {
    if (loaded && navigationRef) {
      console.log("Starting React Navigation tracking for RUM");
      startNavigationTracking(navigationRef);
    }
  }, [loaded, navigationRef]);

  return {
    loaded,
    rum,
    provider,
  };
};
