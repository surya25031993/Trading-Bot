import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, TouchableOpacity, Alert } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api } from "@/src/api";
import { colors, fonts } from "@/src/theme";
import { Bot, Play, Square, Zap, AlertTriangle, Edit3, TrendingUp, TrendingDown, Minus, Trash2, Trophy, Target } from "lucide-react-native";
import { BotConfigEditor } from "@/src/components/BotConfigEditor";
import { ToastContainer, Toast } from "@/src/components/Toast";

export default function BotScreen() {
  const [status, setStatus] = useState<any>(null);
  const [decisions, setDecisions] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const lastTradeIdRef = React.useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, d, st] = await Promise.all([api.botStatus(), api.botDecisions(30), api.botStats()]);
      setStatus(s);
      setStats(st);
      // Detect new trade decisions (BUY/SELL with quantity) → toast
      const newTrades = d.filter((x: any) => (x.action === "BUY" || x.action === "SELL") && x.qty > 0);
      if (newTrades.length && lastTradeIdRef.current !== null) {
        const newest = newTrades[0];
        const newestKey = `${newest.timestamp}-${newest.symbol}`;
        if (lastTradeIdRef.current !== newestKey) {
          // Push toast for the new trade
          setToasts((prev) => [
            ...prev,
            { id: Date.now(), side: newest.action, symbol: newest.symbol, qty: newest.qty, price: newest.price },
          ]);
        }
        lastTradeIdRef.current = newestKey;
      } else if (newTrades.length && lastTradeIdRef.current === null) {
        lastTradeIdRef.current = `${newTrades[0].timestamp}-${newTrades[0].symbol}`;
      }
      setDecisions(d);
    } catch (e) {
      console.warn(e);
    } finally {
      setLoading(false);
    }
  }, []);

  const dismissToast = (id: number) => setToasts((prev) => prev.filter((t) => t.id !== id));

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000); // poll every 10s
    return () => clearInterval(interval);
  }, [load]);

  const start = (mode: "paper" | "live") => {
    if (mode === "live") {
      Alert.alert(
        "⚠ Live Mode",
        "Bot will place REAL orders on your Fyers account using real money. Make sure Fyers is connected first. Continue?",
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "Start Live Bot",
            style: "destructive",
            onPress: async () => {
              setBusy(true);
              try { await api.botStart("live"); await load(); }
              catch (e: any) { Alert.alert("Cannot start", e.message); }
              finally { setBusy(false); }
            },
          },
        ]
      );
      return;
    }
    (async () => {
      setBusy(true);
      try { await api.botStart("paper"); await load(); }
      catch (e: any) { Alert.alert("Error", e.message); }
      finally { setBusy(false); }
    })();
  };

  const stop = async () => {
    setBusy(true);
    try { await api.botStop(); await load(); }
    catch (e: any) { Alert.alert("Error", e.message); }
    finally { setBusy(false); }
  };

  if (loading || !status) {
    return (
      <SafeAreaView style={styles.container} edges={["top"]}>
        <ActivityIndicator color={colors.accent} style={{ marginTop: 80 }} />
      </SafeAreaView>
    );
  }

  const running = status.running;
  const statsRuntime = status.stats || {};
  const cfg = status.config || {};

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.title}>Auto-Trade Bot</Text>
        <Text style={styles.subtitle}>Automated paper / live trading on signals</Text>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 120 }}>
        {/* Big status card */}
        <View style={[styles.statusCard, { borderColor: running ? colors.profit : colors.border }]} testID="bot-status">
          <View style={styles.row}>
            <View style={[styles.iconBubble, { backgroundColor: (running ? colors.profit : colors.textMuted) + "22" }]}>
              <Bot color={running ? colors.profit : colors.textMuted} size={26} />
            </View>
            <View style={{ flex: 1, marginLeft: 14 }}>
              <Text style={styles.statusTitle}>{running ? "Bot Running" : "Bot Stopped"}</Text>
              <Text style={[styles.statusMode, { color: running ? colors.profit : colors.textMuted }]}>
                {running ? `${status.mode.toUpperCase()} mode • scanning every ${cfg.interval_seconds}s` : "Tap Start to begin"}
              </Text>
            </View>
          </View>

          {running ? (
            <TouchableOpacity testID="stop-bot" onPress={stop} disabled={busy} style={[styles.bigBtn, { backgroundColor: colors.loss }]} activeOpacity={0.8}>
              <Square color="#fff" size={18} />
              <Text style={styles.bigBtnText}>Stop Bot</Text>
            </TouchableOpacity>
          ) : (
            <View style={{ gap: 10, marginTop: 18 }}>
              <TouchableOpacity testID="start-paper" onPress={() => start("paper")} disabled={busy} style={[styles.bigBtn, { backgroundColor: colors.accent }]} activeOpacity={0.8}>
                <Play color="#fff" size={18} />
                <Text style={styles.bigBtnText}>Start in Paper Mode</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="start-live" onPress={() => start("live")} disabled={busy} style={[styles.bigBtn, { backgroundColor: colors.loss + "22", borderWidth: 1, borderColor: colors.loss }]} activeOpacity={0.8}>
                <Zap color={colors.loss} size={18} />
                <Text style={[styles.bigBtnText, { color: colors.loss }]}>Start in Live Mode (real orders)</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Stats */}
        <View style={styles.statsCard}>
          <Text style={styles.cardTitle}>Today's Activity</Text>
          <View style={styles.statsGrid}>
            <Stat label="Scans" value={statsRuntime.scans} />
            <Stat label="Buys" value={statsRuntime.buy_orders} color={colors.profit} />
            <Stat label="Sells" value={statsRuntime.sell_orders} color={colors.loss} />
            <Stat label="Errors" value={statsRuntime.errors} color={statsRuntime.errors ? colors.warning : colors.textMuted} />
          </View>
          {status.last_tick && (
            <Text style={styles.lastTick}>
              Last scan: {new Date(status.last_tick).toLocaleTimeString("en-IN")}
            </Text>
          )}
          {statsRuntime.last_error && (
            <View style={styles.errorBox}>
              <AlertTriangle color={colors.warning} size={14} />
              <Text style={styles.errorText}>{statsRuntime.last_error}</Text>
            </View>
          )}
        </View>

        {/* Stats Dashboard */}
        {stats && stats.completed_trades > 0 && (
          <View style={styles.statsCard} testID="stats-dashboard">
            <Text style={styles.cardTitle}>Performance ({stats.completed_trades} closed trades)</Text>
            <View style={styles.bigStats}>
              <View style={styles.bigStat}>
                <Text style={styles.bigStatLabel}>WIN RATE</Text>
                <Text style={[styles.bigStatVal, { color: stats.win_rate >= 50 ? colors.profit : colors.loss }]}>
                  {stats.win_rate}%
                </Text>
                <Text style={styles.bigStatSub}>{stats.wins}W / {stats.losses}L</Text>
              </View>
              <View style={styles.bigStat}>
                <Text style={styles.bigStatLabel}>TOTAL P&L</Text>
                <Text style={[styles.bigStatVal, { color: stats.total_pnl >= 0 ? colors.profit : colors.loss }]}>
                  {stats.total_pnl >= 0 ? "+" : ""}₹{Number(stats.total_pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </Text>
                <Text style={styles.bigStatSub}>avg ₹{Number(stats.avg_pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}/trade</Text>
              </View>
            </View>

            <View style={styles.miniStats}>
              <View style={styles.miniStat}>
                <Text style={styles.miniLabel}>Avg Win</Text>
                <Text style={[styles.miniVal, { color: colors.profit }]}>+₹{Number(stats.avg_win).toFixed(0)}</Text>
              </View>
              <View style={styles.miniStat}>
                <Text style={styles.miniLabel}>Avg Loss</Text>
                <Text style={[styles.miniVal, { color: colors.loss }]}>₹{Number(stats.avg_loss).toFixed(0)}</Text>
              </View>
            </View>

            {stats.best_trade && (
              <View style={styles.tradeHighlight}>
                <Trophy color={colors.profit} size={14} />
                <View style={{ flex: 1, marginLeft: 8 }}>
                  <Text style={styles.tradeHighlightLabel}>BEST TRADE</Text>
                  <Text style={styles.tradeHighlightText}>
                    {stats.best_trade.symbol.replace(".NS", "")} · +₹{stats.best_trade.pnl.toFixed(0)} ({stats.best_trade.pct.toFixed(2)}%)
                  </Text>
                </View>
              </View>
            )}
            {stats.worst_trade && stats.worst_trade.pnl < 0 && (
              <View style={[styles.tradeHighlight, { backgroundColor: colors.loss + "11", borderColor: colors.loss + "44" }]}>
                <Target color={colors.loss} size={14} />
                <View style={{ flex: 1, marginLeft: 8 }}>
                  <Text style={styles.tradeHighlightLabel}>WORST TRADE</Text>
                  <Text style={styles.tradeHighlightText}>
                    {stats.worst_trade.symbol.replace(".NS", "")} · ₹{stats.worst_trade.pnl.toFixed(0)} ({stats.worst_trade.pct.toFixed(2)}%)
                  </Text>
                </View>
              </View>
            )}

            {stats.by_symbol?.length > 0 && (
              <View style={{ marginTop: 14 }}>
                <Text style={styles.bySymTitle}>By Symbol</Text>
                {stats.by_symbol.slice(0, 5).map((s: any) => (
                  <View key={s.symbol} style={styles.bySymRow} testID={`bysym-${s.symbol.replace(".NS", "")}`}>
                    <Text style={styles.bySymName}>{s.symbol.replace(".NS", "")}</Text>
                    <Text style={styles.bySymMeta}>{s.trades} trades · {s.win_rate}% win</Text>
                    <Text style={[styles.bySymPnl, { color: s.pnl >= 0 ? colors.profit : colors.loss }]}>
                      {s.pnl >= 0 ? "+" : ""}₹{Number(s.pnl).toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* Config */}
        <View style={styles.statsCard}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Strategy Config</Text>
            <TouchableOpacity testID="edit-config" onPress={() => setEditorOpen(true)} style={styles.editBtn}>
              <Edit3 color={colors.accent} size={14} />
              <Text style={styles.editBtnText}>Edit</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.cfgList}>
            <Cfg label="Watched stocks" value={`${cfg.symbols?.length || 0}: ${(cfg.symbols || []).slice(0, 4).map((s: string) => s.replace(".NS", "")).join(", ")}${(cfg.symbols?.length || 0) > 4 ? "…" : ""}`} />
            <Cfg label="Scan interval" value={`${cfg.interval_seconds}s (${Math.round(cfg.interval_seconds/60)} min)`} />
            <Cfg label="Buy when" value={`≥ ${cfg.min_buy_signals} of 5 algos say BUY`} />
            <Cfg label="Sell when" value={`≥ ${cfg.min_sell_signals} of 5 algos say SELL`} />
            <Cfg label="Max ₹ per trade" value={`₹${Number(cfg.max_position_size).toLocaleString("en-IN")}`} />
            <Cfg label="Max trades/day" value={cfg.max_trades_per_day} />
            <Cfg label="Auto stop-loss" value={`-${cfg.stop_loss_pct}%`} />
            <Cfg label="Auto take-profit" value={`+${cfg.take_profit_pct}%`} />
          </View>
        </View>

        {/* Decision Log */}
        <View style={styles.statsCard}>
          <View style={styles.cardHeader}>
            <Text style={styles.cardTitle}>Decision Log ({decisions.length})</Text>
            {decisions.length > 0 && (
              <TouchableOpacity testID="clear-log" onPress={async () => { await api.botClearDecisions(); load(); }} style={styles.editBtn}>
                <Trash2 color={colors.loss} size={12} />
                <Text style={[styles.editBtnText, { color: colors.loss }]}>Clear</Text>
              </TouchableOpacity>
            )}
          </View>
          {decisions.length === 0 ? (
            <Text style={styles.empty}>No decisions yet. Start the bot to see scan results.</Text>
          ) : (
            decisions.slice(0, 15).map((d, i) => {
              const Icon = d.action === "BUY" ? TrendingUp : d.action === "SELL" ? TrendingDown : Minus;
              const color = d.action === "BUY" ? colors.profit : d.action === "SELL" ? colors.loss : colors.textMuted;
              const time = new Date(d.timestamp).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
              return (
                <View key={i} style={styles.decisionRow} testID={`decision-${i}`}>
                  <View style={[styles.decisionBadge, { borderColor: color, backgroundColor: color + "22" }]}>
                    <Icon color={color} size={11} />
                    <Text style={[styles.decisionBadgeText, { color }]}>{d.action}</Text>
                  </View>
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <Text style={styles.decisionSym}>{(d.symbol || "").replace(".NS", "")} <Text style={styles.decisionPrice}>₹{(d.price || 0).toFixed(2)}</Text></Text>
                    <Text style={styles.decisionReason} numberOfLines={1}>{d.reason}</Text>
                  </View>
                  <Text style={styles.decisionTime}>{time}</Text>
                </View>
              );
            })
          )}
        </View>

        {/* Info */}
        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>How it works</Text>
          <Text style={styles.infoText}>
            1. Every {Math.round((cfg.interval_seconds || 300)/60)} min, bot scans your watched stocks{"\n"}
            2. If ≥3 of 5 algorithms (SMA, EMA, RSI, MACD, Bollinger) say BUY → opens position{"\n"}
            3. If ≥3 say SELL → closes existing position{"\n"}
            4. Auto stop-loss at -{cfg.stop_loss_pct}%, take-profit at +{cfg.take_profit_pct}%{"\n"}
            5. Max {cfg.max_trades_per_day} trades per day, ₹{Number(cfg.max_position_size||0).toLocaleString("en-IN")} per position{"\n"}{"\n"}
            <Text style={{ color: colors.warning }}>⚠ Paper Mode</Text>: trades hit your virtual ₹10L portfolio only. No real money.{"\n"}
            <Text style={{ color: colors.loss }}>⚠ Live Mode</Text>: places REAL Fyers orders. Requires Fyers connection from Settings.
          </Text>
        </View>
      </ScrollView>

      <BotConfigEditor
        visible={editorOpen}
        initial={cfg}
        onClose={() => setEditorOpen(false)}
        onSaved={load}
      />
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </SafeAreaView>
  );
}

function Stat({ label, value, color }: { label: string; value: any; color?: string }) {
  return (
    <View style={styles.statCell}>
      <Text style={styles.statLabel}>{label}</Text>
      <Text style={[styles.statValue, color && { color }]}>{value ?? 0}</Text>
    </View>
  );
}

function Cfg({ label, value }: { label: string; value: any }) {
  return (
    <View style={styles.cfgRow}>
      <Text style={styles.cfgKey}>{label}</Text>
      <Text style={styles.cfgVal}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 16 },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 26 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 4 },
  statusCard: { marginHorizontal: 12, backgroundColor: colors.surface, borderRadius: 16, borderWidth: 1, padding: 18 },
  row: { flexDirection: "row", alignItems: "center" },
  iconBubble: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center" },
  statusTitle: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 18 },
  statusMode: { fontFamily: fonts.bodyMed, fontSize: 12, marginTop: 4 },
  bigBtn: { flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", paddingVertical: 14, borderRadius: 12, marginTop: 18 },
  bigBtnText: { fontFamily: fonts.bodySemi, color: "#fff", fontSize: 14 },
  statsCard: { marginHorizontal: 12, marginTop: 12, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 14 },
  cardTitle: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 14, marginBottom: 10 },
  cardHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 10 },
  editBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 6, borderWidth: 1, borderColor: colors.border },
  editBtnText: { fontFamily: fonts.bodySemi, color: colors.accent, fontSize: 11 },
  empty: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, padding: 16, textAlign: "center" },
  decisionRow: { flexDirection: "row", alignItems: "center", paddingVertical: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  decisionBadge: { flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: 7, paddingVertical: 4, borderRadius: 5, borderWidth: 1, minWidth: 52, justifyContent: "center" },
  decisionBadgeText: { fontFamily: fonts.bodySemi, fontSize: 10 },
  decisionSym: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 12 },
  decisionPrice: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 11 },
  decisionReason: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, marginTop: 1 },
  decisionTime: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 10 },
  bigStats: { flexDirection: "row", gap: 10 },
  bigStat: { flex: 1, backgroundColor: colors.bg, padding: 12, borderRadius: 10, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  bigStatLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1.5 },
  bigStatVal: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 22, marginTop: 4 },
  bigStatSub: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 10, marginTop: 2 },
  miniStats: { flexDirection: "row", gap: 10, marginTop: 10 },
  miniStat: { flex: 1, paddingVertical: 8, paddingHorizontal: 12, backgroundColor: colors.bg, borderRadius: 8, borderWidth: 1, borderColor: colors.border, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  miniLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11 },
  miniVal: { fontFamily: fonts.monoBold, fontSize: 12 },
  tradeHighlight: { flexDirection: "row", alignItems: "center", backgroundColor: colors.profit + "11", borderWidth: 1, borderColor: colors.profit + "44", padding: 10, borderRadius: 10, marginTop: 10 },
  tradeHighlightLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 9, letterSpacing: 1.5 },
  tradeHighlightText: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 12, marginTop: 2 },
  bySymTitle: { fontFamily: fonts.bodySemi, color: colors.textSecondary, fontSize: 11, marginBottom: 6, letterSpacing: 1 },
  bySymRow: { flexDirection: "row", alignItems: "center", paddingVertical: 7, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  bySymName: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 12, width: 80 },
  bySymMeta: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 10, flex: 1 },
  bySymPnl: { fontFamily: fonts.monoBold, fontSize: 12 },
  statsGrid: { flexDirection: "row", gap: 8 },
  statCell: { flex: 1, backgroundColor: colors.bg, borderRadius: 8, padding: 10, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  statLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, letterSpacing: 1 },
  statValue: { fontFamily: fonts.monoBold, color: colors.textPrimary, fontSize: 18, marginTop: 4 },
  lastTick: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 11, marginTop: 12, textAlign: "center" },
  errorBox: { flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.warning + "11", padding: 10, borderRadius: 8, marginTop: 10, borderWidth: 1, borderColor: colors.warning + "44" },
  errorText: { fontFamily: fonts.body, color: colors.warning, fontSize: 11, flex: 1 },
  cfgList: { gap: 4 },
  cfgRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border, gap: 8 },
  cfgKey: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11 },
  cfgVal: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 12, maxWidth: "60%", textAlign: "right" },
  infoCard: { marginHorizontal: 12, marginTop: 12, backgroundColor: colors.accent + "11", borderRadius: 14, borderWidth: 1, borderColor: colors.accent + "44", padding: 14 },
  infoTitle: { fontFamily: fonts.headingSemi, color: colors.accent, fontSize: 13, marginBottom: 8 },
  infoText: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 12, lineHeight: 19 },
});
