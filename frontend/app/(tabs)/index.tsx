import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator, TouchableOpacity } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { api, Quote } from "@/src/api";
import { colors, fonts } from "@/src/theme";
import { StockRow } from "@/src/components/StockRow";
import { Settings as SettingsIcon } from "lucide-react-native";

export default function Market() {
  const router = useRouter();
  const [indices, setIndices] = useState<Quote[]>([]);
  const [stocks, setStocks] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [idx, pop] = await Promise.all([api.indices(), api.popular()]);
      setIndices(idx);
      setStocks(pop);
    } catch (e) {
      console.warn("market load", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(); };

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header} testID="market-header">
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Indian Markets</Text>
          <Text style={styles.subtitle}>NSE • BSE • Live Quotes</Text>
        </View>
        <TouchableOpacity testID="open-settings" onPress={() => router.push("/settings")} style={styles.settingsBtn}>
          <SettingsIcon color={colors.textSecondary} size={20} />
        </TouchableOpacity>
      </View>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 120 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
      >
        <View style={styles.indices} testID="indices-row">
          {loading && <ActivityIndicator color={colors.accent} style={{ margin: 20 }} />}
          {indices.map((i) => {
            const positive = i.change_pct >= 0;
            return (
              <View key={i.symbol} style={styles.indexCard} testID={`index-${i.symbol}`}>
                <Text style={styles.indexName} numberOfLines={1}>{i.name}</Text>
                <Text style={styles.indexPrice}>{i.price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
                <Text style={[styles.indexChange, { color: positive ? colors.profit : colors.loss }]}>
                  {positive ? "+" : ""}{i.change_pct.toFixed(2)}%
                </Text>
              </View>
            );
          })}
        </View>

        <Text style={styles.section}>Popular Stocks</Text>
        <View style={styles.listCard}>
          {stocks.map((s) => (
            <StockRow
              key={s.symbol}
              symbol={s.symbol}
              name={s.name}
              price={s.price}
              change={s.change}
              change_pct={s.change_pct}
            />
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 16, flexDirection: "row", alignItems: "center" },
  settingsBtn: { padding: 8, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 26 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 4, letterSpacing: 1 },
  indices: { flexDirection: "row", paddingHorizontal: 12, gap: 10 },
  indexCard: {
    flex: 1, backgroundColor: colors.surface, borderRadius: 12, padding: 12,
    borderWidth: 1, borderColor: colors.border,
  },
  indexName: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 11 },
  indexPrice: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 16, marginTop: 6 },
  indexChange: { fontFamily: fonts.mono, fontSize: 12, marginTop: 4 },
  section: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 18, paddingHorizontal: 16, marginTop: 24, marginBottom: 10 },
  listCard: { marginHorizontal: 12, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
});
