import React, { useEffect, useState } from "react";
import {
  View, Text, StyleSheet, ScrollView, Modal, TextInput,
  TouchableOpacity, KeyboardAvoidingView, Platform, ActivityIndicator,
} from "react-native";
import { colors, fonts } from "@/src/theme";
import { api } from "@/src/api";
import { X, Plus, Check } from "lucide-react-native";

const POPULAR = [
  "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
  "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "HINDUNILVR.NS",
  "KOTAKBANK.NS", "ASIANPAINT.NS", "AXISBANK.NS", "MARUTI.NS", "M&M.NS",
  "WIPRO.NS", "BAJFINANCE.NS", "ADANIENT.NS", "TATASTEEL.NS", "SUNPHARMA.NS",
];

export function BotConfigEditor({
  visible, initial, onClose, onSaved,
}: {
  visible: boolean;
  initial: any;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [interval, setIntervalSec] = useState("300");
  const [maxValue, setMaxValue] = useState("50000");
  const [maxTrades, setMaxTrades] = useState("10");
  const [stopLoss, setStopLoss] = useState("2");
  const [takeProfit, setTakeProfit] = useState("4");
  const [minBuy, setMinBuy] = useState("3");
  const [minSell, setMinSell] = useState("3");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!initial || !visible) return;
    setIntervalSec(String(initial.interval_seconds ?? 300));
    setMaxValue(String(initial.max_position_size ?? 50000));
    setMaxTrades(String(initial.max_trades_per_day ?? 10));
    setStopLoss(String(initial.stop_loss_pct ?? 2));
    setTakeProfit(String(initial.take_profit_pct ?? 4));
    setMinBuy(String(initial.min_buy_signals ?? 3));
    setMinSell(String(initial.min_sell_signals ?? 3));
    setSymbols(initial.symbols || []);
  }, [initial, visible]);

  const toggleSymbol = (sym: string) => {
    setSymbols((prev) => prev.includes(sym) ? prev.filter((s) => s !== sym) : [...prev, sym]);
  };

  const save = async () => {
    if (symbols.length === 0) return;
    setSaving(true);
    try {
      await api.botSetConfig({
        interval_seconds: Math.max(30, parseInt(interval || "300", 10)),
        max_position_size: Math.max(100, parseFloat(maxValue || "50000")),
        max_trades_per_day: Math.max(1, parseInt(maxTrades || "10", 10)),
        stop_loss_pct: Math.max(0.5, parseFloat(stopLoss || "2")),
        take_profit_pct: Math.max(0.5, parseFloat(takeProfit || "4")),
        min_buy_signals: Math.max(1, Math.min(5, parseInt(minBuy || "3", 10))),
        min_sell_signals: Math.max(1, Math.min(5, parseInt(minSell || "3", 10))),
        symbols,
      });
      onSaved();
      onClose();
    } catch (e: any) {
      console.warn("save config", e);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="formSheet" onRequestClose={onClose}>
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modal}>
        <View style={styles.header}>
          <TouchableOpacity testID="close-config" onPress={onClose} style={styles.iconBtn}>
            <X color={colors.textPrimary} size={22} />
          </TouchableOpacity>
          <Text style={styles.title}>Edit Bot Config</Text>
          <TouchableOpacity testID="save-config" onPress={save} disabled={saving || symbols.length === 0} style={[styles.saveBtn, (saving || symbols.length === 0) && { opacity: 0.5 }]}>
            {saving ? <ActivityIndicator color="#fff" size="small" /> : <Check color="#fff" size={18} />}
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={{ paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.section}>SIGNAL THRESHOLDS</Text>
          <View style={styles.row2}>
            <Field label="Min BUY signals (of 5)" value={minBuy} onChange={setMinBuy} testID="min-buy" />
            <Field label="Min SELL signals (of 5)" value={minSell} onChange={setMinSell} testID="min-sell" />
          </View>

          <Text style={styles.section}>RISK MANAGEMENT</Text>
          <View style={styles.row2}>
            <Field label="Stop-loss %" value={stopLoss} onChange={setStopLoss} testID="stop-loss" suffix="%" />
            <Field label="Take-profit %" value={takeProfit} onChange={setTakeProfit} testID="take-profit" suffix="%" />
          </View>
          <View style={styles.row2}>
            <Field label="Max ₹ per trade" value={maxValue} onChange={setMaxValue} testID="max-value" prefix="₹" wide />
            <Field label="Max trades/day" value={maxTrades} onChange={setMaxTrades} testID="max-trades" />
          </View>

          <Text style={styles.section}>SCAN INTERVAL</Text>
          <Field label="Seconds between scans (min 30)" value={interval} onChange={setIntervalSec} testID="interval" suffix="s" />

          <Text style={styles.section}>WATCHED STOCKS ({symbols.length})</Text>
          {symbols.length === 0 && <Text style={styles.warn}>Pick at least 1 stock</Text>}
          <View style={styles.symbolGrid}>
            {POPULAR.map((s) => {
              const active = symbols.includes(s);
              const short = s.replace(".NS", "");
              return (
                <TouchableOpacity
                  key={s}
                  testID={`sym-${short}`}
                  onPress={() => toggleSymbol(s)}
                  style={[styles.symChip, active && styles.symChipActive]}
                  activeOpacity={0.7}
                >
                  {active && <Check color={colors.accent} size={12} />}
                  <Text style={[styles.symText, active && styles.symTextActive]}>{short}</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function Field({
  label, value, onChange, testID, prefix, suffix, wide,
}: {
  label: string; value: string; onChange: (v: string) => void;
  testID?: string; prefix?: string; suffix?: string; wide?: boolean;
}) {
  return (
    <View style={[styles.field, wide && { flex: 2 }]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.fieldBox}>
        {!!prefix && <Text style={styles.fieldFix}>{prefix}</Text>}
        <TextInput
          testID={testID}
          value={value}
          onChangeText={onChange}
          keyboardType="decimal-pad"
          style={styles.fieldInput}
          placeholderTextColor={colors.textMuted}
        />
        {!!suffix && <Text style={styles.fieldFix}>{suffix}</Text>}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  modal: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", padding: 12, borderBottomWidth: 1, borderBottomColor: colors.border },
  iconBtn: { padding: 8 },
  title: { flex: 1, textAlign: "center", fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 16 },
  saveBtn: { padding: 8, backgroundColor: colors.accent, borderRadius: 8 },
  section: { fontFamily: fonts.bodySemi, color: colors.textMuted, fontSize: 11, letterSpacing: 1.5, paddingHorizontal: 16, paddingTop: 18, paddingBottom: 8 },
  row2: { flexDirection: "row", paddingHorizontal: 12, gap: 8 },
  field: { flex: 1, marginVertical: 4, paddingHorizontal: 4 },
  fieldLabel: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 11, marginBottom: 4 },
  fieldBox: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: 10, paddingHorizontal: 12, borderWidth: 1, borderColor: colors.border },
  fieldInput: { flex: 1, color: colors.textPrimary, fontFamily: fonts.monoBold, fontSize: 16, paddingVertical: 12 },
  fieldFix: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 14, paddingHorizontal: 6 },
  warn: { fontFamily: fonts.body, color: colors.warning, fontSize: 12, paddingHorizontal: 16, marginBottom: 6 },
  symbolGrid: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: 12, gap: 8 },
  symChip: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  symChipActive: { borderColor: colors.accent, backgroundColor: colors.accent + "22" },
  symText: { fontFamily: fonts.bodyMed, color: colors.textSecondary, fontSize: 11 },
  symTextActive: { color: colors.accent },
});
