import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator, TouchableOpacity, Alert } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, Portfolio } from "@/src/api";
import { colors, fonts } from "@/src/theme";
import { useRouter } from "expo-router";
import { RotateCcw } from "lucide-react-native";

export default function PortfolioScreen() {
  const [port, setPort] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const router = useRouter();

  const load = useCallback(async () => {
    try {
      const data = await api.portfolio();
      setPort(data);
    } catch (e) {
      console.warn("portfolio", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const reset = () => {
    Alert.alert("Reset Portfolio?", "This wipes all paper trades and resets cash to ₹10,00,000.", [
      { text: "Cancel", style: "cancel" },
      { text: "Reset", style: "destructive", onPress: async () => { await api.resetPortfolio(); load(); } },
    ]);
  };

  if (loading || !port) {
    return (
      <SafeAreaView style={styles.container} edges={["top"]}>
        <ActivityIndicator color={colors.accent} style={{ marginTop: 80 }} />
      </SafeAreaView>
    );
  }

  const totalPositive = port.overall_pnl >= 0;

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Portfolio</Text>
          <Text style={styles.subtitle}>Paper Trading</Text>
        </View>
        <TouchableOpacity testID="reset-portfolio" onPress={reset} style={styles.resetBtn}>
          <RotateCcw color={colors.textMuted} size={18} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 120 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.accent} />}
      >
        <View style={styles.summary} testID="portfolio-summary">
          <Text style={styles.summaryLabel}>NET WORTH</Text>
          <Text style={styles.netWorth}>₹{port.net_worth.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
          <Text style={[styles.overall, { color: totalPositive ? colors.profit : colors.loss }]}>
            {totalPositive ? "+" : ""}₹{port.overall_pnl.toLocaleString("en-IN", { maximumFractionDigits: 2 })}  ({totalPositive ? "+" : ""}{port.overall_pnl_pct.toFixed(2)}%)
          </Text>

          <View style={styles.statsRow}>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>Cash</Text>
              <Text style={styles.statValue}>₹{port.cash.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>Invested</Text>
              <Text style={styles.statValue}>₹{port.invested.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
            </View>
            <View style={styles.stat}>
              <Text style={styles.statLabel}>Day P&L</Text>
              <Text style={[styles.statValue, { color: port.total_pnl >= 0 ? colors.profit : colors.loss }]}>
                {port.total_pnl >= 0 ? "+" : ""}{port.total_pnl_pct.toFixed(2)}%
              </Text>
            </View>
          </View>
        </View>

        <Text style={styles.section}>Holdings ({port.positions.length})</Text>
        {port.positions.length === 0 && (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No holdings yet</Text>
            <Text style={styles.emptyHint}>Buy your first stock from any signal or detail page</Text>
          </View>
        )}
        <View style={styles.list}>
          {port.positions.map((p) => {
            const pos = p.pnl >= 0;
            const cleanSym = p.symbol.replace(".NS", "");
            return (
              <TouchableOpacity
                key={p.symbol}
                testID={`position-${cleanSym}`}
                onPress={() => router.push({ pathname: "/stock/[symbol]", params: { symbol: p.symbol, name: p.name } })}
                activeOpacity={0.7}
                style={styles.row}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.sym}>{cleanSym}</Text>
                  <Text style={styles.qty}>{p.quantity} @ ₹{p.avg_price.toFixed(2)}</Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={styles.price}>₹{p.current_value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
                  <Text style={[styles.pnl, { color: pos ? colors.profit : colors.loss }]}>
                    {pos ? "+" : ""}₹{p.pnl.toFixed(2)} ({pos ? "+" : ""}{p.pnl_pct.toFixed(2)}%)
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
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 16, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 26 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 4 },
  resetBtn: { padding: 10, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  summary: { marginHorizontal: 12, backgroundColor: colors.surface, padding: 20, borderRadius: 14, borderWidth: 1, borderColor: colors.border },
  summaryLabel: { fontFamily: fonts.bodyMed, color: colors.textMuted, fontSize: 10, letterSpacing: 2 },
  netWorth: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 30, marginTop: 6 },
  overall: { fontFamily: fonts.mono, fontSize: 14, marginTop: 6 },
  statsRow: { flexDirection: "row", marginTop: 18, gap: 12 },
  stat: { flex: 1 },
  statLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, letterSpacing: 1 },
  statValue: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 14, marginTop: 4 },
  section: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 16, paddingHorizontal: 16, marginTop: 24, marginBottom: 10 },
  empty: { alignItems: "center", marginTop: 30, paddingHorizontal: 24 },
  emptyText: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 14 },
  emptyHint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 6, textAlign: "center" },
  list: { marginHorizontal: 12, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", padding: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  sym: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 15 },
  qty: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 11, marginTop: 2 },
  price: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 14 },
  pnl: { fontFamily: fonts.mono, fontSize: 11, marginTop: 2 },
});
