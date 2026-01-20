// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import { Pressable, StyleSheet } from "react-native";
import { ThemedText } from "./ThemedText";
import { trace } from "@opentelemetry/api";
import Toast from "react-native-toast-message";
import { SplunkRum } from "@splunk/otel-react-native";

export function RumTestButton() {
  const handlePress = () => {
    console.log("Creating test RUM span using Splunk RUM provider...");

    // Use the Splunk RUM provider directly (same way AppStart spans work)
    const provider = SplunkRum.provider;
    if (!provider) {
      console.error("Splunk RUM provider not initialized!");
      Toast.show({
        type: "error",
        position: "bottom",
        text1: "RUM Not Initialized",
        text2: "Provider is null",
        visibilityTime: 2000,
      });
      return;
    }

    const tracer = provider.getTracer("test-tracer");
    const span = tracer.startSpan("test-button-click");

    span.setAttribute("component", "test");
    span.setAttribute("action", "button.click");
    span.setAttribute("test.id", "rum-test-button");

    console.log("Test span created with provider:", span);

    // Show toast notification
    Toast.show({
      type: "success",
      position: "bottom",
      text1: "RUM Span Created",
      text2: "Check console for details",
      visibilityTime: 2000,
    });

    // End span after a delay to simulate work (1 second for visible duration)
    setTimeout(async () => {
      span.end();
      console.log("Test span ended, waiting before flush...");

      // Wait a moment to ensure span is fully ended before flushing
      await new Promise(resolve => setTimeout(resolve, 50));

      // Try to manually force a flush of the span processors
      try {
        await provider.forceFlush();
        console.log("Provider force flush called");
      } catch (error) {
        console.log("Force flush error (might not be supported):", error);
      }
    }, 1000);
  };

  return (
    <Pressable
      style={({ pressed }) => [
        styles.button,
        pressed && styles.buttonPressed
      ]}
      onPress={handlePress}
    >
      {({ pressed }) => (
        <ThemedText style={[
          styles.buttonText,
          pressed && styles.buttonTextPressed
        ]}>
          Test RUM Span
        </ThemedText>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    backgroundColor: "#007AFF",
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 20,
    alignItems: "center",
    marginVertical: 10,
  },
  buttonPressed: {
    backgroundColor: "#0056CC",
    transform: [{ scale: 0.98 }],
  },
  buttonText: {
    color: "white",
    fontWeight: "600",
    fontSize: 16,
  },
  buttonTextPressed: {
    opacity: 0.8,
  },
});
