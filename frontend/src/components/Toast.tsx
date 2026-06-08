import React, { useEffect, useRef } from "react";
import { View, Text, StyleSheet, Animated, TouchableOpacity, Platform } from "react-native";
import { colors, fonts } from "@/src/theme";
import { TrendingUp, TrendingDown, X } from "lucide-react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

export type Toast = {
  id: number;
  side: "BUY" | "SELL";
  symbol: string;
  qty: number;
  price: number;
};

export function ToastContainer({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: number) => void }) {
  const insets = useSafeAreaInsets();
  return (
    <View pointerEvents="box-none" style={[styles.container, { top: insets.top + 8 }]}>
      {toasts.map((t, i) => (
        <ToastCard key={t.id} toast={t} onDismiss={onDismiss} index={i} />
      ))}
    </View>
  );
}

function ToastCard({ toast, onDismiss, index }: { toast: Toast; onDismiss: (id: number) => void; index: number }) {
  const slide = useRef(new Animated.Value(-100)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.spring(slide, { toValue: 0, useNativeDriver: true, friction: 8 }),
      Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: true }),
    ]).start();
    const timer = setTimeout(() => {
      Animated.parallel([
        Animated.timing(slide, { toValue: -100, duration: 250, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: true }),
      ]).start(() => onDismiss(toast.id));
    }, 4500);
    return () => clearTimeout(timer);
  }, []);

  const buy = toast.side === "BUY";
  const Icon = buy ? TrendingUp : TrendingDown;
  const color = buy ? colors.profit : colors.loss;
  const cleanSym = toast.symbol.replace(".NS", "").replace(".BO", "");

  return (
    <Animated.View
      style={[
        styles.toast,
        { transform: [{ translateY: slide }], opacity, top: index * 76, borderColor: color },
      ]}
      testID={`toast-${toast.id}`}
    >
      <View style={[styles.badge, { backgroundColor: color + "22" }]}>
        <Icon color={color} size={18} />
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Text style={styles.title}>
          🤖 Bot {buy ? "bought" : "sold"} <Text style={{ color }}>{cleanSym}</Text>
        </Text>
        <Text style={styles.sub}>
          {toast.qty} × ₹{toast.price.toFixed(2)} = ₹{(toast.qty * toast.price).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
        </Text>
      </View>
      <TouchableOpacity onPress={() => onDismiss(toast.id)} style={styles.close}>
        <X color={colors.textMuted} size={16} />
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: { position: "absolute", left: 12, right: 12, zIndex: 9999 },
  toast: {
    position: "absolute", left: 0, right: 0,
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.surface, borderRadius: 14, padding: 12,
    borderWidth: 1.5,
    ...(Platform.OS === "web"
      ? { boxShadow: "0 8px 24px rgba(0,0,0,0.4)" }
      : { shadowColor: "#000", shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.4, shadowRadius: 12, elevation: 8 }),
  },
  badge: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  title: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 13 },
  sub: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 11, marginTop: 2 },
  close: { padding: 6 },
});
