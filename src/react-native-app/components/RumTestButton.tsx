// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import { Pressable, StyleSheet } from "react-native";
import { ThemedText } from "./ThemedText";
import { trace } from "@opentelemetry/api";
import Toast from "react-native-toast-message";

export function RumTestButton() {
  const handlePress = () => {
    console.log("Creating test RUM span...");

    const tracer = trace.getTracer("test-tracer");
    const span = tracer.startSpan("test-button-click");

    span.setAttribute("component", "test");
    span.setAttribute("action", "button.click");
    span.setAttribute("test.id", "rum-test-button");

    console.log("Test span created:", span);

    // Show toast notification
    Toast.show({
      type: "success",
      position: "bottom",
      text1: "RUM Span Created",
      text2: "Check console for details",
      visibilityTime: 2000,
    });

    // End span after a short delay to simulate work
    setTimeout(() => {
      span.end();
      console.log("Test span ended");
    }, 100);
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
