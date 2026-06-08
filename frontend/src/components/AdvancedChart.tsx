import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Polyline, Line, Rect } from "react-native-svg";
import { colors, fonts } from "@/src/theme";

export type ChartData = {
  dates: string[];
  close: (number | null)[];
  sma20: (number | null)[];
  sma50: (number | null)[];
  bb_upper: (number | null)[];
  bb_lower: (number | null)[];
  rsi: (number | null)[];
  macd_hist: (number | null)[];
};

const W = 360;

function toPoints(values: (number | null)[], height: number, min: number, max: number): string {
  const range = max - min || 1;
  const n = values.length;
  const dx = W / (n - 1);
  return values
    .map((v, i) => v === null || isNaN(v) ? null : `${(i * dx).toFixed(1)},${(height - ((v - min) / range) * (height - 10) - 5).toFixed(1)}`)
    .filter(Boolean)
    .join(" ");
}

export function AdvancedChart({ data }: { data: ChartData }) {
  if (!data || !data.close || data.close.length < 2) return null;
  // Price panel range — combine all overlays
  const allPrices = [
    ...data.close.filter((v): v is number => v !== null),
    ...data.bb_upper.filter((v): v is number => v !== null),
    ...data.bb_lower.filter((v): v is number => v !== null),
  ];
  const pMin = Math.min(...allPrices) * 0.99;
  const pMax = Math.max(...allPrices) * 1.01;
  const pH = 160;

  // RSI panel: fixed 0-100
  const rsiH = 60;

  // MACD histogram panel
  const macdValues = data.macd_hist.filter((v): v is number => v !== null);
  const mMax = Math.max(...macdValues.map(Math.abs)) || 1;
  const mH = 60;
  const dx = W / (data.close.length - 1);

  return (
    <View>
      {/* Price chart with overlays */}
      <Text style={styles.panelTitle}>Price · SMA 20 (blue) · SMA 50 (orange) · Bollinger (gray)</Text>
      <Svg width="100%" height={pH} viewBox={`0 0 ${W} ${pH}`} preserveAspectRatio="none">
        {/* Bollinger fill area */}
        <Polyline points={toPoints(data.bb_upper, pH, pMin, pMax)} fill="none" stroke={colors.border} strokeWidth="0.7" strokeDasharray="2,3" />
        <Polyline points={toPoints(data.bb_lower, pH, pMin, pMax)} fill="none" stroke={colors.border} strokeWidth="0.7" strokeDasharray="2,3" />
        <Polyline points={toPoints(data.sma50, pH, pMin, pMax)} fill="none" stroke={colors.warning} strokeWidth="1.2" />
        <Polyline points={toPoints(data.sma20, pH, pMin, pMax)} fill="none" stroke={colors.neutral} strokeWidth="1.2" />
        <Polyline points={toPoints(data.close, pH, pMin, pMax)} fill="none" stroke={colors.textPrimary} strokeWidth="1.8" />
      </Svg>
      <View style={styles.axis}>
        <Text style={styles.axisText}>₹{pMin.toFixed(0)}</Text>
        <Text style={styles.axisText}>₹{pMax.toFixed(0)}</Text>
      </View>

      {/* RSI panel */}
      <Text style={styles.panelTitle}>RSI (14) · Oversold &lt; 30 · Overbought &gt; 70</Text>
      <Svg width="100%" height={rsiH} viewBox={`0 0 ${W} ${rsiH}`} preserveAspectRatio="none">
        {/* Overbought line at 70 */}
        <Line x1="0" y1={rsiH - ((70 / 100) * (rsiH - 10) + 5)} x2={W} y2={rsiH - ((70 / 100) * (rsiH - 10) + 5)} stroke={colors.loss + "66"} strokeWidth="0.5" strokeDasharray="2,3" />
        {/* Oversold line at 30 */}
        <Line x1="0" y1={rsiH - ((30 / 100) * (rsiH - 10) + 5)} x2={W} y2={rsiH - ((30 / 100) * (rsiH - 10) + 5)} stroke={colors.profit + "66"} strokeWidth="0.5" strokeDasharray="2,3" />
        <Polyline points={toPoints(data.rsi, rsiH, 0, 100)} fill="none" stroke={colors.accent} strokeWidth="1.5" />
      </Svg>
      <View style={styles.axis}>
        <Text style={styles.axisText}>0</Text>
        <Text style={[styles.axisText, { color: colors.profit }]}>30</Text>
        <Text style={[styles.axisText, { color: colors.loss }]}>70</Text>
        <Text style={styles.axisText}>100</Text>
      </View>

      {/* MACD histogram */}
      <Text style={styles.panelTitle}>MACD Histogram · Momentum</Text>
      <Svg width="100%" height={mH} viewBox={`0 0 ${W} ${mH}`} preserveAspectRatio="none">
        <Line x1="0" y1={mH / 2} x2={W} y2={mH / 2} stroke={colors.border} strokeWidth="0.5" />
        {data.macd_hist.map((v, i) => {
          if (v === null) return null;
          const x = i * dx;
          const barH = Math.abs(v) / mMax * (mH / 2 - 2);
          const y = v >= 0 ? mH / 2 - barH : mH / 2;
          const color = v >= 0 ? colors.profit : colors.loss;
          return <Rect key={i} x={x - 1} y={y} width={Math.max(dx * 0.7, 1)} height={barH} fill={color} />;
        })}
      </Svg>
      <View style={styles.legend}>
        <View style={styles.legendItem}><View style={[styles.dot, { backgroundColor: colors.textPrimary }]} /><Text style={styles.legendText}>Close</Text></View>
        <View style={styles.legendItem}><View style={[styles.dot, { backgroundColor: colors.neutral }]} /><Text style={styles.legendText}>SMA 20</Text></View>
        <View style={styles.legendItem}><View style={[styles.dot, { backgroundColor: colors.warning }]} /><Text style={styles.legendText}>SMA 50</Text></View>
        <View style={styles.legendItem}><View style={[styles.dot, { backgroundColor: colors.accent }]} /><Text style={styles.legendText}>RSI</Text></View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  panelTitle: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 10, marginTop: 12, marginBottom: 4, letterSpacing: 0.5 },
  axis: { flexDirection: "row", justifyContent: "space-between", marginTop: 2 },
  axisText: { color: colors.textMuted, fontFamily: fonts.mono, fontSize: 9 },
  legend: { flexDirection: "row", gap: 12, marginTop: 8, flexWrap: "wrap", justifyContent: "center" },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  legendText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 10 },
});
