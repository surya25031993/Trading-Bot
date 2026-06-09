import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Polyline, Line, Rect, Circle } from "react-native-svg";
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
  // Quant indicators (optional for backward compat)
  supertrend?: (number | null)[];
  supertrend_dir?: (number | null)[];  // 1 = uptrend (green), -1 = downtrend (red)
  adx?: (number | null)[];
  plus_di?: (number | null)[];
  minus_di?: (number | null)[];
  stoch_k?: (number | null)[];
  stoch_d?: (number | null)[];
};

const W = 360;

function toPoints(values: (number | null)[] | undefined, height: number, min: number, max: number): string {
  if (!values || values.length === 0) return "";
  const range = max - min || 1;
  const n = values.length;
  const dx = W / (n - 1);
  return values
    .map((v, i) => (v === null || isNaN(v as number) ? null : `${(i * dx).toFixed(1)},${(height - (((v as number) - min) / range) * (height - 10) - 5).toFixed(1)}`))
    .filter(Boolean)
    .join(" ");
}

function getMinMax(arrays: ((number | null)[] | undefined)[]): { min: number; max: number } {
  const vals: number[] = [];
  for (const arr of arrays) {
    if (!arr) continue;
    for (const v of arr) if (v !== null && !isNaN(v as number)) vals.push(v as number);
  }
  if (!vals.length) return { min: 0, max: 1 };
  return { min: Math.min(...vals), max: Math.max(...vals) };
}

