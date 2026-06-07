import React, { useCallback, useEffect, useState } from "react";
import { View, Text, StyleSheet, ScrollView, RefreshControl, ActivityIndicator, TouchableOpacity, Modal, TextInput } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, Quote } from "@/src/api";
import { colors, fonts } from "@/src/theme";
import { StockRow } from "@/src/components/StockRow";
import { Plus, X, Search } from "lucide-react-native";

export default function Watchlist() {
  const [items, setItems] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<{ symbol: string; name: string }[]>([]);

  const load = useCallback(async () => {
    try {
      const data = await api.watchlist();
      setItems(data);
    } catch (e) {
      console.warn("watchlist", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Search popular stocks
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (search.trim().length < 1) { setResults([]); return; }
      try {
        const res = await fetch(`${process.env.EXPO_PUBLIC_BACKEND_URL}/api/stocks/search?q=${encodeURIComponent(search)}`);
        const data = await res.json();
        if (!cancelled) setResults(data);
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [search]);

  const handleAdd = async (symbol: string, name: string) => {
    try {
      await api.addWatch(symbol, name);
      setShowAdd(false);
      setSearch("");
      setResults([]);
      load();
    } catch (e) {
      console.warn(e);
    }
  };

  const handleRemove = async (symbol: string) => {
    await api.removeWatch(symbol);
    load();
  };

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <View>
          <Text style={styles.title}>Watchlist</Text>
          <Text style={styles.subtitle}>Your tracked stocks</Text>
        </View>
        <TouchableOpacity testID="add-watchlist-btn" onPress={() => setShowAdd(true)} style={styles.addBtn} activeOpacity={0.7}>
          <Plus color={colors.bg} size={18} />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ paddingBottom: 120 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={colors.accent} />}
      >
        {loading && <ActivityIndicator color={colors.accent} style={{ marginTop: 40 }} />}
        {!loading && items.length === 0 && (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>No stocks in watchlist</Text>
            <Text style={styles.emptyHint}>Tap + to add stocks you want to track</Text>
          </View>
        )}
        <View style={styles.list}>
          {items.map((s) => (
            <View key={s.symbol} style={styles.rowWrap}>
              <View style={{ flex: 1 }}>
                <StockRow symbol={s.symbol} name={(s as any).name} price={s.price} change={s.change} change_pct={s.change_pct} showArrow={false} />
              </View>
              <TouchableOpacity testID={`remove-${s.symbol}`} onPress={() => handleRemove(s.symbol)} style={styles.removeBtn} activeOpacity={0.6}>
                <X color={colors.textMuted} size={18} />
              </TouchableOpacity>
            </View>
          ))}
        </View>
      </ScrollView>

      <Modal visible={showAdd} transparent animationType="slide" onRequestClose={() => setShowAdd(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Add to Watchlist</Text>
              <TouchableOpacity testID="close-add" onPress={() => setShowAdd(false)}>
                <X color={colors.textPrimary} size={22} />
              </TouchableOpacity>
            </View>
            <View style={styles.searchBox}>
              <Search color={colors.textMuted} size={16} />
              <TextInput
                testID="search-input"
                value={search}
                onChangeText={setSearch}
                placeholder="Search e.g. RELIANCE, TCS"
                placeholderTextColor={colors.textMuted}
                style={styles.input}
                autoFocus
              />
            </View>
            <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 380 }}>
              {results.map((r) => (
                <TouchableOpacity key={r.symbol} testID={`add-${r.symbol}`} onPress={() => handleAdd(r.symbol, r.name)} style={styles.resultRow} activeOpacity={0.7}>
                  <Text style={styles.resultSym}>{r.symbol.replace(".NS", "")}</Text>
                  <Text style={styles.resultName}>{r.name}</Text>
                </TouchableOpacity>
              ))}
              {search && results.length === 0 && <Text style={styles.noResult}>No matches</Text>}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 16, flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { fontFamily: fonts.heading, color: colors.textPrimary, fontSize: 26 },
  subtitle: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 4 },
  addBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.accent, alignItems: "center", justifyContent: "center" },
  list: { marginHorizontal: 12, backgroundColor: colors.surface, borderRadius: 12, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  rowWrap: { flexDirection: "row", alignItems: "center" },
  removeBtn: { padding: 14 },
  empty: { alignItems: "center", marginTop: 80, paddingHorizontal: 24 },
  emptyText: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 16 },
  emptyHint: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 13, marginTop: 6 },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.7)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 16, paddingBottom: 30, maxHeight: "80%" },
  modalHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 16 },
  modalTitle: { fontFamily: fonts.headingSemi, color: colors.textPrimary, fontSize: 18 },
  searchBox: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: colors.bg, borderRadius: 10, paddingHorizontal: 12, borderWidth: 1, borderColor: colors.border },
  input: { flex: 1, color: colors.textPrimary, fontFamily: fonts.body, paddingVertical: 12, fontSize: 14 },
  resultRow: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  resultSym: { fontFamily: fonts.bodySemi, color: colors.textPrimary, fontSize: 14 },
  resultName: { fontFamily: fonts.body, color: colors.textMuted, fontSize: 12, marginTop: 2 },
  noResult: { fontFamily: fonts.body, color: colors.textMuted, textAlign: "center", marginTop: 20 },
});
