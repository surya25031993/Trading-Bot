import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Polyline, Line, Circle } from "react-native-svg";
import { colors, fonts } from "@/src/theme";

export type OptionCandle = { t: number; open: number; high: number; low: number; close: number; volume: number };

export function OptionPremiumChart({ candles, title, color = colors.profit }: { candles: OptionCandle[]; title: string; color?: string }) {
  if (!candles || candles.length < 2) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyText}>No premium data — market may be closed</Text>
      </View>
    );
  }
  const W = 320;
  const H = 130;
  const closes = candles.map((c) => c.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const dx = W / (candles.length - 1);
  const points = candles.map((c, i) => {
    const x = (i * dx).toFixed(1);
    const y = (H - ((c.close - min) / range) * (H - 14) - 7).toFixed(1);
    return `${x},${y}`;
  }).join(" ");

  const last = closes[closes.length - 1];
  const first = closes[0];
  const change = last - first;
  const changePct = (change / first) * 100;
  const positive = change >= 0;
  const lastTime = new Date(candles[candles.length - 1].t * 1000);

  return (
    <View>
      <View style={styles.header}>
        <Text style={styles.title}>{title}</Text>
        <Text style={[styles.change, { color: positive ? colors.profit : colors.loss }]}>
          ₹{last.toFixed(2)}  ({positive ? "+" : ""}{changePct.toFixed(2)}%)
        </Text>
      </View>
      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        <Line x1="0" y1={H / 2} x2={W} y2={H / 2} stroke={colors.border} strokeWidth="0.4" strokeDasharray="3,4" />
        <Polyline points={points} fill="none" stroke={positive ? colors.profit : colors.loss} strokeWidth="1.8" />
      </Svg>
      <View style={styles.axis}>
        <Text style={styles.axisText}>L ₹{min.toFixed(2)}</Text>
        <Text style={styles.axisText}>H ₹{max.toFixed(2)}</Text>
        <Text style={styles.axisText}>{lastTime.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { paddingVertical: 24, alignItems: "center" },
  emptyText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 6 },
  title: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 12 },
  change: { fontFamily: fonts.monoBold, fontSize: 12 },
  axis: { flexDirection: "row", justifyContent: "space-between", marginTop: 4 },
  axisText: { color: colors.textMuted, fontFamily: fonts.mono, fontSize: 9 },
});
