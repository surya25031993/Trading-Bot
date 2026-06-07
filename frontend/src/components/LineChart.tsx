import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Polyline, Line } from "react-native-svg";
import { colors, fonts } from "@/src/theme";

type Point = { close: number };

export function LineChart({ data, height = 180, color = colors.accent }: { data: Point[]; height?: number; color?: string }) {
  if (!data || data.length < 2) {
    return (
      <View style={[styles.empty, { height }]}>
        <Text style={styles.emptyText}>No chart data</Text>
      </View>
    );
  }
  const width = 320; // viewport, scales with preserveAspectRatio
  const closes = data.map((d) => d.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const range = max - min || 1;
  const stepX = width / (data.length - 1);
  const points = data
    .map((d, i) => {
      const x = i * stepX;
      const y = height - ((d.close - min) / range) * (height - 20) - 10;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  return (
    <View>
      <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <Line x1="0" y1={height / 2} x2={width} y2={height / 2} stroke={colors.border} strokeWidth="0.5" strokeDasharray="3,3" />
        <Polyline points={points} fill="none" stroke={color} strokeWidth="2" />
      </Svg>
      <View style={styles.axis}>
        <Text style={styles.axisText}>₹{min.toFixed(0)}</Text>
        <Text style={styles.axisText}>₹{max.toFixed(0)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { alignItems: "center", justifyContent: "center" },
  emptyText: { color: colors.textMuted, fontFamily: fonts.body },
  axis: { flexDirection: "row", justifyContent: "space-between", marginTop: 6 },
  axisText: { color: colors.textMuted, fontFamily: fonts.mono, fontSize: 10 },
});
