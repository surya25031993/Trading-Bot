import React from "react";
import { View, Text, StyleSheet } from "react-native";
import Svg, { Polyline, Line, Circle } from "react-native-svg";
import { colors, fonts } from "@/src/theme";

export function PayoffChart({
  payoff, spot, breakevens, height = 200,
}: {
  payoff: { spot: number; pnl: number }[];
  spot: number;
  breakevens: number[];
  height?: number;
}) {
  if (!payoff || payoff.length < 2) {
    return <View style={[styles.empty, { height }]}><Text style={styles.emptyText}>No data</Text></View>;
  }
  const width = 320;
  const xs = payoff.map((p) => p.spot);
  const ys = payoff.map((p) => p.pnl);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const padY = (maxY - minY) * 0.1 || 1;
  const yRange = (maxY + padY) - (minY - padY) || 1;
  const xRange = maxX - minX || 1;

  const toX = (x: number) => ((x - minX) / xRange) * width;
  const toY = (y: number) => height - (((y - (minY - padY)) / yRange) * (height - 10)) - 5;

  // Split path into profit (green) and loss (red) segments
  const points = payoff.map((p) => `${toX(p.spot).toFixed(1)},${toY(p.pnl).toFixed(1)}`).join(" ");
  const zeroY = toY(0);
  const spotX = toX(spot);

  return (
    <View>
      <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        {/* zero line */}
        <Line x1="0" y1={zeroY} x2={width} y2={zeroY} stroke={colors.border} strokeWidth="0.5" strokeDasharray="3,3" />
        {/* spot line */}
        <Line x1={spotX} y1="0" x2={spotX} y2={height} stroke={colors.accent} strokeWidth="0.8" strokeDasharray="2,4" />
        {/* breakevens */}
        {breakevens.map((b, i) => {
          const x = toX(b);
          return <Line key={i} x1={x} y1="0" x2={x} y2={height} stroke={colors.warning} strokeWidth="0.6" strokeDasharray="2,3" />;
        })}
        {/* payoff curve — color by sign */}
        <Polyline points={points} fill="none" stroke={colors.textPrimary} strokeWidth="1.8" />
        {/* spot dot */}
        <Circle cx={spotX} cy={zeroY} r="3" fill={colors.accent} />
      </Svg>
      <View style={styles.axis}>
        <Text style={styles.axisText}>₹{minX.toFixed(0)}</Text>
        <Text style={[styles.axisText, { color: colors.accent }]}>Spot ₹{spot.toFixed(0)}</Text>
        <Text style={styles.axisText}>₹{maxX.toFixed(0)}</Text>
      </View>
      <View style={styles.legend}>
        <View style={styles.legendItem}><View style={[styles.dot, { backgroundColor: colors.accent }]} /><Text style={styles.legendText}>Spot</Text></View>
        <View style={styles.legendItem}><View style={[styles.dot, { backgroundColor: colors.warning }]} /><Text style={styles.legendText}>Break-even</Text></View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  empty: { alignItems: "center", justifyContent: "center" },
  emptyText: { color: colors.textMuted, fontFamily: fonts.body },
  axis: { flexDirection: "row", justifyContent: "space-between", marginTop: 6 },
  axisText: { color: colors.textMuted, fontFamily: fonts.mono, fontSize: 10 },
  legend: { flexDirection: "row", gap: 16, marginTop: 6, justifyContent: "center" },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  dot: { width: 6, height: 6, borderRadius: 3 },
  legendText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 10 },
});
