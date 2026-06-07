// Shared theme tokens for the algo trading app
export const colors = {
  bg: "#0A0A0A",
  surface: "#141414",
  surfaceElev: "#1A1A1A",
  border: "#27272A",
  borderSubtle: "#27272A80",
  textPrimary: "#FFFFFF",
  textSecondary: "#A1A1AA",
  textMuted: "#71717A",
  profit: "#10B981",
  loss: "#EF4444",
  neutral: "#3B82F6",
  warning: "#F59E0B",
  accent: "#007AFF",
};

export const fonts = {
  heading: "Outfit_700Bold",
  headingSemi: "Outfit_600SemiBold",
  body: "IBMPlexSans_400Regular",
  bodyMed: "IBMPlexSans_500Medium",
  bodySemi: "IBMPlexSans_600SemiBold",
  mono: "JetBrainsMono_500Medium",
  monoBold: "JetBrainsMono_700Bold",
};

export const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;
