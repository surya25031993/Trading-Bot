import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { api } from "@/src/api";
import { colors, fonts } from "@/src/theme";
import { TrendingUp, TrendingDown, Minus } from "lucide-react-native";

type SignalRow = {
  symbol: string; name: string; price: number; change_pct: number;
  consensus: "BUY" | "SELL" | "HOLD"; buy_count: number; sell_count: number; rsi: number;
};

export default function Signals() {
  const [rows, setRows] = useState<SignalRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<"ALL" | "BUY" | "SELL" | "HOLD">("ALL");
  const router = useRouter();

  const load = useCallback(async () => {
    try {
      const data = await api.topSignals();
      setRows(data);
    } catch (e) {
      console.warn("signals", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filtered = filter === "ALL" ? rows : rows.filter((r) => r.consensus === filter);
  const chips = ["ALL", "BUY", "SELL", "HOLD"] as const;

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.title}>Algo Signals</Text>
        <Text style={styles.subtitle}>SMA • EMA • RSI • MACD • Bollinger</Text>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipsRow}
        style={styles.chipsScroll}
      >
        {chips.map((c) => {
          const active = filter === c;
          return (
            <TouchableOpacity
              key={c}
              testID={`chip-${c}`}
              onPress={() => setFilter(c)}
              style={[styles.chip, active && styles.chipActive]}
              activeOpacity={0.7}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{c}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 120 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.accent} />}
      >
        {loading && <ActivityIndicator color={colors.accent} style={{ marginTop: 40 }} />}
        {!loading && filtered.length === 0 && (
          <Text style={styles.empty}>No {filter !== "ALL" ? filter : ""} signals right now. Pull to refresh.</Text>
        )}
        <View style={styles.list}>
          {filtered.map((r) => {
            const Icon = r.consensus === "BUY" ? TrendingUp : r.consensus === "SELL" ? TrendingDown : Minus;
            const color = r.consensus === "BUY" ? colors.profit : r.consensus === "SELL" ? colors.loss : colors.textMuted;
            const cleanSym = r.symbol.replace(".NS", "");
            return (
              <TouchableOpacity
                key={r.symbol}
                testID={`signal-${cleanSym}`}
                onPress={() => router.push({ pathname: "/stock/[symbol]", params: { symbol: r.symbol, name: r.name } })}
                style={styles.row}
                activeOpacity={0.7}
              >
                <View style={[styles.badge, { backgroundColor: color + "22", borderColor: color }]}>
                  <Icon color={color} size={16} />
                  <Text style={[styles.badgeText, { color }]}>{r.consensus}</Text>
                </View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.sym}>{cleanSym}</Text>
                  <Text style={styles.name} numberOfLines={1}>{r.name}</Text>
                  <Text style={styles.meta}>
                    {r.buy_count} buy · {r.sell_count} sell · RSI {r.rsi.toFixed(0)}
                  </Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={styles.price}>₹{r.price.toFixed(2)}</Text>
                  <Text style={[styles.chg, { color: r.change_pct >= 0 ? colors.profit : colors.loss }]}>
                    {r.change_pct >= 0 ? "+" : ""}{r.change_pct.toFixed(2)}%
                  </Text>
                </View>
              </TouchableOpacity>
            );
          })}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 8 },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 26 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11, marginTop: 4, letterSpacing: 1 },
  chipsScroll: { maxHeight: 56 },
  chipsRow: { paddingHorizontal: 16, paddingVertical: 10, gap: 8, alignItems: "center" },
  chip: {
    flexShrink: 0, height: 36, paddingHorizontal: 16, borderRadius: 18,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surface,
  },
  chipActive: { borderColor: colors.accent, backgroundColor: colors.accent + "22" },
  chipText: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 12 },
  chipTextActive: { color: colors.accent },
  list: { marginHorizontal: 12, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  row: {
    flexDirection: "row", alignItems: "center", paddingVertical: 14, paddingHorizontal: 14,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  badge: {
    flexDirection: "row", alignItems: "center", paddingHorizontal: 8, paddingVertical: 6, borderRadius: 8,
    borderWidth: 1, gap: 4, minWidth: 64, justifyContent: "center",
  },
  badgeText: { fontFamily: fonts.bodySemi, fontSize: 11 },
  sym: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 15 },
  name: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11, marginTop: 2 },
  meta: { fontFamily: fonts.mono, color: colors.textSecondary, fontSize: 10, marginTop: 2 },
  price: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 14 },
  chg: { fontFamily: fonts.mono, fontSize: 11, marginTop: 2 },
  empty: { fontFamily: fonts.body, color: colors.textMuted, textAlign: "center", marginTop: 60, paddingHorizontal: 24 },
});
