import React, { useCallback, useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, TouchableOpacity, RefreshControl } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, OptionCalcResult, OptionSuggestion, OptionLeg } from "@/src/api";
import { colors, fonts } from "@/src/theme";
import { PayoffChart } from "@/src/components/PayoffChart";
import { AdvancedChart, ChartData } from "@/src/components/AdvancedChart";
import { OptionPremiumChart, OptionCandle } from "@/src/components/OptionPremiumChart";
import { Sparkles, TrendingUp, TrendingDown, Minus } from "lucide-react-native";

function fyersUnavailableMsg(chain: any): string {
  if (!chain) return "Connect Fyers in Settings → Live option chain will appear here during market hours (9:15 AM – 3:30 PM IST).";
  if (chain.available === false) return chain.reason || "Option chain unavailable. Fyers connection may be needed.";
  return "Loading…";
}

type Index = "NIFTY" | "SENSEX" | "BANKNIFTY";
const INDICES: Index[] = ["NIFTY", "SENSEX", "BANKNIFTY"];

export default function Options() {
  const [index, setIndex] = useState<Index>("NIFTY");
  const [sugg, setSugg] = useState<OptionSuggestion | null>(null);
  const [calc, setCalc] = useState<OptionCalcResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [calcLoading, setCalcLoading] = useState(false);
  const [chain, setChain] = useState<any>(null);
  const [indexChart, setIndexChart] = useState<ChartData | null>(null);
  const [ceCandles, setCeCandles] = useState<OptionCandle[]>([]);
  const [peCandles, setPeCandles] = useState<OptionCandle[]>([]);
  const [atmInfo, setAtmInfo] = useState<{ ceSym: string; peSym: string; strike: number } | null>(null);
  const [tradeBusy, setTradeBusy] = useState(false);
  const [tradeMsg, setTradeMsg] = useState<string | null>(null);

  const load = useCallback(async (idx: Index) => {
    setLoading(true);
    try {
      const s = await api.optionsSuggest(idx);
      setSugg(s);
      const legs: OptionLeg[] = s.concrete_legs.map((l) => ({
        side: l.side, type: l.type, strike: l.strike, premium: l.premium_est, qty: l.qty,
      }));
      setCalcLoading(true);
      const c = await api.optionsCalculate({
        index: idx as any, spot: s.spot, days_to_expiry: 7, iv: 15, legs,
      });
      setCalc(c);
      // try fyers option chain first, fallback to NSE
      try {
        const ch = await fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL}/api/fyers/option-chain?index=${idx}&strike_count=8`).then(r => r.json());
        if (ch.available) {
          setChain(ch);
          // Get ATM symbols and fetch their intraday premium history
          const atmRow = ch.chain.find((r: any) => r.strike === ch.atm);
          if (atmRow && atmRow.ce_symbol && atmRow.pe_symbol) {
            setAtmInfo({ ceSym: atmRow.ce_symbol, peSym: atmRow.pe_symbol, strike: ch.atm });
            const [ce, pe] = await Promise.all([
              fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL}/api/fyers/history?symbol=${encodeURIComponent(atmRow.ce_symbol)}&resolution=5`).then(r => r.json()).catch(() => null),
              fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL}/api/fyers/history?symbol=${encodeURIComponent(atmRow.pe_symbol)}&resolution=5`).then(r => r.json()).catch(() => null),
            ]);
            setCeCandles(ce?.candles || []);
            setPeCandles(pe?.candles || []);
          }
        } else {
          setChain(null);
        }
      } catch {
        setChain(null);
      }
      // Load index advanced chart
      try {
        const idxSymMap: Record<string, string> = { NIFTY: "^NSEI", SENSEX: "^BSESN", BANKNIFTY: "^NSEBANK" };
        const sym = idxSymMap[idx];
        if (sym) {
          const ch = await api.stockChart(sym);
          setIndexChart(ch);
        }
      } catch (e) {
        console.warn("index chart load", e);
        setIndexChart(null);
      }
    } catch (e) {
      console.warn("options load", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
      setCalcLoading(false);
    }
  }, []);

  const placeStrategy = async () => {
    if (!sugg) return;
    setTradeBusy(true);
    try {
      const result = await api.optionsPaperTrade({
        index: sugg.index,
        legs: sugg.concrete_legs.map(l => ({
          side: l.side, type: l.type, strike: l.strike, premium: l.premium_est, qty: l.qty,
        })),
      });
      setTradeMsg(`✓ Paper trade placed: ${sugg.strategy.name} on ${sugg.index}`);
      setTimeout(() => setTradeMsg(null), 4000);
    } catch (e: any) {
      setTradeMsg(`Error: ${e.message}`);
      setTimeout(() => setTradeMsg(null), 4000);
    } finally {
      setTradeBusy(false);
    }
  };

  useEffect(() => { load(index); }, [index, load]);

  const consensusColor = (c: string) => c === "BUY" ? colors.profit : c === "SELL" ? colors.loss : colors.warning;
  const ConsensusIcon = sugg?.consensus === "BUY" ? TrendingUp : sugg?.consensus === "SELL" ? TrendingDown : Minus;

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.title}>Options</Text>
        <Text style={styles.subtitle}>NIFTY • SENSEX • BANK NIFTY</Text>
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipsScroll}
        contentContainerStyle={styles.chipsRow}
      >
        {INDICES.map((i) => {
          const active = index === i;
          return (
            <TouchableOpacity
              key={i}
              testID={`chip-${i}`}
              onPress={() => setIndex(i)}
              style={[styles.chip, active && styles.chipActive]}
              activeOpacity={0.7}
            >
              <Text style={[styles.chipText, active && styles.chipTextActive]}>{i}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 140 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(index); }} tintColor={colors.accent} />}
      >
        {loading && <ActivityIndicator color={colors.accent} style={{ marginTop: 40 }} />}

        {sugg && !loading && (
          <>
            {/* Index snapshot */}
            <View style={styles.card} testID="index-snapshot">
              <View style={styles.rowBetween}>
                <Text style={styles.cardTitle}>{sugg.index}</Text>
                <Text style={[styles.cardChange, { color: sugg.change_pct >= 0 ? colors.profit : colors.loss }]}>
                  {sugg.change_pct >= 0 ? "+" : ""}{sugg.change_pct.toFixed(2)}%
                </Text>
              </View>
              <Text style={styles.spot}>₹{sugg.spot.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
              <View style={styles.statsRow}>
                <View style={styles.stat}><Text style={styles.statLabel}>ATM</Text><Text style={styles.statVal}>{sugg.atm}</Text></View>
                <View style={styles.stat}><Text style={styles.statLabel}>RSI</Text><Text style={styles.statVal}>{sugg.rsi.toFixed(1)}</Text></View>
                <View style={styles.stat}><Text style={styles.statLabel}>Lot Size</Text><Text style={styles.statVal}>{sugg.lot_size}</Text></View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Trend</Text>
                  <View style={[styles.viewTag, { backgroundColor: consensusColor(sugg.consensus) + "22", borderColor: consensusColor(sugg.consensus) }]}>
                    <ConsensusIcon color={consensusColor(sugg.consensus)} size={11} />
                    <Text style={[styles.viewTagText, { color: consensusColor(sugg.consensus) }]}>{sugg.consensus}</Text>
                  </View>
                </View>
              </View>
            </View>

            {/* Index Technical Chart */}
            {indexChart && (
              <View style={styles.card} testID="index-chart">
                <Text style={styles.cardTitle}>{sugg.index} Technical Chart · All Indicators</Text>
                <AdvancedChart data={indexChart} />
              </View>
            )}

            {/* Strategy recommendation */}
            <View style={styles.card} testID="strategy-card">
              <View style={styles.rowBetween}>
                <View style={styles.sparkles}>
                  <Sparkles color={colors.accent} size={14} />
                  <Text style={styles.cardLabel}>RECOMMENDED STRATEGY</Text>
                </View>
              </View>
              <Text style={styles.stratName}>{sugg.strategy.name}</Text>
              <Text style={styles.stratView}>View: {sugg.strategy.view}</Text>
              <Text style={styles.stratDesc}>{sugg.strategy.description}</Text>
              <View style={styles.miniGrid}>
                <View style={styles.miniCard}><Text style={styles.miniLabel}>RISK</Text><Text style={styles.miniVal}>{sugg.strategy.risk}</Text></View>
                <View style={styles.miniCard}><Text style={styles.miniLabel}>REWARD</Text><Text style={styles.miniVal}>{sugg.strategy.reward}</Text></View>
              </View>
            </View>

            {/* Legs */}
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Trade Setup ({sugg.concrete_legs.length} legs)</Text>
              {sugg.concrete_legs.map((leg, i) => {
                const sideColor = leg.side === "BUY" ? colors.profit : colors.loss;
                return (
                  <View key={i} style={styles.legRow} testID={`leg-${i}`}>
                    <View style={[styles.sideBadge, { backgroundColor: sideColor + "22", borderColor: sideColor }]}>
                      <Text style={[styles.sideBadgeText, { color: sideColor }]}>{leg.side}</Text>
                    </View>
                    <View style={{ flex: 1, marginLeft: 12 }}>
                      <Text style={styles.legMain}>{leg.strike} {leg.type === "CE" ? "CALL" : "PUT"}</Text>
                      <Text style={styles.legSub}>Premium ~₹{leg.premium_est.toFixed(2)} · Qty {leg.qty} lot</Text>
                    </View>
                  </View>
                );
              })}
              <Text style={styles.note}>{sugg.note}</Text>
            </View>

            {/* Paper trade button */}
            <View style={styles.tradeRow}>
              <TouchableOpacity
                testID="paper-trade-strategy"
                onPress={placeStrategy}
                disabled={tradeBusy}
                style={[styles.tradeBtn, { backgroundColor: sugg.consensus === "BUY" ? colors.profit : sugg.consensus === "SELL" ? colors.loss : colors.accent }]}
                activeOpacity={0.8}
              >
                <Text style={styles.tradeBtnText}>
                  {tradeBusy ? "Placing…" : `Paper Trade ${sugg.strategy.name}`}
                </Text>
              </TouchableOpacity>
            </View>
            {tradeMsg && <Text style={[styles.toast, { color: tradeMsg.startsWith("✓") ? colors.profit : colors.loss }]} testID="trade-toast">{tradeMsg}</Text>}

            {/* Live Option Premium Charts (CE + PE) */}
            {atmInfo && (ceCandles.length > 0 || peCandles.length > 0) && (
              <View style={styles.card} testID="option-premium-charts">
                <Text style={styles.cardTitle}>ATM {atmInfo.strike} · Live Premium Chart (5m)</Text>
                <View style={{ marginTop: 8 }}>
                  <OptionPremiumChart candles={ceCandles} title={`CALL ${atmInfo.strike}`} color={colors.profit} />
                </View>
                <View style={{ marginTop: 14 }}>
                  <OptionPremiumChart candles={peCandles} title={`PUT ${atmInfo.strike}`} color={colors.loss} />
                </View>
                <Text style={styles.chainHint}>Source: Fyers · 5-min candles · last 5 days</Text>
              </View>
            )}

            {/* Live Option Chain */}
            {chain?.available && chain?.chain?.length > 0 ? (
              <View style={styles.card} testID="option-chain">
                <Text style={styles.cardTitle}>Live Option Chain · {chain.expiry}</Text>
                <View style={styles.chainHeader}>
                  <Text style={styles.chainCol}>CALL LTP</Text>
                  <Text style={styles.chainCol}>OI</Text>
                  <Text style={[styles.chainCol, styles.strikeCol]}>STRIKE</Text>
                  <Text style={styles.chainCol}>OI</Text>
                  <Text style={styles.chainCol}>PUT LTP</Text>
                </View>
                {chain.chain.map((row: any, i: number) => {
                  const isATM = row.strike === chain.atm;
                  return (
                    <View key={i} style={[styles.chainRow, isATM && styles.chainRowATM]} testID={`chain-${row.strike}`}>
                      <Text style={[styles.chainCol, { color: colors.profit }]}>{row.ce_ltp?.toFixed(1) || "-"}</Text>
                      <Text style={[styles.chainCol, styles.chainOI]}>{((row.ce_oi || 0) / 1000).toFixed(0)}k</Text>
                      <Text style={[styles.chainCol, styles.strikeCol, isATM && { color: colors.accent, fontFamily: fonts.monoBold }]}>{row.strike}</Text>
                      <Text style={[styles.chainCol, styles.chainOI]}>{((row.pe_oi || 0) / 1000).toFixed(0)}k</Text>
                      <Text style={[styles.chainCol, { color: colors.loss }]}>{row.pe_ltp?.toFixed(1) || "-"}</Text>
                    </View>
                  );
                })}
                <Text style={styles.chainHint}>Source: Fyers Live · ATM ₹{chain.atm} highlighted</Text>
              </View>
            ) : (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>Live Option Chain</Text>
                <Text style={styles.chainEmpty}>
                  {fyersUnavailableMsg(chain)}
                </Text>
              </View>
            )}

            {/* Payoff Chart */}
            {calc && (
              <View style={styles.card} testID="payoff-card">
                <Text style={styles.cardTitle}>Payoff at Expiry</Text>
                <PayoffChart payoff={calc.payoff} spot={sugg.spot} breakevens={calc.breakevens} />
                <View style={styles.payoffStats}>
                  <View style={styles.payoffStat}>
                    <Text style={styles.payoffLabel}>Max Profit</Text>
                    <Text style={[styles.payoffVal, { color: colors.profit }]}>
                      {calc.max_profit === null ? "Unlimited" : `₹${calc.max_profit.toLocaleString("en-IN")}`}
                    </Text>
                  </View>
                  <View style={styles.payoffStat}>
                    <Text style={styles.payoffLabel}>Max Loss</Text>
                    <Text style={[styles.payoffVal, { color: colors.loss }]}>
                      {calc.max_loss === null ? "Unlimited" : `₹${calc.max_loss.toLocaleString("en-IN")}`}
                    </Text>
                  </View>
                  <View style={styles.payoffStat}>
                    <Text style={styles.payoffLabel}>P(Profit)</Text>
                    <Text style={styles.payoffVal}>{calc.probability_of_profit_pct ?? "—"}%</Text>
                  </View>
                </View>
                <View style={styles.beRow}>
                  <Text style={styles.beLabel}>Breakevens:</Text>
                  <Text style={styles.beVal}>
                    {calc.breakevens.length ? calc.breakevens.map((b) => `₹${b}`).join(" · ") : "—"}
                  </Text>
                </View>
                <View style={styles.greeks} testID="greeks-grid">
                  <Text style={styles.greeksTitle}>Greeks (today)</Text>
                  <View style={styles.greeksGrid}>
                    <GreekCell label="Δ Delta" value={calc.greeks.delta.toFixed(2)} hint="Spot sensitivity" />
                    <GreekCell label="Γ Gamma" value={calc.greeks.gamma.toFixed(4)} hint="Delta change" />
                    <GreekCell label="Θ Theta" value={calc.greeks.theta.toFixed(2)} hint="Per day decay" />
                    <GreekCell label="V Vega" value={calc.greeks.vega.toFixed(2)} hint="Per 1% vol" />
                  </View>
                </View>
                <Text style={styles.netPrem}>
                  Net {calc.net_premium >= 0 ? "Credit" : "Debit"}: ₹{Math.abs(calc.net_premium).toLocaleString("en-IN", { maximumFractionDigits: 2 })}
                </Text>
              </View>
            )}
            {calcLoading && !calc && <ActivityIndicator color={colors.accent} style={{ marginTop: 12 }} />}

            <Text style={styles.disclaimer}>
              ⚠ Options trading is high risk. Premiums shown are Black-Scholes estimates, not live NSE prices. Always check live option chain before placing trades.
            </Text>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function GreekCell({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <View style={styles.greekCell}>
      <Text style={styles.greekLabel}>{label}</Text>
      <Text style={styles.greekValue}>{value}</Text>
      <Text style={styles.greekHint}>{hint}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 4 },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 26 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11, marginTop: 4, letterSpacing: 1 },
  chipsScroll: { maxHeight: 56 },
  chipsRow: { paddingHorizontal: 16, paddingVertical: 10, gap: 8, alignItems: "center" },
  chip: {
    flexShrink: 0, height: 36, paddingHorizontal: 18, borderRadius: 18,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.surface,
  },
  chipActive: { borderColor: colors.accent, backgroundColor: colors.accent + "22" },
  chipText: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 12 },
  chipTextActive: { color: colors.accent },

  card: { marginHorizontal: 12, marginTop: 12, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16 },
  cardTitle: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 15 },
  cardLabel: { fontFamily: fonts.bodySemi, color: colors.accent, fontSize: 10, letterSpacing: 2 },
  cardChange: { fontFamily: fonts.mono, fontSize: 13 },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sparkles: { flexDirection: "row", alignItems: "center", gap: 6 },
  spot: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 30, marginTop: 8 },
  statsRow: { flexDirection: "row", marginTop: 14, gap: 8 },
  stat: { flex: 1 },
  statLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  statVal: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 13, marginTop: 3 },
  viewTag: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 6, paddingVertical: 3, borderRadius: 6, borderWidth: 1, alignSelf: "flex-start", marginTop: 3 },
  viewTagText: { fontFamily: fonts.bodySemi, fontSize: 9 },

  stratName: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 22, marginTop: 8 },
  stratView: { fontFamily: fonts.bodyMed, color: colors.accent, fontSize: 12, marginTop: 4 },
  stratDesc: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 13, lineHeight: 19, marginTop: 8 },
  miniGrid: { flexDirection: "row", gap: 10, marginTop: 14 },
  miniCard: { flex: 1, backgroundColor: colors.bg, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: colors.border },
  miniLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  miniVal: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 12, marginTop: 4 },

  legRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  sideBadge: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, borderWidth: 1, minWidth: 50, alignItems: "center" },
  sideBadgeText: { fontFamily: fonts.bodySemi, fontSize: 11 },
  legMain: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 14 },
  legSub: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 11, marginTop: 2 },
  note: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, marginTop: 12, fontStyle: "italic" },

  payoffStats: { flexDirection: "row", marginTop: 14, gap: 8 },
  payoffStat: { flex: 1, backgroundColor: colors.bg, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: colors.border },
  payoffLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  payoffVal: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 13, marginTop: 4 },
  beRow: { flexDirection: "row", marginTop: 12, alignItems: "center", gap: 8 },
  beLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11 },
  beVal: { fontFamily: fonts.monoBold, color: colors.warning, fontSize: 12 },
  netPrem: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 13, marginTop: 14, textAlign: "center" },

  greeks: { marginTop: 14 },
  greeksTitle: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 12, marginBottom: 8 },
  greeksGrid: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  greekCell: { flexBasis: "23%", flexGrow: 1, backgroundColor: colors.bg, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: colors.border },
  greekLabel: { fontFamily: fonts.bodySemi, color: colors.textSecondary, fontSize: 10 },
  greekValue: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 13, marginTop: 2 },
  greekHint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, marginTop: 2 },

  disclaimer: { fontFamily: fonts.body, color: colors.warning, fontSize: 11, marginHorizontal: 16, marginTop: 20, lineHeight: 17, textAlign: "center" },
  tradeRow: { marginHorizontal: 12, marginTop: 14 },
  tradeBtn: { paddingVertical: 16, borderRadius: 12, alignItems: "center" },
  tradeBtnText: { fontFamily: fonts.bodySemi, color: "#fff", fontSize: 15, letterSpacing: 1 },
  toast: { textAlign: "center", fontFamily: fonts.bodySemi, marginTop: 10, fontSize: 12 },
  chainHeader: { flexDirection: "row", paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border, marginTop: 8 },
  chainRow: { flexDirection: "row", paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  chainRowATM: { backgroundColor: colors.accent + "11" },
  chainCol: { flex: 1, fontFamily: fonts.mono, color: colors.textPrimary, fontSize: 11, textAlign: "center" },
  chainOI: { color: colors.textMuted },
  strikeCol: { fontFamily: fonts.bodySemi, color: colors.textPrimary, flex: 1.2 },
  chainHint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, marginTop: 10, textAlign: "center" },
  chainEmpty: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, lineHeight: 18, marginTop: 8 },
});
