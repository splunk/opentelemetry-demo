// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import { Pressable, StyleSheet, View } from "react-native";
import { ThemedText } from "./ThemedText";
import Toast from "react-native-toast-message";

export function ErrorTestButtons() {
  const handleErrorPress = () => {
    console.log("Testing caught error with Splunk RUM...");

    try {
      // Create an intentional error
      throw new Error("Test Error: This is a caught error for RUM testing");
    } catch (error) {
      // Log the error - Splunk RUM will automatically capture console.error
      console.error("Caught error for RUM testing:", error);

      // Show toast notification
      Toast.show({
        type: "error",
        position: "bottom",
        text1: "Error Thrown & Caught",
        text2: "Check Splunk RUM for error data",
        visibilityTime: 3000,
      });
    }
  };

  const handleCrashPress = () => {
    console.log("Testing uncaught error with Splunk RUM...");

    // Show warning toast first
    Toast.show({
      type: "error",
      position: "bottom",
      text1: "Uncaught Error",
      text2: "Throwing uncaught error in 2 seconds...",
      visibilityTime: 2000,
    });

    // Delay the error to allow the toast to show
    setTimeout(() => {
      // This will throw an uncaught error
      // In dev mode, React Native will show the red error screen
      // In production, this would crash the app
      throw new Error("Test Uncaught Error: Testing error boundary and crash reporting");
    }, 2000);
  };

  return (
    <View style={styles.container}>
      <Pressable
        style={({ pressed }) => [
          styles.button,
          styles.errorButton,
          pressed && styles.buttonPressed
        ]}
        onPress={handleErrorPress}
      >
        {({ pressed }) => (
          <ThemedText style={[
            styles.buttonText,
            pressed && styles.buttonTextPressed
          ]}>
            Trigger Caught Error
          </ThemedText>
        )}
      </Pressable>

      <Pressable
        style={({ pressed }) => [
          styles.button,
          styles.crashButton,
          pressed && styles.buttonPressed
        ]}
        onPress={handleCrashPress}
      >
        {({ pressed }) => (
          <ThemedText style={[
            styles.buttonText,
            pressed && styles.buttonTextPressed
          ]}>
            Trigger Uncaught Error
          </ThemedText>
        )}
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 10,
  },
  button: {
    borderRadius: 8,
    paddingVertical: 12,
    paddingHorizontal: 20,
    alignItems: "center",
    marginVertical: 5,
  },
  errorButton: {
    backgroundColor: "#FF9800",
  },
  crashButton: {
    backgroundColor: "#F44336",
  },
  buttonPressed: {
    opacity: 0.7,
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
