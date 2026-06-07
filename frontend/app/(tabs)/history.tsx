import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, Trade } from "@/src/api";
import { colors, fonts } from "@/src/theme";

export default function History() {
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.trades();
      setTrades(data);
    } catch (e) {
      console.warn(e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.title}>Trade History</Text>
        <Text style={styles.subtitle}>{trades.length} {trades.length === 1 ? "trade" : "trades"}</Text>
      </View>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 120 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.accent} />}
      >
        {loading && <ActivityIndicator color={colors.accent} style={{ marginTop: 60 }} />}
        {!loading && trades.length === 0 && (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No trades yet</Text>
            <Text style={styles.emptyHint}>Place your first paper trade from the Market or Signals tab</Text>
          </View>
        )}
        <View style={styles.list}>
          {trades.map((t) => {
            const buy = t.side === "BUY";
            const dt = new Date(t.timestamp);
            const cleanSym = t.symbol.replace(".NS", "");
            return (
              <View key={t.id} style={styles.row} testID={`trade-${t.id}`}>
                <View style={[styles.sideTag, { backgroundColor: (buy ? colors.profit : colors.loss) + "22", borderColor: buy ? colors.profit : colors.loss }]}>
                  <Text style={[styles.sideText, { color: buy ? colors.profit : colors.loss }]}>{t.side}</Text>
                </View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.sym}>{cleanSym}</Text>
                  <Text style={styles.meta}>{t.quantity} × ₹{t.price.toFixed(2)}</Text>
                  <Text style={styles.dt}>{dt.toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}</Text>
                </View>
                <Text style={styles.total}>₹{t.total.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
              </View>
            );
          })}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 16 },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 26 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 4 },
  list: { marginHorizontal: 12, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", padding: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  sideTag: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: 6, borderWidth: 1, minWidth: 54, alignItems: "center" },
  sideText: { fontFamily: fonts.bodySemi, fontSize: 11 },
  sym: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 14 },
  meta: { fontFamily: fonts.mono, color: colors.textSecondary, fontSize: 11, marginTop: 2 },
  dt: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, marginTop: 2 },
  total: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 14 },
  empty: { alignItems: "center", marginTop: 80, paddingHorizontal: 24 },
  emptyText: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 16 },
  emptyHint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 13, marginTop: 6, textAlign: "center" },
});
