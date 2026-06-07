import { Stack } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import {
  useFonts as useIBMPlex,
  IBMPlexSans_400Regular,
  IBMPlexSans_500Medium,
  IBMPlexSans_600SemiBold,
} from "@expo-google-fonts/ibm-plex-sans";
import {
  JetBrainsMono_500Medium,
  JetBrainsMono_700Bold,
} from "@expo-google-fonts/jetbrains-mono";
import { Outfit_600SemiBold, Outfit_700Bold } from "@expo-google-fonts/outfit";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";

SplashScreen.preventAutoHideAsync();

export default function RootLayout() {
  const [iconsLoaded, iconsError] = useIconFonts();
  const [fontsLoaded] = useIBMPlex({
    IBMPlexSans_400Regular,
    IBMPlexSans_500Medium,
    IBMPlexSans_600SemiBold,
    JetBrainsMono_500Medium,
    JetBrainsMono_700Bold,
    Outfit_600SemiBold,
    Outfit_700Bold,
  });

  useEffect(() => {
    if ((iconsLoaded || iconsError) && fontsLoaded) {
      SplashScreen.hideAsync();
    }
  }, [iconsLoaded, iconsError, fontsLoaded]);

  if ((!iconsLoaded && !iconsError) || !fontsLoaded) return null;

  return (
    <SafeAreaProvider>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: "#0A0A0A" } }}>
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="stock/[symbol]" options={{ presentation: "card" }} />
      </Stack>
    </SafeAreaProvider>
  );
}
