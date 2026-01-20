// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { StyleSheet, Pressable, NativeModules } from "react-native";
import { ThemedView } from "@/components/ThemedView";
import { ThemedText } from "@/components/ThemedText";
import { useEffect, useState } from "react";
import { getRegion, setRegion, getRegionConfig, type Region } from "@/utils/RegionSettings";
import { getFrontendProxyURL } from "@/utils/Settings";
import Toast from "react-native-toast-message";

interface RegionSelectorProps {
  onRegionChange?: (region: Region) => void;
}

export function RegionSelector({ onRegionChange }: RegionSelectorProps) {
  const [selectedRegion, setSelectedRegion] = useState<Region>('EU');
  const [initialRegion, setInitialRegion] = useState<Region>('EU');
  const [currentUrl, setCurrentUrl] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [hasChanged, setHasChanged] = useState(false);

  useEffect(() => {
    const loadSettings = async () => {
      const region = await getRegion();
      const url = await getFrontendProxyURL();
      setSelectedRegion(region);
      setInitialRegion(region);
      setCurrentUrl(url);
      setLoading(false);
    };
    loadSettings();
  }, []);

  const handleRegionSelect = async (region: Region) => {
    setSelectedRegion(region);
    await setRegion(region);
    setHasChanged(region !== initialRegion);

    // Update the URL display to show the new region's URL
    const regionConfig = await getRegionConfig();
    setCurrentUrl(regionConfig.frontendProxyUrl);

    Toast.show({
      type: "info",
      position: "bottom",
      text1: `Region switched to ${region}`,
      text2: "Tap 'Restart App' to apply changes",
    });

    if (onRegionChange) {
      onRegionChange(region);
    }
  };

  const handleRestart = () => {
    try {
      // Use React Native's DevSettings to reload in development mode
      if (__DEV__ && NativeModules.DevSettings) {
        NativeModules.DevSettings.reload();
      } else {
        // In production, show a toast asking user to manually restart
        Toast.show({
          type: "info",
          position: "bottom",
          text1: "Please restart the app",
          text2: "Close and reopen the app to apply changes",
          visibilityTime: 4000,
        });
      }
    } catch (error) {
      console.error('Error restarting app:', error);
      Toast.show({
        type: "error",
        position: "bottom",
        text1: "Restart Failed",
        text2: "Please manually close and reopen the app",
      });
    }
  };

  if (loading) {
    return (
      <ThemedView style={styles.container}>
        <ThemedText>Loading region...</ThemedText>
      </ThemedView>
    );
  }

  return (
    <ThemedView style={styles.container}>
      <ThemedText style={styles.label}>Splunk RUM Region:</ThemedText>
      <ThemedView style={styles.buttonGroup}>
        <Pressable
          style={[
            styles.button,
            selectedRegion === 'EU' && styles.buttonActive
          ]}
          onPress={() => handleRegionSelect('EU')}
        >
          <ThemedText style={[
            styles.buttonText,
            selectedRegion === 'EU' && styles.buttonTextActive
          ]}>
            EU (eu0)
          </ThemedText>
        </Pressable>
        <Pressable
          style={[
            styles.button,
            selectedRegion === 'US' && styles.buttonActive
          ]}
          onPress={() => handleRegionSelect('US')}
        >
          <ThemedText style={[
            styles.buttonText,
            selectedRegion === 'US' && styles.buttonTextActive
          ]}>
            US (us1)
          </ThemedText>
        </Pressable>
      </ThemedView>
      <ThemedText style={styles.hint}>
        Selected: {selectedRegion}
      </ThemedText>

      {/* Restart App Button */}
      {hasChanged && (
        <Pressable
          style={styles.restartButton}
          onPress={handleRestart}
        >
          <ThemedText style={styles.restartButtonText}>
            Restart App
          </ThemedText>
        </Pressable>
      )}

      {/* Frontend Proxy URL Display */}
      <ThemedView style={styles.urlContainer}>
        <ThemedText style={styles.urlLabel}>Frontend Proxy URL:</ThemedText>
        <ThemedText style={styles.urlValue}>{currentUrl}</ThemedText>
      </ThemedView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    display: "flex",
    gap: 10,
  },
  label: {
    fontWeight: "600",
  },
  buttonGroup: {
    flexDirection: "row",
    gap: 10,
  },
  button: {
    borderRadius: 8,
    borderWidth: 2,
    borderColor: "#666",
    backgroundColor: "transparent",
    paddingVertical: 12,
    paddingHorizontal: 20,
    alignItems: "center",
    minWidth: 100,
  },
  buttonActive: {
    borderColor: "#4CAF50",
    backgroundColor: "#4CAF50",
  },
  buttonText: {
    color: "#666",
    fontWeight: "600",
  },
  buttonTextActive: {
    color: "white",
  },
  hint: {
    fontSize: 12,
    opacity: 0.7,
    fontStyle: "italic",
  },
  restartButton: {
    marginTop: 10,
    backgroundColor: "#FF9800",
    borderRadius: 8,
    paddingVertical: 14,
    paddingHorizontal: 24,
    alignItems: "center",
    justifyContent: "center",
    shadowColor: "#000",
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
    elevation: 5,
  },
  restartButtonText: {
    color: "white",
    fontWeight: "700",
    fontSize: 16,
  },
  urlContainer: {
    marginTop: 10,
    paddingTop: 10,
    borderTopWidth: 1,
    borderTopColor: "#333",
    gap: 5,
  },
  urlLabel: {
    fontSize: 12,
    fontWeight: "600",
    opacity: 0.7,
  },
  urlValue: {
    fontSize: 13,
    color: "#4CAF50",
    fontFamily: "monospace",
  },
});
