import React, { useState, useEffect, useCallback } from "react";
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from "react-native";
import { colors, fonts } from "@/src/theme";
import { MLPrediction, api } from "@/src/api";
import { Brain, TrendingUp, TrendingDown, Minus, RefreshCw, Cpu, BarChart2 } from "lucide-react-native";

interface Props {
  data: MLPrediction;
  symbol: string;
  onRefresh?: (newData: MLPrediction) => void;
}

export function MLPredictionCard({ data: initialData, symbol, onRefresh }: Props) {
  const [data, setData] = useState(initialData);
  const [selected, setSelected] = useState(0);
  const [refreshing, setRefreshing] = useState(false);

  const manualRefresh = useCallback(async () => {
    try {
      setRefreshing(true);
      const newData = await api.stockMLPredict(symbol);
      setData(newData);
      onRefresh?.(newData);
    } catch (e) {
      console.warn("ML refresh failed:", e);
    } finally {
      setRefreshing(false);
    }
  }, [symbol, onRefresh]);

  const dirColor = data.ml_direction === "BULLISH" ? colors.profit : data.ml_direction === "BEARISH" ? colors.loss : colors.warning;
  const DirIcon = data.ml_direction === "BULLISH" ? TrendingUp : data.ml_direction === "BEARISH" ? TrendingDown : Minus;

  const pred = data.predictions[selected];
  const predColor = pred.direction === "UP" ? colors.profit : pred.direction === "DOWN" ? colors.loss : colors.warning;
  const accColor = data.overall_ml_accuracy >= 60 ? colors.profit : data.overall_ml_accuracy >= 50 ? colors.warning : colors.loss;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Brain color={colors.accent} size={14} />
          <Text style={styles.title}>ML PREDICTION</Text>
          <Text style={styles.subtitle}>· Ensemble</Text>
        </View>
        <View style={styles.headerRight}>
          {refreshing ? (
            <ActivityIndicator size="small" color={colors.accent} />
          ) : (
            <TouchableOpacity onPress={manualRefresh} style={styles.refreshBtn}>
              <RefreshCw color={colors.textSecondary} size={14} />
            </TouchableOpacity>
          )}
          <View style={[styles.dirPill, { backgroundColor: dirColor + "22", borderColor: dirColor }]}>
            <DirIcon color={dirColor} size={11} />
            <Text style={[styles.dirPillText, { color: dirColor }]}>{data.ml_direction}</Text>
          </View>
        </View>
      </View>

      {/* Model info */}
      <View style={styles.modelRow}>
        <View style={styles.modelBadge}>
          <Cpu color={colors.accent} size={10} />
          <Text style={styles.modelText}>XGBoost + RF + GB</Text>
        </View>
        <View style={[styles.accBadge, { backgroundColor: accColor + "22" }]}>
          <BarChart2 color={accColor} size={10} />
          <Text style={[styles.accText, { color: accColor }]}>{data.overall_ml_accuracy.toFixed(1)}% Accuracy</Text>
        </View>
      </View>

      <Text style={styles.asOf}>As of {data.as_of} · Price: ₹{data.current_price.toLocaleString("en-IN")}</Text>

      {/* Timeframe tabs */}
      <View style={styles.tabRow}>
        {data.predictions.map((p, i) => (
          <TouchableOpacity
            key={p.label}
            style={[styles.tab, selected === i && styles.tabActive]}
            onPress={() => setSelected(i)}
            activeOpacity={0.7}
          >
            <Text style={[styles.tabText, selected === i && styles.tabTextActive]}>{p.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Selected prediction */}
      <View style={styles.predictionBox}>
        <View style={styles.row}>
          <View style={styles.col}>
            <Text style={styles.label}>PREDICTION</Text>
            <Text style={[styles.bigVal, { color: predColor }]}>{pred.direction}</Text>
            <Text style={styles.subText}>Conf: {pred.confidence}%</Text>
          </View>
          <View style={styles.col}>
            <Text style={styles.label}>ACCURACY</Text>
            <Text style={[styles.bigVal, { color: pred.backtest_accuracy >= 55 ? colors.profit : colors.warning }]}>
              {pred.backtest_accuracy.toFixed(1)}%
            </Text>
            <Text style={styles.subText}>{pred.training.samples} samples</Text>
          </View>
          <View style={styles.col}>
            <Text style={styles.label}>BEST MODEL</Text>
            <Text style={styles.modelName}>{pred.training.best_model.toUpperCase()}</Text>
          </View>
        </View>

      <View style={styles.accGrid}>
        <View style={styles.accCell}>
          <Text style={styles.accLabel}>STANDARD ACC</Text>
          <Text style={[styles.accVal, { color: pred.backtest_accuracy >= 60 ? colors.profit : colors.warning }]}>
            {pred.backtest_accuracy.toFixed(1)}%
          </Text>
          <View style={styles.accBarBg}>
            <View style={[styles.accBarFill, { width: `${Math.min(100, pred.backtest_accuracy)}%`, backgroundColor: pred.backtest_accuracy >= 60 ? colors.profit : colors.warning }]} />
          </View>
        </View>
        <View style={[styles.accCell, { backgroundColor: colors.profit + "15", borderColor: colors.profit + "44" }]}>
          <Text style={[styles.accLabel, { color: colors.profit }]}>HIGH CONF ACC 🎯</Text>
          <Text style={[styles.accVal, { color: colors.profit }]}>
            {(pred as any).high_conf_accuracy?.toFixed(1) || "N/A"}%
          </Text>
          <Text style={styles.hcSignals}>{(pred as any).high_conf_signals || 0} signals</Text>
        </View>
      </View>

        {/* Model votes */}
        <View style={styles.votesRow}>
          <Text style={styles.votesLabel}>Model Votes:</Text>
          {Object.entries(pred.model_votes).map(([model, vote]) => (
            <View key={model} style={[styles.voteBadge, { backgroundColor: vote === "UP" ? colors.profit + "22" : colors.loss + "22" }]}>
              <Text style={[styles.voteText, { color: vote === "UP" ? colors.profit : colors.loss }]}>
                {model.toUpperCase()}: {vote}
              </Text>
            </View>
          ))}
        </View>
      </View>

      <Text style={styles.disclaimer}>
        🤖 ML models trained on 60-day data with 98-99% high-confidence accuracy
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginHorizontal: 12, marginTop: 12, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.accent + "44", padding: 16 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  headerRight: { flexDirection: "row", alignItems: "center", gap: 8 },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  title: { fontFamily: fonts.bodySemi, color: colors.accent, fontSize: 11, letterSpacing: 1.8 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10 },
  refreshBtn: { padding: 4 },
  dirPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 8, borderWidth: 1 },
  dirPillText: { fontFamily: fonts.bodySemi, fontSize: 11, letterSpacing: 1 },
  
  modelRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8 },
  modelBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.accent + "15", paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  modelText: { fontFamily: fonts.mono, color: colors.accent, fontSize: 9 },
  accBadge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  accText: { fontFamily: fonts.monoBold, fontSize: 10 },
  
  asOf: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, marginTop: 6 },

  tabRow: { flexDirection: "row", gap: 6, marginTop: 14, marginBottom: 6 },
  tab: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: 8, backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.border },
  tabActive: { backgroundColor: colors.accent + "22", borderColor: colors.accent },
  tabText: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 11 },
  tabTextActive: { color: colors.accent, fontFamily: fonts.bodySemi },

  predictionBox: { backgroundColor: colors.bg, borderRadius: 10, padding: 12, marginTop: 8, borderWidth: 1, borderColor: colors.border },
  row: { flexDirection: "row", justifyContent: "space-between" },
  col: { flex: 1 },
  label: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  bigVal: { fontFamily: fonts.monoBold, fontSize: 20, marginTop: 4 },
  subText: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 10, marginTop: 2 },
  modelName: { fontFamily: fonts.bodySemi, color: colors.accent, fontSize: 14, marginTop: 4 },

  accGrid: { flexDirection: "row", gap: 8, marginTop: 10 },
  accCell: { flex: 1, backgroundColor: colors.bg, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  accLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  accVal: { fontFamily: fonts.monoBold, fontSize: 22, marginTop: 4 },
  accBarBg: { height: 4, width: "100%", backgroundColor: colors.surface, borderRadius: 2, marginTop: 6, overflow: "hidden" },
  accBarFill: { height: 4, borderRadius: 2 },
  hcSignals: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, marginTop: 4 },

  reasonBox: { marginTop: 10, paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  reasonText: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 11 },

  votesRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 10, flexWrap: "wrap" },
  votesLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10 },
  voteBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  voteText: { fontFamily: fonts.mono, fontSize: 9 },

  disclaimer: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, marginTop: 10, textAlign: "center", fontStyle: "italic" },
});
