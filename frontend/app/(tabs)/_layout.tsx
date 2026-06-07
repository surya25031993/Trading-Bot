import { Tabs } from "expo-router";
import { Home, Star, TrendingUp, Briefcase, History } from "lucide-react-native";
import { colors, fonts } from "@/src/theme";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Platform } from "react-native";

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.accent,
        tabBarInactiveTintColor: colors.textMuted,
        tabBarStyle: {
          backgroundColor: colors.bg,
          borderTopColor: colors.border,
          borderTopWidth: 0.5,
          height: 56 + insets.bottom,
          paddingBottom: insets.bottom + (Platform.OS === "ios" ? 0 : 6),
          paddingTop: 6,
        },
        tabBarLabelStyle: { fontFamily: fonts.bodyMed, fontSize: 11 },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Market",
          tabBarIcon: ({ color, size }) => <Home color={color} size={size} />,
          tabBarTestID: "tab-market",
        }}
      />
      <Tabs.Screen
        name="signals"
        options={{
          title: "Signals",
          tabBarIcon: ({ color, size }) => <TrendingUp color={color} size={size} />,
          tabBarTestID: "tab-signals",
        }}
      />
      <Tabs.Screen
        name="watchlist"
        options={{
          title: "Watchlist",
          tabBarIcon: ({ color, size }) => <Star color={color} size={size} />,
          tabBarTestID: "tab-watchlist",
        }}
      />
      <Tabs.Screen
        name="portfolio"
        options={{
          title: "Portfolio",
          tabBarIcon: ({ color, size }) => <Briefcase color={color} size={size} />,
          tabBarTestID: "tab-portfolio",
        }}
      />
      <Tabs.Screen
        name="history"
        options={{
          title: "History",
          tabBarIcon: ({ color, size }) => <History color={color} size={size} />,
          tabBarTestID: "tab-history",
        }}
      />
    </Tabs>
  );
}
