import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, TouchableOpacity, Linking, Alert, Platform, Modal } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { api } from "@/src/api";
import { colors, fonts } from "@/src/theme";
import { ArrowLeft, Link2, LogOut, RefreshCw, ShieldCheck, ShieldAlert, ExternalLink } from "lucide-react-native";

export default function Settings() {
  const router = useRouter();
  const [status, setStatus] = useState<any>(null);
  const [profile, setProfile] = useState<any>(null);
  const [funds, setFunds] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [showDisconnect, setShowDisconnect] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await api.fyersStatus();
      setStatus(s);
      if (s.connected) {
        try {
          const [p, f] = await Promise.all([api.fyersProfile(), api.fyersFunds()]);
          setProfile(p);
          setFunds(f);
        } catch (e) {
          console.warn("Could not fetch profile/funds:", e);
        }
      }
    } catch (e) {
      console.warn("fyers status", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const connect = async () => {
    setConnecting(true);
    try {
      const { login_url } = await api.fyersLoginUrl();
      if (Platform.OS === "web") {
        const w = window.open(login_url, "_blank");
        if (!w) {
          window.location.href = login_url;
        }
      } else {
        await Linking.openURL(login_url);
      }
      // Poll for status changes every 3s for 2 minutes
      let attempts = 0;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const s = await api.fyersStatus();
          if (s.connected) {
            clearInterval(poll);
            setStatus(s);
            await load();
            setConnecting(false);
          }
        } catch {}
        if (attempts > 40) {
          clearInterval(poll);
          setConnecting(false);
        }
      }, 3000);
    } catch (e: any) {
      setConnecting(false);
      Alert.alert("Connection failed", e.message || "Could not start Fyers login");
    }
  };

  const disconnect = () => setShowDisconnect(true);

  const confirmDisconnect = async () => {
    setShowDisconnect(false);
    try {
      await api.fyersDisconnect();
      setStatus({ configured: true, connected: false });
      setProfile(null);
      setFunds(null);
    } catch (e: any) {
      console.warn("Disconnect failed", e);
    }
  };

  const fundsLine = Array.isArray(funds) ? funds.find((f: any) => f.title?.toLowerCase().includes("available") || f.id === 10) : null;
  const availableCash = fundsLine?.equityAmount ?? fundsLine?.commodityAmount ?? 0;

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <TouchableOpacity testID="settings-back" onPress={() => router.back()} style={styles.iconBtn}>
          <ArrowLeft color={colors.textPrimary} size={22} />
        </TouchableOpacity>
        <Text style={styles.title}>Settings</Text>
        <TouchableOpacity onPress={load} style={styles.iconBtn}>
          <RefreshCw color={colors.textMuted} size={18} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 60 }}>
        {loading && <ActivityIndicator color={colors.accent} style={{ marginTop: 40 }} />}

        {!loading && (
          <View style={styles.card} testID="fyers-card">
            <View style={styles.row}>
              <View style={[styles.iconBubble, { backgroundColor: (status?.connected ? colors.profit : colors.warning) + "22" }]}>
                {status?.connected
                  ? <ShieldCheck color={colors.profit} size={20} />
                  : <ShieldAlert color={colors.warning} size={20} />}
              </View>
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.cardTitle}>Fyers Broker</Text>
                <Text style={[styles.cardSub, { color: status?.connected ? colors.profit : colors.textMuted }]}>
                  {status?.connected ? "Connected" : status?.configured ? "Not connected" : "Not configured"}
                </Text>
              </View>
            </View>

            {status?.connected ? (
              <>
                {profile && (
                  <View style={styles.kvList}>
                    <View style={styles.kv}><Text style={styles.kvKey}>Name</Text><Text style={styles.kvVal}>{profile.name || "—"}</Text></View>
                    <View style={styles.kv}><Text style={styles.kvKey}>Fyers ID</Text><Text style={styles.kvVal}>{profile.fy_id || "—"}</Text></View>
                    <View style={styles.kv}><Text style={styles.kvKey}>PAN</Text><Text style={styles.kvVal}>{profile.PAN || profile.pan || "—"}</Text></View>
                    <View style={styles.kv}><Text style={styles.kvKey}>Email</Text><Text style={styles.kvVal} numberOfLines={1}>{profile.email_id || profile.email || "—"}</Text></View>
                  </View>
                )}
                {!!availableCash && (
                  <View style={styles.cashCard}>
                    <Text style={styles.cashLabel}>AVAILABLE EQUITY CASH</Text>
                    <Text style={styles.cashVal}>₹{Number(availableCash).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</Text>
                  </View>
                )}
                <Text style={styles.expHint}>
                  Token valid until: {status.access_expires_at ? new Date(status.access_expires_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "—"}
                </Text>
                <TouchableOpacity testID="disconnect-fyers" onPress={disconnect} style={styles.dangerBtn} activeOpacity={0.8}>
                  <LogOut color={colors.loss} size={16} />
                  <Text style={[styles.btnText, { color: colors.loss }]}>Disconnect Fyers</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                <Text style={styles.bodyText}>
                  Connect your Fyers account to get <Text style={{ color: colors.profit }}>live NSE/BSE prices</Text>, <Text style={{ color: colors.profit }}>real option chain</Text>, holdings, funds and the ability to place real orders.
                </Text>
                <View style={styles.warnBox}>
                  <Text style={styles.warnText}>
                    ⚠ Once connected, BUY/SELL on the stock detail screen can place REAL orders with REAL money. We've added a safety toggle — real orders only fire when you explicitly enable Live Mode.
                  </Text>
                </View>
                <TouchableOpacity testID="connect-fyers" onPress={connect} disabled={connecting} style={styles.primaryBtn} activeOpacity={0.8}>
                  <Link2 color="#fff" size={16} />
                  <Text style={[styles.btnText, { color: "#fff" }]}>
                    {connecting ? "Waiting for Fyers login…" : "Connect Fyers Account"}
                  </Text>
                </TouchableOpacity>
                <Text style={styles.hint}>You'll be redirected to fyers.in. After login, return to this app — it'll detect the connection automatically.</Text>
              </>
            )}
          </View>
        )}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>About</Text>
          <View style={styles.kvList}>
            <View style={styles.kv}><Text style={styles.kvKey}>App</Text><Text style={styles.kvVal}>AlgoBot India</Text></View>
            <View style={styles.kv}><Text style={styles.kvKey}>Markets</Text><Text style={styles.kvVal}>NSE • BSE • Options</Text></View>
            <View style={styles.kv}><Text style={styles.kvKey}>Algorithms</Text><Text style={styles.kvVal}>5 indicators + 7 option strategies</Text></View>
            <View style={styles.kv}><Text style={styles.kvKey}>Paper Capital</Text><Text style={styles.kvVal}>₹10,00,000</Text></View>
          </View>
        </View>

        <Text style={styles.disclaimer}>
          ⚠ This app is for educational and informational purposes. Trading involves substantial risk of loss. Past performance does not guarantee future results. Never invest more than you can afford to lose.
        </Text>
      </ScrollView>

      <Modal visible={showDisconnect} transparent animationType="fade" onRequestClose={() => setShowDisconnect(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard} testID="disconnect-modal">
            <Text style={styles.modalTitle}>Disconnect Fyers?</Text>
            <Text style={styles.modalBody}>
              Your access token will be removed. You can reconnect anytime, but you'll lose real-time prices and option chain until you do.
            </Text>
            <View style={styles.modalBtns}>
              <TouchableOpacity testID="cancel-disconnect" onPress={() => setShowDisconnect(false)} style={[styles.modalBtn, { backgroundColor: colors.surfaceElev }]}>
                <Text style={[styles.modalBtnText, { color: colors.textPrimary }]}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="confirm-disconnect" onPress={confirmDisconnect} style={[styles.modalBtn, { backgroundColor: colors.loss }]}>
                <Text style={styles.modalBtnText}>Disconnect</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: 12, paddingTop: 8, paddingBottom: 8 },
  iconBtn: { padding: 8 },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 22, flex: 1, textAlign: "center" },
  card: { marginHorizontal: 12, marginTop: 12, backgroundColor: colors.surface, borderRadius: 14, borderWidth: 1, borderColor: colors.border, padding: 16 },
  cardTitle: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 16 },
  cardSub: { fontFamily: fonts.bodySemi, fontSize: 12, marginTop: 2 },
  row: { flexDirection: "row", alignItems: "center" },
  iconBubble: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  bodyText: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 13, lineHeight: 20, marginTop: 14 },
  warnBox: { backgroundColor: colors.warning + "11", borderWidth: 1, borderColor: colors.warning + "55", borderRadius: 10, padding: 12, marginTop: 12 },
  warnText: { fontFamily: fonts.body, color: colors.warning, fontSize: 11, lineHeight: 17 },
  primaryBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.accent, paddingVertical: 14, borderRadius: 12, marginTop: 16 },
  dangerBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.loss + "22", borderWidth: 1, borderColor: colors.loss, paddingVertical: 12, borderRadius: 12, marginTop: 16 },
  btnText: { fontFamily: fonts.bodySemi, fontSize: 14 },
  hint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11, marginTop: 10, textAlign: "center", lineHeight: 17 },
  expHint: { fontFamily: fonts.mono, color: colors.textMuted, fontSize: 11, marginTop: 12, textAlign: "center" },
  kvList: { marginTop: 14, gap: 8 },
  kv: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6 },
  kvKey: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12 },
  kvVal: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 13, maxWidth: "60%", textAlign: "right" },
  cashCard: { backgroundColor: colors.bg, borderRadius: 10, padding: 14, marginTop: 14, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  cashLabel: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 10, letterSpacing: 2 },
  cashVal: { fontFamily: fonts.monoBold, color: colors.profit, fontSize: 22, marginTop: 4 },
  disclaimer: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 11, lineHeight: 17, padding: 20, textAlign: "center" },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "center", alignItems: "center", padding: 20 },
  modalCard: { backgroundColor: colors.surface, borderRadius: 16, padding: 24, borderWidth: 1, borderColor: colors.border, maxWidth: 420, width: "100%" },
  modalTitle: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 20, textAlign: "center" },
  modalBody: { fontFamily: fonts.body, color: colors.textSecondary, fontSize: 13, marginTop: 12, lineHeight: 20, textAlign: "center" },
  modalBtns: { flexDirection: "row", gap: 10, marginTop: 20 },
  modalBtn: { flex: 1, paddingVertical: 14, borderRadius: 10, alignItems: "center" },
  modalBtnText: { fontFamily: fonts.bodySemi, color: "#fff", fontSize: 14 },
});
