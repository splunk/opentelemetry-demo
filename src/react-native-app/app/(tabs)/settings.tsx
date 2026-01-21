// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import { ThemedView } from "@/components/ThemedView";
import { ThemedText } from "@/components/ThemedText";
import { StyleSheet, ScrollView } from "react-native";
import { RegionSelector } from "@/components/RegionSelector";
import { RumTestButton } from "@/components/RumTestButton";
import { ErrorTestButtons } from "@/components/ErrorTestButtons";
import { APP_VERSION } from "@/constants/AppVersion";

export default function Settings() {
  return (
    <ScrollView>
      <ThemedView style={styles.container}>
        {/* Version Information */}
        <ThemedView style={styles.section}>
          <ThemedText style={styles.sectionTitle}>App Information</ThemedText>
          <ThemedView style={styles.infoRow}>
            <ThemedText style={styles.infoLabel}>Version:</ThemedText>
            <ThemedText style={styles.infoValue}>{APP_VERSION}</ThemedText>
          </ThemedView>
        </ThemedView>

        {/* Region Selector with Frontend Proxy URL */}
        <ThemedView style={styles.section}>
          <ThemedText style={styles.sectionTitle}>Splunk Configuration</ThemedText>
          <RegionSelector />
        </ThemedView>

        {/* Error Testing */}
        <ThemedView style={styles.section}>
          <ThemedText style={styles.sectionTitle}>Error Testing</ThemedText>
          <ThemedText style={styles.hint}>
            Test error tracking with Splunk RUM
          </ThemedText>
          <ErrorTestButtons />
        </ThemedView>

        {/* RUM Testing */}
        <ThemedView style={styles.section}>
          <ThemedText style={styles.sectionTitle}>RUM Testing</ThemedText>
          <ThemedText style={styles.hint}>
            Click the button below to manually create a test RUM span
          </ThemedText>
          <RumTestButton />
        </ThemedView>
      </ThemedView>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    display: "flex",
    gap: 30,
    paddingLeft: 20,
    paddingRight: 20,
    paddingTop: 20,
    paddingBottom: 40,
  },
  section: {
    gap: 15,
    paddingBottom: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: "bold",
    marginBottom: 5,
  },
  infoRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 8,
  },
  infoLabel: {
    fontWeight: "600",
    opacity: 0.8,
  },
  infoValue: {
    fontWeight: "500",
    color: "#4CAF50",
  },
  hint: {
    fontSize: 12,
    opacity: 0.7,
    fontStyle: "italic",
    marginBottom: 10,
  },
});
