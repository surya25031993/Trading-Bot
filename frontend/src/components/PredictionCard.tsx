import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Line, Rect, Circle, Polygon, Polyline } from "react-native-svg";
import { colors, fonts } from "@/src/theme";
import { Prediction } from "@/src/api";
import { TrendingUp, TrendingDown, Minus, Sparkles, AlertTriangle, CheckCircle2 } from "lucide-react-native";

function colorFor(name: "profit" | "loss" | "warning" | "neutral"): string {
  switch (name) {
    case "profit": return colors.profit;
    case "loss": return colors.loss;
    case "warning": return colors.warning;
    default: return colors.neutral;
  }
}

export function PredictionCard({ data }: { data: Prediction }) {
  const dirColor = data.direction === "BULLISH" ? colors.profit : data.direction === "BEARISH" ? colors.loss : colors.warning;
  const DirIcon = data.direction === "BULLISH" ? TrendingUp : data.direction === "BEARISH" ? TrendingDown : Minus;
  const recColor = colorFor(data.recommendation_color);

  return (
    <View style={styles.container}>
      {/* Header with sparkle */}
      <View style={styles.header}>
        <View style={styles.titleRow}>
          <Sparkles color={colors.accent} size={14} />
          <Text style={styles.title}>ALGO PREDICTION</Text>
        </View>
        <View style={[styles.dirPill, { backgroundColor: dirColor + "22", borderColor: dirColor }]}>
          <DirIcon color={dirColor} size={12} />
          <Text style={[styles.dirPillText, { color: dirColor }]}>{data.direction}</Text>
        </View>
      </View>

      {/* Confidence meter */}
      <View style={styles.confRow}>
        <View style={styles.confLabelRow}>
          <Text style={styles.confLabel}>Confidence</Text>
          <Text style={[styles.confValue, { color: dirColor }]}>{data.confidence_pct}%</Text>
        </View>
        <View style={styles.confBarBg}>
          <View style={[styles.confBarFill, { width: `${data.confidence_pct}%`, backgroundColor: dirColor }]} />
        </View>
        <View style={styles.confSplits}>
          <Text style={[styles.confSplit, { color: colors.profit }]}>↑ {data.bull_count} BUY</Text>
          <Text style={[styles.confSplit, { color: colors.textMuted }]}>· {data.neutral_count} HOLD</Text>
          <Text style={[styles.confSplit, { color: colors.loss }]}>↓ {data.bear_count} SELL</Text>
          <Text style={[styles.confSplit, { color: colors.textMuted }]}>of 8 algos</Text>
        </View>
      </View>

      {/* Narrative */}
      <Text style={styles.narrative}>{data.narrative}</Text>

      {/* Forecast horizons */}
      <Text style={styles.sectionTitle}>FORECAST HORIZONS</Text>
      <View style={styles.horizonsGrid}>
        {data.predictions.map((p) => {
          const upPct = p.expected_change_pct;
          const isUp = upPct >= 0;
          const mvColor = isUp ? colors.profit : colors.loss;
          return (
            <View key={p.horizon} style={styles.horizonCard}>
              <Text style={styles.horizonLabel}>{p.horizon.toUpperCase()}</Text>
              <Text style={[styles.horizonTarget, { color: mvColor }]}>
                ₹{p.target.toLocaleString("en-IN", { maximumFractionDigits: 1 })}
              </Text>
              <Text style={[styles.horizonChange, { color: mvColor }]}>
                {isUp ? "+" : ""}{upPct.toFixed(2)}%
              </Text>
              <View style={styles.rangeRow}>
                <Text style={styles.rangeText}>₹{p.low.toFixed(0)}</Text>
                <Text style={styles.rangeText}>—</Text>
                <Text style={styles.rangeText}>₹{p.high.toFixed(0)}</Text>
              </View>
              <View style={styles.probRow}>
                <Text style={styles.probLabel}>P(UP)</Text>
                <Text style={[styles.probValue, { color: p.prob_up >= 55 ? colors.profit : p.prob_up <= 45 ? colors.loss : colors.warning }]}>
                  {p.prob_up.toFixed(0)}%
                </Text>
              </View>
            </View>
          );
        })}
      </View>

      {/* Forecast cone chart */}
      <ForecastCone data={data} />

      {/* Volatility info */}
      <View style={styles.volRow}>
        <View style={styles.volStat}>
          <Text style={styles.volLabel}>ATR</Text>
          <Text style={styles.volValue}>{data.atr_pct.toFixed(2)}%</Text>
        </View>
        <View style={styles.volStat}>
          <Text style={styles.volLabel}>VOLATILITY</Text>
          <Text style={styles.volValue}>{data.volatility_pct.toFixed(2)}%</Text>
        </View>
        <View style={styles.volStat}>
          <Text style={styles.volLabel}>NET SCORE</Text>
          <Text style={[styles.volValue, { color: data.net_score > 0 ? colors.profit : data.net_score < 0 ? colors.loss : colors.warning }]}>
            {data.net_score > 0 ? "+" : ""}{data.net_score}
          </Text>
        </View>
      </View>

      {/* Drivers */}
      {data.key_drivers.length > 0 && (
        <View style={styles.driverSection}>
          <View style={styles.driverHeader}>
            <CheckCircle2 color={colors.profit} size={12} />
            <Text style={[styles.driverHeaderText, { color: colors.profit }]}>KEY DRIVERS</Text>
          </View>
          {data.key_drivers.map((d, i) => (
            <View key={i} style={styles.driverRow}>
              <Text style={styles.driverName}>{d.name}</Text>
              <Text style={styles.driverReason}>{d.reason}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Risks */}
      {data.risk_factors.length > 0 && (
        <View style={styles.driverSection}>
          <View style={styles.driverHeader}>
            <AlertTriangle color={colors.loss} size={12} />
            <Text style={[styles.driverHeaderText, { color: colors.loss }]}>RISK FACTORS</Text>
          </View>
          {data.risk_factors.map((d, i) => (
            <View key={i} style={styles.driverRow}>
              <Text style={styles.driverName}>{d.name}</Text>
              <Text style={styles.driverReason}>{d.reason}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Recommendation */}
      <View style={[styles.recBox, { backgroundColor: recColor + "1A", borderColor: recColor }]}>
        <Text style={[styles.recLabel, { color: recColor }]}>RECOMMENDATION</Text>
        <Text style={[styles.recAction, { color: recColor }]}>{data.recommendation}</Text>
      </View>

      <Text style={styles.disclaimer}>
        ⚠ Predictions are probabilistic estimates based on 8 quant algorithms + historical volatility. Not investment advice.
      </Text>
    </View>
  );
}

function ForecastCone({ data }: { data: Prediction }) {
  // Visualize current price + 3 forecast targets with low/high bands
  const W = 320, H = 110;
  const spot = data.current_price;
  const points = [{ x: 0, low: spot, target: spot, high: spot, days: 0 }];
  data.predictions.forEach((p, idx) => {
    points.push({ x: idx + 1, low: p.low, target: p.target, high: p.high, days: p.days });
  });

  const allVals = points.flatMap(p => [p.low, p.target, p.high]);
  const minV = Math.min(...allVals);
  const maxV = Math.max(...allVals);
  const range = (maxV - minV) || 1;
  const padding = range * 0.1;
  const yMin = minV - padding;
  const yMax = maxV + padding;
  const yRange = yMax - yMin;
  const N = points.length;
  const dx = W / (N - 1);
  const yOf = (v: number) => H - ((v - yMin) / yRange) * (H - 16) - 8;

  // Cone path (low band → high band reversed)
  const topPts = points.map((p, i) => `${i * dx},${yOf(p.high)}`).join(" ");
  const botPts = points.slice().reverse().map((p, i) => `${(N - 1 - i) * dx},${yOf(p.low)}`).join(" ");
  const conePath = `${topPts} ${botPts}`;
  const targetPts = points.map((p, i) => `${i * dx},${yOf(p.target)}`).join(" ");
  const dirColor = data.direction === "BULLISH" ? colors.profit : data.direction === "BEARISH" ? colors.loss : colors.warning;

  return (
    <View style={styles.coneWrap}>
      <Text style={styles.coneTitle}>Forecast Cone (1σ band)</Text>
      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {/* Spot reference line */}
        <Line x1={0} y1={yOf(spot)} x2={W} y2={yOf(spot)} stroke={colors.border} strokeWidth="0.6" strokeDasharray="3,3" />
        {/* 1-sigma confidence cone */}
        <Polygon points={conePath} fill={dirColor + "22"} stroke="none" />
        {/* Target trajectory */}
        <Polyline points={targetPts} fill="none" stroke={dirColor} strokeWidth="1.8" />
        {/* Dots */}
        {points.map((p, i) => (
          <Circle key={`c${i}`} cx={i * dx} cy={yOf(p.target)} r="2.8" fill={dirColor} />
        ))}
      </Svg>
      <View style={styles.coneAxis}>
        <Text style={styles.coneAxisText}>Now</Text>
        {data.predictions.map((p, i) => (
          <Text key={i} style={styles.coneAxisText}>{p.horizon}</Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginHorizontal: 12, marginTop: 12, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  title: { fontFamily: fonts.bodySemi, color: colors.accent, fontSize: 11, letterSpacing: 2 },
  dirPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 9, paddingVertical: 4, borderRadius: 8, borderWidth: 1 },
  dirPillText: { fontFamily: fonts.bodySemi, fontSize: 11, letterSpacing: 1 },

  confRow: { marginTop: 16 },
  confLabelRow: { flexDirection: "row", justifyContent: "space-between" },
  confLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11 },
  confValue: { fontFamily: fonts.monoBold, fontSize: 16 },
  confBarBg: { height: 6, backgroundColor: colors.bg, borderRadius: 3, marginTop: 6, overflow: "hidden" },
  confBarFill: { height: 6, borderRadius: 3 },
  confSplits: { flexDirection: "row", marginTop: 8, gap: 8, flexWrap: "wrap" },
  confSplit: { fontFamily: fonts.bodyMed, fontSize: 10 },

  narrative: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 12, lineHeight: 18, marginTop: 14, fontStyle: "italic" },

  sectionTitle: { fontFamily: fonts.bodySemi, color: colors.textMuted, fontSize: 10, letterSpacing: 1.5, marginTop: 18, marginBottom: 8 },
  horizonsGrid: { flexDirection: "row", gap: 8 },
  horizonCard: { flex: 1, backgroundColor: colors.bg, borderRadius: 10, padding: 10, borderWidth: 1, borderColor: colors.border },
  horizonLabel: { fontFamily: fonts.bodySemi, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  horizonTarget: { fontFamily: fonts.monoBold, fontSize: 15, marginTop: 4 },
  horizonChange: { fontFamily: fonts.mono, fontSize: 11, marginTop: 2 },
  rangeRow: { flexDirection: "row", gap: 3, marginTop: 6, alignItems: "center" },
  rangeText: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 9 },
  probRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 6, alignItems: "center" },
  probLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9 },
  probValue: { fontFamily: fonts.bodySemi, fontSize: 11 },

  coneWrap: { marginTop: 14 },
  coneTitle: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 10, marginBottom: 6, letterSpacing: 0.5 },
  coneAxis: { flexDirection: "row", justifyContent: "space-between", marginTop: 4 },
  coneAxisText: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9 },

  volRow: { flexDirection: "row", gap: 8, marginTop: 14 },
  volStat: { flex: 1, backgroundColor: colors.bg, borderRadius: 8, padding: 8, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  volLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1 },
  volValue: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 13, marginTop: 3 },

  driverSection: { marginTop: 16 },
  driverHeader: { flexDirection: "row", alignItems: "center", gap: 5, marginBottom: 6 },
  driverHeaderText: { fontFamily: fonts.bodySemi, fontSize: 10, letterSpacing: 1.5 },
  driverRow: { flexDirection: "row", paddingVertical: 5, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  driverName: { fontFamily: fonts.bodyMed, color: colors.textPrimary, fontSize: 11, flex: 0.45 },
  driverReason: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 11, flex: 0.55 },

  recBox: { marginTop: 18, paddingVertical: 12, paddingHorizontal: 14, borderRadius: 10, borderWidth: 1, alignItems: "center" },
  recLabel: { fontFamily: fonts.bodySemi, fontSize: 10, letterSpacing: 1.5 },
  recAction: { fontFamily: fonts.headingSemi, fontSize: 16, marginTop: 4, letterSpacing: 0.5 },

  disclaimer: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, marginTop: 12, textAlign: "center", lineHeight: 14, fontStyle: "italic" },
});
