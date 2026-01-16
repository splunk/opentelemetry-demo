// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { SplunkRum } from "@splunk/otel-react-native";

const SPLUNK_RUM_REALM = process.env.EXPO_PUBLIC_SPLUNK_RUM_REALM;
const SPLUNK_RUM_TOKEN = process.env.EXPO_PUBLIC_SPLUNK_RUM_TOKEN;
const SPLUNK_APP_NAME = process.env.EXPO_PUBLIC_SPLUNK_APP_NAME;
const SPLUNK_RUM_ENV = process.env.EXPO_PUBLIC_SPLUNK_RUM_ENV;

export interface SplunkRumResult {
  loaded: boolean;
  rum: ReturnType<typeof SplunkRum.init> | null;
}

const initializeSplunkRum = () => {
  // Skip initialization if required environment variables are not set
  if (!SPLUNK_RUM_REALM || !SPLUNK_RUM_TOKEN || !SPLUNK_APP_NAME) {
    console.warn(
      "Splunk RUM not initialized: missing required environment variables (EXPO_PUBLIC_SPLUNK_RUM_REALM, EXPO_PUBLIC_SPLUNK_RUM_TOKEN, EXPO_PUBLIC_SPLUNK_APP_NAME)"
    );
    return null;
  }

  try {
    const rum = SplunkRum.init({
      realm: SPLUNK_RUM_REALM,
      rumAccessToken: SPLUNK_RUM_TOKEN,
      applicationName: SPLUNK_APP_NAME,
      deploymentEnvironment: SPLUNK_RUM_ENV || "development",
    });

    console.log("Splunk RUM initialized successfully");
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

  useEffect(() => {
    if (!loaded) {
      const rumInstance = initializeSplunkRum();
      setRum(rumInstance);
      setLoaded(true);
    }
  }, [loaded]);

  return {
    loaded,
    rum,
  };
};
