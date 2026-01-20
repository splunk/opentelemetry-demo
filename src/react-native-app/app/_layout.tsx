// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
import { SplashScreen, Stack } from "expo-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  DarkTheme,
  DefaultTheme,
  ThemeProvider,
} from "@react-navigation/native";
import { useColorScheme } from "react-native";
import { RootSiblingParent } from "react-native-root-siblings";
import Toast from "react-native-toast-message";
import { useFonts } from "expo-font";
import { useEffect } from "react";
import { SplunkRumProvider } from "@/components/SplunkRumProvider";
import CartProvider from "@/providers/Cart.provider";

const queryClient = new QueryClient();

export default function RootLayout() {
  const colorScheme = useColorScheme();
  const [fontsLoaded] = useFonts({
    SpaceMono: require("../assets/fonts/SpaceMono-Regular.ttf"),
  });

  useEffect(() => {
    if (fontsLoaded) {
      SplashScreen.hideAsync();
    }
  }, [fontsLoaded]);

  if (!fontsLoaded) {
    return null;
  }

  return (
    <ThemeProvider value={colorScheme === "dark" ? DarkTheme : DefaultTheme}>
      <RootSiblingParent>
        {/*
          Splunk RUM Provider using official OtelWrapper pattern
          This follows the recommended Splunk RUM setup for React Native
          and enables automatic HTTP request instrumentation
        */}
        <SplunkRumProvider>
          <QueryClientProvider client={queryClient}>
            <CartProvider>
              <Stack>
                <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
              </Stack>
            </CartProvider>
          </QueryClientProvider>
        </SplunkRumProvider>
      </RootSiblingParent>
      <Toast />
    </ThemeProvider>
  );
}
