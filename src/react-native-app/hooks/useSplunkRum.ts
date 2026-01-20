// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { SplunkRum, startNavigationTracking } from "@splunk/otel-react-native";
import { getSplunkGlobalAttributes } from "../utils/UserAttributes";
import { getRegionConfig, getAppName } from "../utils/RegionSettings";
import { useNavigationContainerRef } from "expo-router";

export interface SplunkRumResult {
  loaded: boolean;
  rum: ReturnType<typeof SplunkRum.init> | null;
}

// Intercept fetch to log RUM beacon requests
const originalFetch = global.fetch;
global.fetch = async (...args) => {
  const [url, options] = args;
  const urlString = typeof url === 'string' ? url : url.toString();

  // Log all requests to RUM beacon
  if (urlString.includes('rum-ingest') || urlString.includes('signalfx')) {
    console.log('📡 [RUM FETCH] Sending spans to beacon:', urlString);
    console.log('📡 [RUM FETCH] Request method:', options?.method || 'GET');
    console.log('📡 [RUM FETCH] Request headers:', options?.headers);

    if (options?.body) {
      try {
        const bodyText = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
        console.log('📡 [RUM FETCH] Request body preview:', bodyText.substring(0, 500));
      } catch (e) {
        console.log('📡 [RUM FETCH] Request body:', options.body);
      }
    }
  }

  try {
    const response = await originalFetch(...args);

    // Log response for RUM requests
    if (urlString.includes('rum-ingest') || urlString.includes('signalfx')) {
      console.log('✅ [RUM FETCH] Response status:', response.status, response.statusText);
      console.log('✅ [RUM FETCH] Response headers:', Object.fromEntries(response.headers.entries()));
    }

    return response;
  } catch (error) {
    // Log errors for RUM requests
    if (urlString.includes('rum-ingest') || urlString.includes('signalfx')) {
      console.error('❌ [RUM FETCH] Request failed:', error);
    }
    throw error;
  }
};

// Also intercept XMLHttpRequest in case the SDK uses that
const OriginalXHR = global.XMLHttpRequest;
if (OriginalXHR) {
  global.XMLHttpRequest = class extends OriginalXHR {
    open(method: string, url: string | URL, ...rest: any[]) {
      const urlString = typeof url === 'string' ? url : url.toString();
      if (urlString.includes('rum-ingest') || urlString.includes('signalfx')) {
        console.log('📡 [RUM XHR] Opening request to:', urlString);
        console.log('📡 [RUM XHR] Method:', method);
      }
      // @ts-ignore
      return super.open(method, url, ...rest);
    }

    send(body?: Document | XMLHttpRequestBodyInit | null) {
      // @ts-ignore
      const url = this._url || this.responseURL;
      if (url && (url.includes('rum-ingest') || url.includes('signalfx'))) {
        console.log('📡 [RUM XHR] Sending request');
        if (body) {
          try {
            const bodyText = typeof body === 'string' ? body : JSON.stringify(body);
            console.log('📡 [RUM XHR] Body preview:', bodyText.substring(0, 500));
          } catch (e) {
            console.log('📡 [RUM XHR] Body:', body);
          }
        }

        // Log response when done
        this.addEventListener('loadend', () => {
          console.log('✅ [RUM XHR] Response status:', this.status, this.statusText);
          console.log('✅ [RUM XHR] Response:', this.responseText?.substring(0, 200));
        });

        this.addEventListener('error', (e) => {
          console.error('❌ [RUM XHR] Request failed:', e);
        });
      }
      return super.send(body);
    }
  };
}

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
      globalAttributes,
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
  const navigationRef = useNavigationContainerRef();

  useEffect(() => {
    if (!loaded) {
      initializeSplunkRum().then((rumInstance) => {
        setRum(rumInstance);
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
  };
};
