import React, { useState } from "react";
import { View, Text, StyleSheet, TouchableOpacity } from "react-native";
import { colors, fonts } from "@/src/theme";
import { IntradayForecast } from "@/src/api";
import { Activity, TrendingUp, TrendingDown, Minus, Target, History } from "lucide-react-native";

export function IntradayPredictionCard({ data }: { data: IntradayForecast }) {
  const [selected, setSelected] = useState(0); // index into data.predictions

  const dirColor = data.direction === "BULLISH" ? colors.profit : data.direction === "BEARISH" ? colors.loss : colors.warning;
  const DirIcon = data.direction === "BULLISH" ? TrendingUp : data.direction === "BEARISH" ? TrendingDown : Minus;

  const live = data.predictions[selected];
  const bt = data.backtest[selected];
  const moveColor = (live.expected_change_pct || 0) >= 0 ? colors.profit : colors.loss;

  // Accuracy color
  const accColor = bt.directional_accuracy_pct >= 55 ? colors.profit : bt.directional_accuracy_pct >= 45 ? colors.warning : colors.loss;
  const bandColor = bt.within_1sigma_band_pct >= 65 ? colors.profit : bt.within_1sigma_band_pct >= 50 ? colors.warning : colors.loss;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Activity color={colors.accent} size={14} />
          <Text style={styles.title}>INTRADAY FORECAST</Text>
          <Text style={styles.interval}>· 5-min candles</Text>
        </View>
        <View style={[styles.dirPill, { backgroundColor: dirColor + "22", borderColor: dirColor }]}>
          <DirIcon color={dirColor} size={11} />
          <Text style={[styles.dirPillText, { color: dirColor }]}>{data.direction}</Text>
        </View>
      </View>

      <Text style={styles.asOf}>As of {data.as_of} · {data.bull_count} BUY · {data.bear_count} SELL of 8 algos</Text>

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
            <Text style={styles.label}>TARGET</Text>
            <Text style={[styles.bigVal, { color: moveColor }]}>
              ₹{live.target.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            </Text>
            <Text style={[styles.changeText, { color: moveColor }]}>
              {live.expected_change_pct >= 0 ? "+" : ""}{live.expected_change_pct.toFixed(3)}%
            </Text>
          </View>
          <View style={styles.col}>
            <Text style={styles.label}>P(UP)</Text>
            <Text style={[styles.bigVal, { color: live.prob_up >= 55 ? colors.profit : live.prob_up <= 45 ? colors.loss : colors.warning }]}>
              {live.prob_up.toFixed(0)}%
            </Text>
            <Text style={styles.subText}>{live.predicted_direction}</Text>
          </View>
        </View>
        <View style={styles.rangeRow}>
          <Text style={styles.rangeLabel}>1σ RANGE</Text>
          <Text style={styles.rangeVal}>
            ₹{live.low.toLocaleString("en-IN", { maximumFractionDigits: 1 })}
            <Text style={styles.rangeDash}>  ←  →  </Text>
            ₹{live.high.toLocaleString("en-IN", { maximumFractionDigits: 1 })}
          </Text>
        </View>
      </View>

      {/* Backtest accuracy */}
      <View style={styles.backtestHeader}>
        <History color={colors.textSecondary} size={12} />
        <Text style={styles.backtestTitle}>BACKTEST · {bt.label} · {bt.samples} bars (~{data.backtest_window_days_approx} days)</Text>
      </View>

      <View style={styles.accGrid}>
        <View style={styles.accCell}>
          <Text style={styles.accLabel}>DIRECTION ACC</Text>
          <Text style={[styles.accVal, { color: accColor }]}>{bt.directional_accuracy_pct.toFixed(1)}%</Text>
          <View style={styles.accBarBg}>
            <View style={[styles.accBarFill, { width: `${Math.min(100, bt.directional_accuracy_pct)}%`, backgroundColor: accColor }]} />
          </View>
          <Text style={styles.accSub}>{bt.total_signals} signals</Text>
        </View>
        <View style={styles.accCell}>
          <Text style={styles.accLabel}>IN-RANGE HIT</Text>
          <Text style={[styles.accVal, { color: bandColor }]}>{bt.within_1sigma_band_pct.toFixed(1)}%</Text>
          <View style={styles.accBarBg}>
            <View style={[styles.accBarFill, { width: `${Math.min(100, bt.within_1sigma_band_pct)}%`, backgroundColor: bandColor }]} />
          </View>
          <Text style={styles.accSub}>1σ band</Text>
        </View>
      </View>

      <View style={styles.miniStatsRow}>
        <MiniStat label="LONG ACC" value={`${bt.long_accuracy_pct.toFixed(0)}%`} color={colors.profit} />
        <MiniStat label="SHORT ACC" value={`${bt.short_accuracy_pct.toFixed(0)}%`} color={colors.loss} />
        <MiniStat label="MAE" value={`${bt.mae_pct.toFixed(2)}%`} color={colors.textSecondary} />
        <MiniStat label="VOL 5m" value={`${data.volatility_5m_pct.toFixed(2)}%`} color={colors.warning} />
      </View>

      <View style={styles.overallBox}>
        <Target color={colors.accent} size={11} />
        <Text style={styles.overallText}>
          Overall ensemble accuracy: <Text style={[styles.overallPct, { color: accColor }]}>{data.overall_accuracy_pct.toFixed(1)}%</Text> across all horizons
        </Text>
      </View>

      <Text style={styles.disclaimer}>
        ⚠ Walk-forward backtest on out-of-sample 5-min candles. Past performance ≠ future returns.
      </Text>
    </View>
  );
}

