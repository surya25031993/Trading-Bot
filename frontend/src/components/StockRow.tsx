import React from "react";
import { Text, View, StyleSheet, TouchableOpacity } from "react-native";
import { useRouter } from "expo-router";
import { colors, fonts } from "@/src/theme";
import { ChevronRight } from "lucide-react-native";

type Props = {
  symbol: string;
  name?: string;
  price: number;
  change?: number;
  change_pct?: number;
  testID?: string;
  showArrow?: boolean;
};

export function StockRow({ symbol, name, price, change = 0, change_pct = 0, testID, showArrow = true }: Props) {
  const router = useRouter();
  const positive = change_pct >= 0;
  const color = positive ? colors.profit : colors.loss;
  const cleanSym = symbol.replace(".NS", "").replace(".BO", "").replace("^", "");
  return (
    <TouchableOpacity
      testID={testID || `stock-row-${cleanSym}`}
      onPress={() => router.push({ pathname: "/stock/[symbol]", params: { symbol, name: name || cleanSym } })}
      style={styles.row}
      activeOpacity={0.7}
    >
      <View style={styles.left}>
        <Text style={styles.symbol} numberOfLines={1}>{cleanSym}</Text>
        {!!name && <Text style={styles.name} numberOfLines={1}>{name}</Text>}
      </View>
      <View style={styles.right}>
        <Text style={styles.price}>₹{price.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
        <View style={styles.changeWrap}>
          <Text style={[styles.change, { color }]}>
            {positive ? "+" : ""}{change.toFixed(2)} ({positive ? "+" : ""}{change_pct.toFixed(2)}%)
          </Text>
        </View>
      </View>
      {showArrow && <ChevronRight color={colors.textMuted} size={18} style={{ marginLeft: 6 }} />}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 14,
    paddingHorizontal: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  left: { flex: 1, paddingRight: 12 },
  right: { alignItems: "flex-end" },
  symbol: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 15 },
  name: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 2 },
  price: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 15 },
  changeWrap: { marginTop: 2 },
  change: { fontFamily: fonts.mono, fontSize: 12 },
});
