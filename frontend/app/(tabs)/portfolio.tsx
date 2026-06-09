import React, { useCallback, useEffect, useState, useMemo } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator, TouchableOpacity, Alert } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, Portfolio } from "@/src/api";
import { colors, fonts } from "@/src/theme";
import { useRouter } from "expo-router";
import { RotateCcw, Zap, BookOpen, AlertCircle } from "lucide-react-native";

function findFund(funds: any[], titles: string[]): number {
  if (!Array.isArray(funds)) return 0;
  const lower = titles.map(t => t.toLowerCase());
  const f = funds.find((x: any) => x?.title && lower.some(t => x.title.toLowerCase().includes(t)));
  return Number(f?.equityAmount || 0);
}

export default function PortfolioScreen() {
  const [port, setPort] = useState<Portfolio | null>(null);
  const [fyersHoldings, setFyersHoldings] = useState<any>(null);
  const [fyersPositions, setFyersPositions] = useState<any>(null);
  const [fyersFunds, setFyersFunds] = useState<any>(null);
  const [fyersStatus, setFyersStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [tab, setTab] = useState<"live" | "paper">("live");
  const router = useRouter();

  const load = useCallback(async () => {
    try {
      const data = await api.portfolio().catch(() => null);
      setPort(data);
      try {
        const s = await api.fyersStatus();
        setFyersStatus(s);
        if (s?.connected) {
          const [h, f, p] = await Promise.all([
            api.fyersHoldings().catch(() => null),
            api.fyersFunds().catch(() => null),
            api.fyersPositions().catch(() => null),
          ]);
          setFyersHoldings(h);
          setFyersFunds(f);
          setFyersPositions(p);
        }
      } catch {}
    } catch (e) {
      console.warn("portfolio", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Default to "paper" tab if Fyers is not connected
  useEffect(() => {
    if (fyersStatus && !fyersStatus.connected) setTab("paper");
  }, [fyersStatus]);

  const reset = () => {
    Alert.alert("Reset Paper Portfolio?", "This wipes all paper trades and resets cash to ₹10,00,000.", [
      { text: "Cancel", style: "cancel" },
      { text: "Reset", style: "destructive", onPress: async () => { await api.resetPortfolio(); load(); } },
    ]);
  };

  const fyers = useMemo(() => {
    const available = findFund(fyersFunds || [], ["available balance"]);
    const utilized = findFund(fyersFunds || [], ["utilized amount"]);
    const totalBalance = findFund(fyersFunds || [], ["total balance"]);
    const realizedPL = findFund(fyersFunds || [], ["realized profit"]);
    const collaterals = findFund(fyersFunds || [], ["collaterals"]);
    const holdingsValue = Number(fyersHoldings?.overall?.total_current_value || 0);
    const holdingsCost = Number(fyersHoldings?.overall?.total_investment || 0);
    const holdingsPL = Number(fyersHoldings?.overall?.total_pl || 0);
    const holdingsPLPct = Number(fyersHoldings?.overall?.pnl_perc || 0);
    const positionsPL = Number(fyersPositions?.overall?.pl_total || 0);
    const positionsRealized = Number(fyersPositions?.overall?.pl_realized || 0);
    const positionsUnrealized = Number(fyersPositions?.overall?.pl_unrealized || 0);
    const netWorth = available + holdingsValue;
    const dayPL = positionsPL + realizedPL;
    return {
      available, utilized, totalBalance, realizedPL, collaterals,
      holdingsValue, holdingsCost, holdingsPL, holdingsPLPct,
      positionsPL, positionsRealized, positionsUnrealized,
      netWorth, dayPL,
    };
  }, [fyersFunds, fyersHoldings, fyersPositions]);

  if (loading) {
    return (
      <SafeAreaView style={styles.container} edges={["top"]}>
        <ActivityIndicator color={colors.accent} style={{ marginTop: 80 }} />
      </SafeAreaView>
    );
  }

  const isLiveConnected = !!fyersStatus?.connected;
  const live = tab === "live" && isLiveConnected;

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Portfolio</Text>
          <Text style={styles.subtitle}>{live ? "LIVE • Fyers account" : "Paper trading (practice)"}</Text>
        </View>
        {!live && (
          <TouchableOpacity testID="reset-portfolio" onPress={reset} style={styles.resetBtn}>
            <RotateCcw color={colors.textMuted} size={18} />
          </TouchableOpacity>
        )}
      </View>

      {/* Tab switcher */}
      <View style={styles.tabRow}>
        <TouchableOpacity
          testID="tab-live"
          onPress={() => setTab("live")}
          style={[styles.tab, live && styles.tabActive, !isLiveConnected && styles.tabDisabled]}
          disabled={!isLiveConnected}
        >
          <Zap color={live ? colors.profit : (isLiveConnected ? colors.textMuted : colors.textMuted + "66")} size={13} />
          <Text style={[styles.tabText, live && { color: colors.profit }]}>LIVE</Text>
          {!isLiveConnected && <Text style={styles.tabHint}>Connect Fyers</Text>}
        </TouchableOpacity>
        <TouchableOpacity
          testID="tab-paper"
          onPress={() => setTab("paper")}
          style={[styles.tab, !live && styles.tabActive]}
        >
          <BookOpen color={!live ? colors.accent : colors.textMuted} size={13} />
          <Text style={[styles.tabText, !live && { color: colors.accent }]}>PAPER</Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 140 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.accent} />}
      >
        {live ? (
          /* === LIVE FYERS PORTFOLIO === */
          <>
            <View style={styles.summary} testID="fyers-summary">
              <View style={styles.liveBadgeRow}>
                <View style={styles.liveDot} />
                <Text style={styles.liveBadge}>LIVE • Fyers</Text>
              </View>
              <Text style={styles.summaryLabel}>NET WORTH</Text>
              <Text style={styles.netWorth}>₹{fyers.netWorth.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
              <Text style={[styles.overall, { color: fyers.dayPL >= 0 ? colors.profit : colors.loss }]}>
                Day P&L  {fyers.dayPL >= 0 ? "+" : ""}₹{fyers.dayPL.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
              </Text>
              <View style={styles.statsRow}>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Available</Text>
                  <Text style={styles.statValue}>₹{fyers.available.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Holdings</Text>
                  <Text style={styles.statValue}>₹{fyers.holdingsValue.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Utilized</Text>
                  <Text style={styles.statValue}>₹{fyers.utilized.toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
                </View>
              </View>
            </View>

            {fyers.available === 0 && fyers.holdingsValue === 0 && (
              <View style={styles.emptyAccount} testID="empty-fyers-account">
                <AlertCircle color={colors.warning} size={18} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.emptyAccountTitle}>Fyers account is empty</Text>
                  <Text style={styles.emptyAccountHint}>
                    No funds and no holdings detected. Fund your account at fyers.in to start trading live.
                  </Text>
                </View>
              </View>
            )}

            <Text style={styles.section}>Holdings ({fyersHoldings?.holdings?.length || 0})</Text>
            {fyersHoldings?.overall && fyersHoldings.holdings?.length > 0 && (
              <View style={styles.overallRow}>
                <Text style={styles.overallLabel}>Invested ₹{(fyersHoldings.overall.total_investment || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
                <Text style={[styles.overallPL, { color: (fyersHoldings.overall.total_pl || 0) >= 0 ? colors.profit : colors.loss }]}>
                  {(fyersHoldings.overall.total_pl || 0) >= 0 ? "+" : ""}₹{(fyersHoldings.overall.total_pl || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}  ({(fyersHoldings.overall.pnl_perc || 0).toFixed(2)}%)
                </Text>
              </View>
            )}
            {(fyersHoldings?.holdings?.length || 0) === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyText}>No equity holdings</Text>
                <Text style={styles.emptyHint}>Buy stocks via Fyers or place orders through the Signals tab</Text>
              </View>
            ) : (
              <View style={styles.list}>
                {fyersHoldings.holdings.map((h: any, i: number) => {
                  const pl = Number(h.pl || 0);
                  const pos = pl >= 0;
                  const symbol = (h.symbol || "").replace("NSE:", "").replace("-EQ", "");
                  return (
                    <View key={i} style={styles.row} testID={`fyers-hold-${i}`}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.sym}>{symbol}</Text>
                        <Text style={styles.qty}>{h.quantity} @ ₹{(Number(h.costPrice) || 0).toFixed(2)}</Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={styles.price}>₹{(Number(h.marketVal) || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
                        <Text style={[styles.pnl, { color: pos ? colors.profit : colors.loss }]}>
                          {pos ? "+" : ""}₹{pl.toFixed(0)}
                        </Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}

            <Text style={styles.section}>Open Positions ({fyersPositions?.net_positions?.length || 0})</Text>
            {(fyersPositions?.net_positions?.length || 0) === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyText}>No open positions</Text>
                <Text style={styles.emptyHint}>Intraday positions will appear here once you place orders.</Text>
              </View>
            ) : (
              <View style={styles.list}>
                {fyersPositions.net_positions.map((p: any, i: number) => {
                  const pl = Number(p.pl || 0);
                  const pos = pl >= 0;
                  const symbol = (p.symbol || "").replace("NSE:", "").replace("BSE:", "").replace("-EQ", "");
                  return (
                    <View key={i} style={styles.row} testID={`fyers-pos-${i}`}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.sym}>{symbol}</Text>
                        <Text style={styles.qty}>{p.netQty} @ ₹{(Number(p.avgPrice) || 0).toFixed(2)}</Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={styles.price}>₹{(Number(p.ltp) || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
                        <Text style={[styles.pnl, { color: pos ? colors.profit : colors.loss }]}>
                          {pos ? "+" : ""}₹{pl.toFixed(0)}
                        </Text>
                      </View>
                    </View>
                  );
                })}
              </View>
            )}

            <View style={styles.fyersFooter}>
              <Text style={styles.fyersFooterText}>
                All values pulled live from your Fyers account ({fyersStatus?.access_expires_at?.slice(0, 10)}).
              </Text>
            </View>
          </>
        ) : (
          /* === PAPER PORTFOLIO === */
          <>
            <View style={styles.summary} testID="paper-summary">
              <Text style={styles.summaryLabel}>NET WORTH (PAPER)</Text>
              <Text style={styles.netWorth}>₹{(port?.net_worth || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
              <Text style={[styles.overall, { color: (port?.overall_pnl || 0) >= 0 ? colors.profit : colors.loss }]}>
                {(port?.overall_pnl || 0) >= 0 ? "+" : ""}₹{(port?.overall_pnl || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}  ({(port?.overall_pnl_pct || 0).toFixed(2)}%)
              </Text>
              <View style={styles.statsRow}>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Cash</Text>
                  <Text style={styles.statValue}>₹{(port?.cash || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Invested</Text>
                  <Text style={styles.statValue}>₹{(port?.invested || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Day P&L</Text>
                  <Text style={[styles.statValue, { color: (port?.total_pnl || 0) >= 0 ? colors.profit : colors.loss }]}>
                    {(port?.total_pnl || 0) >= 0 ? "+" : ""}{(port?.total_pnl_pct || 0).toFixed(2)}%
                  </Text>
                </View>
              </View>
            </View>

            <Text style={styles.section}>Paper Holdings ({port?.positions?.length || 0})</Text>
            {(port?.positions?.length || 0) === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyText}>No holdings yet</Text>
                <Text style={styles.emptyHint}>Buy your first stock from any signal or detail page</Text>
              </View>
            ) : (
              <View style={styles.list}>
                {port!.positions.map((p) => {
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
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 12, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 26 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 4 },
  resetBtn: { padding: 10, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },

  tabRow: { flexDirection: "row", marginHorizontal: 12, gap: 8, marginBottom: 8 },
  tab: { flex: 1, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 8, borderRadius: 10, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  tabActive: { borderColor: colors.accent + "88", backgroundColor: colors.accent + "10" },
  tabDisabled: { opacity: 0.5 },
  tabText: { fontFamily: fonts.bodySemi, color: colors.textMuted, fontSize: 11, letterSpacing: 1 },
  tabHint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, marginLeft: 4, fontStyle: "italic" },

  summary: { marginHorizontal: 12, backgroundColor: colors.surface, padding: 20, borderRadius: 14, borderWidth: 1, borderColor: colors.border, marginTop: 4 },
  liveBadgeRow: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 8 },
  liveDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.profit },
  liveBadge: { fontFamily: fonts.bodySemi, color: colors.profit, fontSize: 10, letterSpacing: 2 },
  summaryLabel: { fontFamily: fonts.bodyMed, color: colors.textMuted, fontSize: 10, letterSpacing: 2 },
  netWorth: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 30, marginTop: 6 },
  overall: { fontFamily: fonts.mono, fontSize: 14, marginTop: 6 },
  statsRow: { flexDirection: "row", marginTop: 18, gap: 12 },
  stat: { flex: 1 },
  statLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, letterSpacing: 1 },
  statValue: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 14, marginTop: 4 },

  emptyAccount: { flexDirection: "row", gap: 10, alignItems: "flex-start", marginHorizontal: 12, marginTop: 12, padding: 14, backgroundColor: colors.warning + "11", borderRadius: 12, borderWidth: 1, borderColor: colors.warning + "55" },
  emptyAccountTitle: { fontFamily: fonts.bodySemi, color: colors.warning, fontSize: 13 },
  emptyAccountHint: { fontFamily: fonts.body, color: colors.textPrimary, fontSize: 11, marginTop: 4, lineHeight: 16 },

  section: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 16, paddingHorizontal: 16, marginTop: 24, marginBottom: 10 },
  overallRow: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 16, marginBottom: 8 },
  overallLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11 },
  overallPL: { fontFamily: fonts.monoBold, fontSize: 12 },
  empty: { alignItems: "center", marginTop: 14, paddingHorizontal: 24, paddingVertical: 22, marginHorizontal: 12, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border },
  emptyText: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 14 },
  emptyHint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 6, textAlign: "center" },
  list: { marginHorizontal: 12, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", padding: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  sym: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 15 },
  qty: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 11, marginTop: 2 },
  price: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 14 },
  pnl: { fontFamily: fonts.mono, fontSize: 11, marginTop: 2 },

  fyersFooter: { marginTop: 16, paddingHorizontal: 18 },
  fyersFooterText: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, textAlign: "center", fontStyle: "italic" },
});