function MiniStat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={styles.miniStat}>
      <Text style={styles.miniStatLabel}>{label}</Text>
      <Text style={[styles.miniStatVal, { color }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginHorizontal: 12, marginTop: 12, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  title: { fontFamily: fonts.bodySemi, color: colors.accent, fontSize: 11, letterSpacing: 1.8 },
  interval: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10 },
  dirPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 8, borderWidth: 1 },
  dirPillText: { fontFamily: fonts.bodySemi, fontSize: 11, letterSpacing: 1 },
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
  bigVal: { fontFamily: fonts.monoBold, fontSize: 22, marginTop: 4 },
  changeText: { fontFamily: fonts.mono, fontSize: 11, marginTop: 2 },
  subText: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 11, marginTop: 2 },
  rangeRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 10, paddingTop: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  rangeLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  rangeVal: { fontFamily: fonts.mono, color: colors.textSecondary, fontSize: 11 },
  rangeDash: { color: colors.textMuted, fontSize: 9 },

  backtestHeader: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 18, marginBottom: 8 },
  backtestTitle: { fontFamily: fonts.bodySemi, color: colors.textSecondary, fontSize: 10, letterSpacing: 1 },

  accGrid: { flexDirection: "row", gap: 8 },
  accCell: { flex: 1, backgroundColor: colors.bg, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: colors.border },
  accLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  accVal: { fontFamily: fonts.monoBold, fontSize: 20, marginTop: 4 },
  accBarBg: { height: 4, backgroundColor: colors.surface, borderRadius: 2, marginTop: 6, overflow: "hidden" },
  accBarFill: { height: 4, borderRadius: 2 },
  accSub: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, marginTop: 4 },

  miniStatsRow: { flexDirection: "row", gap: 6, marginTop: 10 },
  miniStat: { flex: 1, backgroundColor: colors.bg, padding: 7, borderRadius: 7, alignItems: "center", borderWidth: StyleSheet.hairlineWidth, borderColor: colors.border },
  miniStatLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 8, letterSpacing: 0.5 },
  miniStatVal: { fontFamily: fonts.monoBold, fontSize: 12, marginTop: 2 },

  overallBox: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 14, paddingVertical: 10, paddingHorizontal: 12, backgroundColor: colors.accent + "10", borderRadius: 8, borderWidth: 1, borderColor: colors.accent + "44" },
  overallText: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 11, flex: 1 },
  overallPct: { fontFamily: fonts.bodySemi },

  disclaimer: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, marginTop: 10, textAlign: "center", fontStyle: "italic" },
});