export function AdvancedChart({ data }: { data: ChartData }) {
  if (!data || !data.close || data.close.length < 2) return null;

  // === PRICE PANEL (with Supertrend overlay split by direction) ===
  const { min: pMinRaw, max: pMaxRaw } = getMinMax([data.close, data.bb_upper, data.bb_lower, data.supertrend]);
  const pMin = pMinRaw * 0.99;
  const pMax = pMaxRaw * 1.01;
  const pH = 170;

  // Split supertrend into uptrend and downtrend segments so we can color them differently
  const stUp: (number | null)[] = [];
  const stDn: (number | null)[] = [];
  if (data.supertrend && data.supertrend_dir) {
    for (let i = 0; i < data.supertrend.length; i++) {
      const dir = data.supertrend_dir[i];
      const v = data.supertrend[i];
      if (dir === 1) { stUp.push(v); stDn.push(null); }
      else if (dir === -1) { stDn.push(v); stUp.push(null); }
      else { stUp.push(null); stDn.push(null); }
    }
  }

  // === ADX PANEL ===
  const adxH = 70;
  const hasAdx = !!data.adx && data.adx.some(v => v !== null);
  const { max: adxMaxRaw } = getMinMax([data.adx, data.plus_di, data.minus_di]);
  const adxMax = Math.max(60, Math.ceil(adxMaxRaw / 10) * 10);

  // === STOCHASTIC PANEL ===
  const stochH = 70;
  const hasStoch = !!data.stoch_k && data.stoch_k.some(v => v !== null);

  // === RSI PANEL ===
  const rsiH = 60;

  // === MACD HIST PANEL ===
  const macdValues = data.macd_hist.filter((v): v is number => v !== null);
  const mMax = Math.max(...macdValues.map(Math.abs)) || 1;
  const mH = 55;
  const dx = W / (data.close.length - 1);

  // Current trend tag for Supertrend
  const lastDir = data.supertrend_dir?.slice().reverse().find(d => d !== null) ?? 0;
  const stTrendLabel = lastDir === 1 ? "UPTREND" : lastDir === -1 ? "DOWNTREND" : "—";
  const stColor = lastDir === 1 ? colors.profit : lastDir === -1 ? colors.loss : colors.textMuted;

  return (
    <View>
      {/* Price chart with overlays */}
      <View style={styles.panelHeader}>
        <Text style={styles.panelTitle}>Price · SMA20 · SMA50 · Bollinger · Supertrend</Text>
        {data.supertrend && (
          <View style={[styles.trendPill, { backgroundColor: stColor + "22", borderColor: stColor }]}>
            <Text style={[styles.trendPillText, { color: stColor }]}>{stTrendLabel}</Text>
          </View>
        )}
      </View>
      <Svg width="100%" height={pH} viewBox={`0 0 ${W} ${pH}`} preserveAspectRatio="none">
        <Polyline points={toPoints(data.bb_upper, pH, pMin, pMax)} fill="none" stroke={colors.border} strokeWidth="0.7" strokeDasharray="2,3" />
        <Polyline points={toPoints(data.bb_lower, pH, pMin, pMax)} fill="none" stroke={colors.border} strokeWidth="0.7" strokeDasharray="2,3" />
        <Polyline points={toPoints(data.sma50, pH, pMin, pMax)} fill="none" stroke={colors.warning} strokeWidth="1.2" />
        <Polyline points={toPoints(data.sma20, pH, pMin, pMax)} fill="none" stroke={colors.neutral} strokeWidth="1.2" />
        {/* Supertrend overlay split by direction */}
        {data.supertrend && (
          <>
            <Polyline points={toPoints(stUp, pH, pMin, pMax)} fill="none" stroke={colors.profit} strokeWidth="1.6" strokeDasharray="3,2" />
            <Polyline points={toPoints(stDn, pH, pMin, pMax)} fill="none" stroke={colors.loss} strokeWidth="1.6" strokeDasharray="3,2" />
          </>
        )}
        <Polyline points={toPoints(data.close, pH, pMin, pMax)} fill="none" stroke={colors.textPrimary} strokeWidth="1.8" />
      </Svg>
      <View style={styles.axis}>
        <Text style={styles.axisText}>₹{pMin.toFixed(0)}</Text>
        <Text style={styles.axisText}>₹{pMax.toFixed(0)}</Text>
      </View>

      {/* RSI panel */}
      <Text style={styles.panelTitle}>RSI (14) · OS &lt; 30 · OB &gt; 70</Text>
      <Svg width="100%" height={rsiH} viewBox={`0 0 ${W} ${rsiH}`} preserveAspectRatio="none">
        <Line x1="0" y1={rsiH - ((70 / 100) * (rsiH - 10) + 5)} x2={W} y2={rsiH - ((70 / 100) * (rsiH - 10) + 5)} stroke={colors.loss + "66"} strokeWidth="0.5" strokeDasharray="2,3" />
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

      {/* ADX panel */}
      {hasAdx && (
        <>
          <Text style={styles.panelTitle}>ADX (14) · +DI (green) · -DI (red) · ADX (yellow) · Strong &gt; 25</Text>
          <Svg width="100%" height={adxH} viewBox={`0 0 ${W} ${adxH}`} preserveAspectRatio="none">
            {/* Trend strength reference at 25 */}
            <Line x1="0" y1={adxH - ((25 / adxMax) * (adxH - 10) + 5)} x2={W} y2={adxH - ((25 / adxMax) * (adxH - 10) + 5)} stroke={colors.warning + "66"} strokeWidth="0.5" strokeDasharray="2,3" />
            <Polyline points={toPoints(data.plus_di, adxH, 0, adxMax)} fill="none" stroke={colors.profit} strokeWidth="1.2" />
            <Polyline points={toPoints(data.minus_di, adxH, 0, adxMax)} fill="none" stroke={colors.loss} strokeWidth="1.2" />
            <Polyline points={toPoints(data.adx, adxH, 0, adxMax)} fill="none" stroke={colors.warning} strokeWidth="1.6" />
          </Svg>
          <View style={styles.axis}>
            <Text style={styles.axisText}>0</Text>
            <Text style={[styles.axisText, { color: colors.warning }]}>25</Text>
            <Text style={styles.axisText}>{adxMax}</Text>
          </View>
        </>
      )}

      {/* Stochastic panel */}
      {hasStoch && (
        <>
          <Text style={styles.panelTitle}>Stochastic (14,3) · %K (cyan) · %D (orange) · OS &lt; 20 · OB &gt; 80</Text>
          <Svg width="100%" height={stochH} viewBox={`0 0 ${W} ${stochH}`} preserveAspectRatio="none">
            <Line x1="0" y1={stochH - ((80 / 100) * (stochH - 10) + 5)} x2={W} y2={stochH - ((80 / 100) * (stochH - 10) + 5)} stroke={colors.loss + "66"} strokeWidth="0.5" strokeDasharray="2,3" />
            <Line x1="0" y1={stochH - ((20 / 100) * (stochH - 10) + 5)} x2={W} y2={stochH - ((20 / 100) * (stochH - 10) + 5)} stroke={colors.profit + "66"} strokeWidth="0.5" strokeDasharray="2,3" />
            <Polyline points={toPoints(data.stoch_k, stochH, 0, 100)} fill="none" stroke={colors.accent} strokeWidth="1.4" />
            <Polyline points={toPoints(data.stoch_d, stochH, 0, 100)} fill="none" stroke={colors.warning} strokeWidth="1.2" />
          </Svg>
          <View style={styles.axis}>
            <Text style={styles.axisText}>0</Text>
            <Text style={[styles.axisText, { color: colors.profit }]}>20</Text>
            <Text style={[styles.axisText, { color: colors.loss }]}>80</Text>
            <Text style={styles.axisText}>100</Text>
          </View>
        </>
      )}

      <View style={styles.legend}>
        <LegendDot color={colors.textPrimary} label="Close" />
        <LegendDot color={colors.neutral} label="SMA 20" />
        <LegendDot color={colors.warning} label="SMA 50" />
        <LegendDot color={colors.profit} label="ST↑ / +DI / %K" />
        <LegendDot color={colors.loss} label="ST↓ / -DI" />
        <LegendDot color={colors.accent} label="RSI / Stoch" />
      </View>
    </View>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={styles.legendText}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  panelHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 12, marginBottom: 4 },
  panelTitle: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 10, marginTop: 12, marginBottom: 4, letterSpacing: 0.5 },
  trendPill: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6, borderWidth: 1 },
  trendPillText: { fontFamily: fonts.bodySemi, fontSize: 9, letterSpacing: 1 },
  axis: { flexDirection: "row", justifyContent: "space-between", marginTop: 2 },
  axisText: { color: colors.textMuted, fontFamily: fonts.mono, fontSize: 9 },
  legend: { flexDirection: "row", gap: 10, marginTop: 10, flexWrap: "wrap", justifyContent: "center" },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  legendText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 9 },
});
