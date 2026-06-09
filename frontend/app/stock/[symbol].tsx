import React, { useCallback, useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, TouchableOpacity,
  Modal, TextInput, KeyboardAvoidingView, Platform,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { api, IndicatorData, Quote, Prediction, IntradayForecast, MLPrediction } from "@/src/api";
import { colors, fonts, API } from "@/src/theme";
import { LineChart } from "@/src/components/LineChart";
import { AdvancedChart, ChartData } from "@/src/components/AdvancedChart";
import { PredictionCard } from "@/src/components/PredictionCard";
import { IntradayPredictionCard } from "@/src/components/IntradayPredictionCard";
import { MLPredictionCard } from "@/src/components/MLPredictionCard";
import { ArrowLeft, Sparkles, Star } from "lucide-react-native";

type TradeSide = "BUY" | "SELL";

export default function StockDetail() {
  const params = useLocalSearchParams<{ symbol: string; name?: string }>();
  const symbol = String(params.symbol || "");
  const name = String(params.name || symbol.replace(".NS", ""));
  const router = useRouter();

  const [quote, setQuote] = useState<Quote | null>(null);
  const [chart, setChart] = useState<{ close: number }[]>([]);
  const [advChart, setAdvChart] = useState<ChartData | null>(null);
  const [ind, setInd] = useState<IndicatorData | null>(null);
  const [pred, setPred] = useState<Prediction | null>(null);
  const [intra, setIntra] = useState<IntradayForecast | null>(null);
  const [mlPred, setMlPred] = useState<MLPrediction | null>(null);
  const [loading, setLoading] = useState(true);

  const [aiText, setAiText] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const [tradeModal, setTradeModal] = useState<TradeSide | null>(null);
  const [qty, setQty] = useState("1");
  const [tradeMsg, setTradeMsg] = useState<string | null>(null);
  const [tradeBusy, setTradeBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, s, c, p, intraData, mlData] = await Promise.all([
        api.stockDetail(symbol),
        api.stockSignals(symbol).catch(() => null),
        api.stockChart(symbol).catch(() => null),
        api.stockPredict(symbol).catch(() => null),
        api.stockIntradayForecast(symbol).catch(() => null),
        api.stockMLPredict(symbol).catch(() => null),
      ]);
      setQuote(d.quote);
      setChart(d.chart.map((c) => ({ close: c.close })));
      if (s) setInd(s);
      if (c) setAdvChart(c);
      if (p) setPred(p);
      if (intraData) setIntra(intraData);
      if (mlData) setMlPred(mlData);
    } catch (e) {
      console.warn(e);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  useEffect(() => { load(); }, [load]);

  const runAI = async () => {
    setAiLoading(true);
    setAiText("");
    try {
      const res = await fetch(api.aiAnalyzeUrl(symbol), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol }),
      });
      if (!res.body) {
        const t = await res.text();
        setAiText(t);
      } else {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let acc = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          acc += decoder.decode(value, { stream: true });
          setAiText(acc);
        }
      }
    } catch (e: any) {
      setAiText(`Error: ${e.message}`);
    } finally {
      setAiLoading(false);
    }
  };

  const addToWatchlist = async () => {
    try {
      await api.addWatch(symbol, name);
      setTradeMsg("Added to watchlist");
      setTimeout(() => setTradeMsg(null), 1800);
    } catch {}
  };

  const placeTrade = async () => {
    if (!quote || !tradeModal) return;
    const q = parseInt(qty, 10);
    if (isNaN(q) || q <= 0) { setTradeMsg("Enter valid quantity"); return; }
    setTradeBusy(true);
    try {
      const res = await api.paperTrade({ symbol, name, side: tradeModal, quantity: q, price: quote.price });
      setTradeMsg(`${tradeModal} ${q} @ ₹${quote.price.toFixed(2)} placed!`);
      setTradeModal(null);
      setQty("1");
      setTimeout(() => setTradeMsg(null), 2500);
    } catch (e: any) {
      setTradeMsg(e.message || "Trade failed");
    } finally {
      setTradeBusy(false);
    }
  };

  if (loading || !quote) {
    return (
      <SafeAreaView style={styles.container}>
        <ActivityIndicator color={colors.accent} style={{ marginTop: 80 }} />
      </SafeAreaView>
    );
  }

  const positive = quote.change_pct >= 0;
  const cleanSym = symbol.replace(".NS", "");

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity testID="back-btn" onPress={() => router.back()} style={styles.iconBtn}>
          <ArrowLeft color={colors.textPrimary} size={22} />
        </TouchableOpacity>
        <View style={{ flex: 1, marginLeft: 8 }}>
          <Text style={styles.headerSym}>{cleanSym}</Text>
          <Text style={styles.headerName} numberOfLines={1}>{name}</Text>
        </View>
        <TouchableOpacity testID="add-watchlist" onPress={addToWatchlist} style={styles.iconBtn}>
          <Star color={colors.accent} size={20} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 200 }}>
        <View style={styles.priceBlock}>
          <Text style={styles.price}>₹{quote.price.toFixed(2)}</Text>
          <Text style={[styles.change, { color: positive ? colors.profit : colors.loss }]}>
            {positive ? "+" : ""}{quote.change.toFixed(2)}  ({positive ? "+" : ""}{quote.change_pct.toFixed(2)}%)
          </Text>
          <View style={styles.miniStats}>
            <Text style={styles.miniStat}>H ₹{quote.day_high.toFixed(2)}</Text>
            <Text style={styles.miniStat}>L ₹{quote.day_low.toFixed(2)}</Text>
            <Text style={styles.miniStat}>Vol {(quote.volume / 1000).toFixed(0)}K</Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Technical Charts · All Indicators</Text>
          {advChart ? <AdvancedChart data={advChart} /> : <LineChart data={chart} color={positive ? colors.profit : colors.loss} />}
        </View>

        {/* === ALGO PREDICTION SECTION === */}
        {pred && <PredictionCard data={pred} />}

        {/* === INTRADAY 5/10/15/30-min FORECAST + BACKTEST === */}
        {intra && <IntradayPredictionCard data={intra} symbol={symbol} onRefresh={setIntra} />}

        {/* === ML PREDICTION SECTION (Separate) === */}
        <View style={[styles.card, { borderColor: colors.accent, borderWidth: 2 }]}>
          <Text style={[styles.cardTitle, { color: colors.accent }]}>🤖 ML PREDICTION (V2 - 98% Accuracy)</Text>
          {mlPred ? (
            <MLPredictionCard data={mlPred} symbol={symbol} onRefresh={setMlPred} />
          ) : (
            <Text style={{ color: colors.textMuted, padding: 20, textAlign: 'center' }}>Loading ML Prediction...</Text>
          )}
        </View>

        {ind && (
          <View style={styles.card}>
            <View style={styles.row}>
              <Text style={styles.cardTitle}>Algo Signals</Text>
              <View style={[styles.consensus, { backgroundColor: consensusColor(ind.consensus) + "22", borderColor: consensusColor(ind.consensus) }]}>
                <Text style={[styles.consensusText, { color: consensusColor(ind.consensus) }]}>
                  {ind.consensus} ({ind.buy_count}B / {ind.sell_count}S / {ind.hold_count}H)
                </Text>
              </View>
            </View>
            {ind.signals.map((s, i) => (
              <View key={i} style={styles.sigRow} testID={`signal-${s.name}`}>
                <View style={[styles.tag, { backgroundColor: consensusColor(s.action) + "22", borderColor: consensusColor(s.action) }]}>
                  <Text style={[styles.tagText, { color: consensusColor(s.action) }]}>{s.action}</Text>
                </View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.sigName}>{s.name}</Text>
                  <Text style={styles.sigReason}>{s.reason}</Text>
                </View>
              </View>
            ))}
            <View style={styles.indGrid}>
              <Indicator label="RSI(14)" value={ind.indicators.rsi.toFixed(1)} />
              <Indicator label="MACD" value={ind.indicators.macd.toFixed(2)} />
              <Indicator label="SMA20" value={`₹${ind.indicators.sma20.toFixed(0)}`} />
              <Indicator label="SMA50" value={`₹${ind.indicators.sma50.toFixed(0)}`} />
              <Indicator label="BB Low" value={`₹${ind.indicators.bb_lower.toFixed(0)}`} />
              <Indicator label="BB High" value={`₹${ind.indicators.bb_upper.toFixed(0)}`} />
              {ind.indicators.supertrend !== undefined && (
                <Indicator
                  label={`SUPERTREND ${ind.indicators.supertrend_uptrend ? "↑" : "↓"}`}
                  value={`₹${ind.indicators.supertrend.toFixed(0)}`}
                />
              )}
              {ind.indicators.adx !== undefined && (
                <Indicator label="ADX(14)" value={ind.indicators.adx.toFixed(1)} />
              )}
              {ind.indicators.stoch_k !== undefined && (
                <Indicator label="STOCH %K" value={ind.indicators.stoch_k.toFixed(1)} />
              )}
            </View>
          </View>
        )}

        <View style={styles.card}>
          <View style={styles.row}>
            <Text style={styles.cardTitle}>AI Analysis</Text>
            <TouchableOpacity testID="run-ai" onPress={runAI} disabled={aiLoading} style={styles.aiBtn}>
              <Sparkles color={colors.accent} size={14} />
              <Text style={styles.aiBtnText}>{aiLoading ? "Analyzing…" : "Run"}</Text>
            </TouchableOpacity>
          </View>
          {aiLoading && !aiText && <ActivityIndicator color={colors.accent} style={{ marginTop: 12 }} />}
          {aiText ? (
            <Text style={styles.aiText} testID="ai-output">{aiText}</Text>
          ) : (
            !aiLoading && <Text style={styles.aiHint}>Tap Run to get Claude's technical view on this stock.</Text>
          )}
        </View>

        {tradeMsg && <Text style={styles.toast} testID="trade-toast">{tradeMsg}</Text>}
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity testID="sell-btn" onPress={() => setTradeModal("SELL")} style={[styles.actionBtn, { backgroundColor: colors.loss }]} activeOpacity={0.8}>
          <Text style={styles.actionText}>SELL</Text>
        </TouchableOpacity>
        <TouchableOpacity testID="buy-btn" onPress={() => setTradeModal("BUY")} style={[styles.actionBtn, { backgroundColor: colors.profit }]} activeOpacity={0.8}>
          <Text style={styles.actionText}>BUY</Text>
        </TouchableOpacity>
      </View>

      <Modal visible={tradeModal !== null} transparent animationType="slide" onRequestClose={() => setTradeModal(null)}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>{tradeModal} {cleanSym}</Text>
            <Text style={styles.modalSub}>at ₹{quote.price.toFixed(2)} per share</Text>
            <Text style={styles.label}>Quantity</Text>
            <TextInput
              testID="qty-input"
              value={qty}
              onChangeText={setQty}
              keyboardType="number-pad"
              style={styles.qtyInput}
              placeholderTextColor={colors.textMuted}
            />
            <Text style={styles.total}>Total: ₹{(parseFloat(qty || "0") * quote.price).toFixed(2)}</Text>
            <View style={styles.modalBtns}>
              <TouchableOpacity testID="cancel-trade" onPress={() => setTradeModal(null)} style={[styles.modalBtn, { backgroundColor: colors.surfaceElev }]}>
                <Text style={[styles.modalBtnText, { color: colors.textPrimary }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                testID="confirm-trade"
                onPress={placeTrade}
                disabled={tradeBusy}
                style={[styles.modalBtn, { backgroundColor: tradeModal === "BUY" ? colors.profit : colors.loss }]}
              >
                <Text style={styles.modalBtnText}>{tradeBusy ? "..." : `Confirm ${tradeModal}`}</Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

function consensusColor(c: "BUY" | "SELL" | "HOLD") {
  return c === "BUY" ? colors.profit : c === "SELL" ? colors.loss : colors.textMuted;
}

function Indicator({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.indCell}>
      <Text style={styles.indLabel}>{label}</Text>
      <Text style={styles.indValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingVertical: 8 },
  iconBtn: { padding: 8 },
  headerSym: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 16 },
  headerName: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11 },
  priceBlock: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 20 },
  price: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 32 },
  change: { fontFamily: fonts.mono, fontSize: 14, marginTop: 6 },
  miniStats: { flexDirection: "row", gap: 16, marginTop: 12 },
  miniStat: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 11 },
  card: { marginHorizontal: 12, marginTop: 12, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 },
  cardTitle: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 15 },
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  consensus: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8, borderWidth: 1 },
  consensusText: { fontFamily: fonts.bodySemi, fontSize: 11 },
  sigRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  tag: { paddingHorizontal: 8, paddingVertical: 5, borderRadius: 6, borderWidth: 1, minWidth: 50, alignItems: "center" },
  tagText: { fontFamily: fonts.bodySemi, fontSize: 10 },
  sigName: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 13 },
  sigReason: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11, marginTop: 2 },
  indGrid: { flexDirection: "row", flexWrap: "wrap", marginTop: 10, gap: 8 },
  indCell: { flexBasis: "31%", flexGrow: 1, backgroundColor: colors.bg, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.border },
  indLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, letterSpacing: 1 },
  indValue: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 13, marginTop: 4 },
  aiBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8, borderWidth: 1, borderColor: colors.accent },
  aiBtnText: { fontFamily: fonts.bodySemi, color: colors.accent, fontSize: 12 },
  aiText: { fontFamily: fonts.body, color: colors.textPrimary, fontSize: 13, lineHeight: 20, marginTop: 10 },
  aiHint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 10 },
  footer: { position: "absolute", bottom: 0, left: 0, right: 0, flexDirection: "row", padding: 12, gap: 10, backgroundColor: colors.bg, borderTopWidth: 1, borderTopColor: colors.border, paddingBottom: 24 },
  actionBtn: { flex: 1, paddingVertical: 14, borderRadius: 12, alignItems: "center" },
  actionText: { fontFamily: fonts.bodySemi, color: "#fff", fontSize: 15, letterSpacing: 1 },
  toast: { textAlign: "center", color: colors.accent, fontFamily: fonts.bodySemi, marginTop: 16 },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 20, paddingBottom: 32 },
  modalTitle: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 18 },
  modalSub: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 13, marginTop: 4 },
  label: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 11, letterSpacing: 1, marginTop: 18 },
  qtyInput: { backgroundColor: colors.bg, borderRadius: 10, padding: 14, color: colors.textPrimary, fontFamily: fonts.monoBold, fontSize: 20, marginTop: 8, borderWidth: 1, borderColor: colors.border },
  total: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 16, marginTop: 12 },
  modalBtns: { flexDirection: "row", gap: 10, marginTop: 18 },
  modalBtn: { flex: 1, paddingVertical: 14, borderRadius: 10, alignItems: "center" },
  modalBtnText: { fontFamily: fonts.bodySemi, color: "#fff", fontSize: 14 },
});
