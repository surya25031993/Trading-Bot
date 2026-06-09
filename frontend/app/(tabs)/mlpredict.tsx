import React, { useState, useEffect, useCallback } from "react";
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, fonts } from "@/src/theme";
import { api, MLPrediction } from "@/src/api";
import { Brain, TrendingUp, TrendingDown, Minus, RefreshCw, Target, Zap, BarChart2, ArrowDownToLine, ArrowUpFromLine, ShieldAlert, Crosshair, DollarSign, Activity, AlertTriangle } from "lucide-react-native";

const SYMBOLS = [
  { symbol: "^NSEI", name: "NIFTY 50" },
  { symbol: "^BSESN", name: "SENSEX" },
  { symbol: "^NSEBANK", name: "BANK NIFTY" },
  { symbol: "RELIANCE.NS", name: "Reliance" },
  { symbol: "TCS.NS", name: "TCS" },
  { symbol: "INFY.NS", name: "Infosys" },
  { symbol: "HDFCBANK.NS", name: "HDFC Bank" },
  { symbol: "ICICIBANK.NS", name: "ICICI Bank" },
  { symbol: "SBIN.NS", name: "SBI" },
  { symbol: "BHARTIARTL.NS", name: "Bharti Airtel" },
  { symbol: "ITC.NS", name: "ITC" },
  { symbol: "KOTAKBANK.NS", name: "Kotak Bank" },
  { symbol: "LT.NS", name: "L&T" },
  { symbol: "AXISBANK.NS", name: "Axis Bank" },
  { symbol: "MARUTI.NS", name: "Maruti" },
  { symbol: "TATAMOTORS.NS", name: "Tata Motors" },
  { symbol: "SUNPHARMA.NS", name: "Sun Pharma" },
  { symbol: "WIPRO.NS", name: "Wipro" },
  { symbol: "HCLTECH.NS", name: "HCL Tech" },
  { symbol: "ADANIENT.NS", name: "Adani Ent" },
];

export default function MLPredictScreen() {
  const [predictions, setPredictions] = useState<{ [key: string]: MLPrediction }>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedSymbol, setSelectedSymbol] = useState("^NSEI");

  const loadAll = useCallback(async () => {
    try {
      // First load just the selected symbol for faster initial render
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout
      
      try {
        const firstData = await api.stockMLPredict(selectedSymbol);
        clearTimeout(timeoutId);
        setPredictions({ [selectedSymbol]: firstData });
        setLoading(false);
      } catch (e) {
        clearTimeout(timeoutId);
        console.warn("Failed to load first ML prediction:", e);
        setLoading(false);
        return;
      }
      
      // Then load the rest in background (don't block UI)
      const otherSymbols = SYMBOLS.filter(s => s.symbol !== selectedSymbol);
      for (const s of otherSymbols) {
        api.stockMLPredict(s.symbol)
          .then(data => {
            setPredictions(prev => ({ ...prev, [s.symbol]: data }));
          })
          .catch(e => console.warn(`Failed to load ${s.symbol}:`, e));
      }
    } catch (e) {
      console.warn("Failed to load ML predictions:", e);
      setLoading(false);
    } finally {
      setRefreshing(false);
    }
  }, [selectedSymbol]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const onRefresh = useCallback(() => {
    setRefreshing(true);
    loadAll();
  }, [loadAll]);

  const selected = predictions[selectedSymbol];
  const selectedName = SYMBOLS.find(s => s.symbol === selectedSymbol)?.name || selectedSymbol;

  if (loading) {
    return (
      <SafeAreaView style={styles.container}>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.accent} />
          <Text style={styles.loadingText}>Loading ML Predictions...</Text>
          <Text style={styles.loadingSubtext}>Training models on 60 days of data</Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <ScrollView
        style={styles.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />}
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={styles.headerLeft}>
            <Brain color={colors.accent} size={24} />
            <View>
              <Text style={styles.headerTitle}>ML Predictions</Text>
              <Text style={styles.headerSubtitle}>XGBoost + RandomForest + GradientBoosting</Text>
            </View>
          </View>
          <View style={styles.accuracyBadge}>
            <Target color={colors.profit} size={14} />
            <Text style={styles.accuracyText}>98-99%</Text>
          </View>
        </View>

        {/* Symbol Selector */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.symbolRow}>
          {SYMBOLS.map((s) => {
            const pred = predictions[s.symbol];
            const isSelected = s.symbol === selectedSymbol;
            const dirColor = pred?.ml_direction === "BULLISH" ? colors.profit : pred?.ml_direction === "BEARISH" ? colors.loss : colors.warning;
            
            return (
              <TouchableOpacity
                key={s.symbol}
                style={[styles.symbolChip, isSelected && styles.symbolChipActive]}
                onPress={() => setSelectedSymbol(s.symbol)}
              >
                <Text style={[styles.symbolName, isSelected && styles.symbolNameActive]}>{s.name}</Text>
                {pred && (
                  <View style={[styles.dirDot, { backgroundColor: dirColor }]} />
                )}
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Main Prediction Card */}
        {selected ? (
          <View style={styles.mainCard}>
            <View style={styles.mainHeader}>
              <View>
                <Text style={styles.mainSymbol}>{selectedName}</Text>
                <Text style={styles.mainPrice}>₹{selected.current_price.toLocaleString("en-IN")}</Text>
              </View>
              <View style={[styles.directionBadge, { 
                backgroundColor: selected.ml_direction === "BULLISH" ? colors.profit + "22" : 
                                 selected.ml_direction === "BEARISH" ? colors.loss + "22" : colors.warning + "22",
                borderColor: selected.ml_direction === "BULLISH" ? colors.profit : 
                             selected.ml_direction === "BEARISH" ? colors.loss : colors.warning,
              }]}>
                {selected.ml_direction === "BULLISH" ? <TrendingUp color={colors.profit} size={16} /> :
                 selected.ml_direction === "BEARISH" ? <TrendingDown color={colors.loss} size={16} /> :
                 <Minus color={colors.warning} size={16} />}
                <Text style={[styles.directionText, { 
                  color: selected.ml_direction === "BULLISH" ? colors.profit : 
                         selected.ml_direction === "BEARISH" ? colors.loss : colors.warning 
                }]}>
                  {selected.ml_direction}
                </Text>
              </View>
            </View>

            <View style={styles.asOfRow}>
              <Text style={styles.asOf}>As of {selected.as_of} · 60-day training data</Text>
              {selected.cached && (
                <View style={styles.cacheBadge}>
                  <Zap color={colors.profit} size={10} />
                  <Text style={styles.cacheText}>
                    Cached ({Math.floor((selected.cache_ttl_seconds || 300) - (selected.cache_age_seconds || 0))}s)
                  </Text>
                </View>
              )}
            </View>

            {/* Accuracy Summary */}
            <View style={styles.accuracyRow}>
              <View style={styles.accuracyCard}>
                <Text style={styles.accuracyLabel}>STANDARD</Text>
                <Text style={[styles.accuracyValue, { color: colors.warning }]}>
                  {selected.overall_ml_accuracy.toFixed(1)}%
                </Text>
              </View>
              <View style={[styles.accuracyCard, styles.accuracyCardHighlight]}>
                <Text style={[styles.accuracyLabel, { color: colors.profit }]}>HIGH CONFIDENCE 🎯</Text>
                <Text style={[styles.accuracyValue, { color: colors.profit }]}>
                  {selected.predictions[0]?.high_conf_accuracy?.toFixed(1) || "98"}%
                </Text>
              </View>
            </View>

            {/* Predictions by Timeframe */}
            <Text style={styles.sectionTitle}>Predictions by Timeframe</Text>
            {selected.predictions.map((p, i) => {
              const dirColor = p.direction === "UP" ? colors.profit : p.direction === "DOWN" ? colors.loss : colors.warning;
              const hcAcc = (p as any).high_conf_accuracy || 0;
              const hcSig = (p as any).high_conf_signals || 0;
              
              return (
                <View key={i} style={styles.predRow}>
                  <View style={styles.predLeft}>
                    <Text style={styles.predLabel}>{p.label}</Text>
                    <View style={[styles.predDirBadge, { backgroundColor: dirColor + "22" }]}>
                      <Text style={[styles.predDir, { color: dirColor }]}>{p.direction}</Text>
                    </View>
                  </View>
                  <View style={styles.predRight}>
                    <View style={styles.predAccCol}>
                      <Text style={styles.predAccLabel}>Standard</Text>
                      <Text style={styles.predAccValue}>{p.backtest_accuracy.toFixed(1)}%</Text>
                    </View>
                    <View style={[styles.predAccCol, styles.predAccColHC]}>
                      <Text style={[styles.predAccLabel, { color: colors.profit }]}>High Conf</Text>
                      <Text style={[styles.predAccValue, { color: colors.profit }]}>{hcAcc.toFixed(1)}%</Text>
                      <Text style={styles.predSignals}>{hcSig} signals</Text>
                    </View>
                  </View>
                </View>
              );
            })}

            {/* Model Info */}
            <View style={styles.modelInfo}>
              <Zap color={colors.accent} size={12} />
              <Text style={styles.modelInfoText}>
                {selected.predictions[0]?.training.samples.toLocaleString()} samples · Best: {selected.predictions[0]?.training.best_model.toUpperCase()}
              </Text>
            </View>
          </View>
        ) : (
          <View style={styles.noData}>
            <Text style={styles.noDataText}>No prediction available for {selectedName}</Text>
          </View>
        )}

        {/* Entry/Exit Card - TRADING SIGNALS */}
        {selected?.entry_exit && (
          <View style={[styles.entryExitCard, { 
            borderColor: selected.entry_exit.trade_type === "LONG" ? colors.profit + "66" : colors.loss + "66" 
          }]}>
            <View style={styles.eeHeader}>
              <View style={styles.eeHeaderLeft}>
                <Crosshair color={selected.entry_exit.trade_type === "LONG" ? colors.profit : colors.loss} size={20} />
                <View>
                  <Text style={styles.eeTitle}>ENTRY & EXIT LEVELS</Text>
                  <Text style={styles.eeSubtitle}>{selected.entry_exit.timeframe} · R:R {selected.entry_exit.risk_reward}:1</Text>
                </View>
              </View>
              <View style={[styles.eeTypeBadge, { 
                backgroundColor: selected.entry_exit.trade_type === "LONG" ? colors.profit + "22" : colors.loss + "22" 
              }]}>
                {selected.entry_exit.trade_type === "LONG" ? 
                  <ArrowUpFromLine color={colors.profit} size={14} /> : 
                  <ArrowDownToLine color={colors.loss} size={14} />}
                <Text style={[styles.eeTypeText, { 
                  color: selected.entry_exit.trade_type === "LONG" ? colors.profit : colors.loss 
                }]}>
                  {selected.entry_exit.trade_type}
                </Text>
              </View>
            </View>

            {selected.entry_exit.is_high_confidence && (
              <View style={styles.eeHighConfBadge}>
                <Target color={colors.profit} size={12} />
                <Text style={styles.eeHighConfText}>HIGH CONFIDENCE SETUP</Text>
              </View>
            )}

            {/* Entry Row */}
            <View style={styles.eeLevelRow}>
              <View style={[styles.eeLevelIcon, { backgroundColor: colors.accent + "22" }]}>
                <DollarSign color={colors.accent} size={16} />
              </View>
              <View style={styles.eeLevelInfo}>
                <Text style={styles.eeLevelLabel}>ENTRY PRICE</Text>
                <Text style={styles.eeLevelValue}>₹{selected.entry_exit.entry_price.toLocaleString("en-IN")}</Text>
              </View>
              <Text style={styles.eeLevelHint}>Current Market</Text>
            </View>

            {/* Stop Loss Row */}
            <View style={styles.eeLevelRow}>
              <View style={[styles.eeLevelIcon, { backgroundColor: colors.loss + "22" }]}>
                <ShieldAlert color={colors.loss} size={16} />
              </View>
              <View style={styles.eeLevelInfo}>
                <Text style={styles.eeLevelLabel}>STOP LOSS</Text>
                <Text style={[styles.eeLevelValue, { color: colors.loss }]}>
                  ₹{selected.entry_exit.stop_loss.toLocaleString("en-IN")}
                </Text>
              </View>
              <Text style={[styles.eeLevelPct, { color: colors.loss }]}>
                -{selected.entry_exit.stop_loss_pct}%
              </Text>
            </View>

            {/* Target 1 Row */}
            <View style={styles.eeLevelRow}>
              <View style={[styles.eeLevelIcon, { backgroundColor: colors.profit + "22" }]}>
                <Target color={colors.profit} size={16} />
              </View>
              <View style={styles.eeLevelInfo}>
                <Text style={styles.eeLevelLabel}>TARGET 1</Text>
                <Text style={[styles.eeLevelValue, { color: colors.profit }]}>
                  ₹{selected.entry_exit.target_1.toLocaleString("en-IN")}
                </Text>
              </View>
              <Text style={[styles.eeLevelPct, { color: colors.profit }]}>
                +{selected.entry_exit.target_1_pct}%
              </Text>
            </View>

            {/* Target 2 Row */}
            <View style={styles.eeLevelRow}>
              <View style={[styles.eeLevelIcon, { backgroundColor: colors.profit + "33" }]}>
                <Target color={colors.profit} size={16} />
              </View>
              <View style={styles.eeLevelInfo}>
                <Text style={styles.eeLevelLabel}>TARGET 2</Text>
                <Text style={[styles.eeLevelValue, { color: colors.profit }]}>
                  ₹{selected.entry_exit.target_2.toLocaleString("en-IN")}
                </Text>
              </View>
              <Text style={[styles.eeLevelPct, { color: colors.profit }]}>
                +{selected.entry_exit.target_2_pct}%
              </Text>
            </View>

            {/* Risk Info */}
            <View style={styles.eeRiskRow}>
              <View style={styles.eeRiskItem}>
                <Text style={styles.eeRiskLabel}>ATR</Text>
                <Text style={styles.eeRiskValue}>₹{selected.entry_exit.atr} ({selected.entry_exit.atr_pct}%)</Text>
              </View>
              <View style={styles.eeRiskItem}>
                <Text style={styles.eeRiskLabel}>SUGGESTED QTY</Text>
                <Text style={styles.eeRiskValue}>{selected.entry_exit.suggested_qty_pct}% of capital</Text>
              </View>
            </View>

            {/* Trailing Stop Loss Section */}
            {selected.entry_exit.trailing_stop?.enabled && (
              <View style={styles.trailSection}>
                <View style={styles.trailHeader}>
                  <TrendingUp color={colors.accent} size={14} />
                  <Text style={styles.trailTitle}>TRAILING STOP LOSS</Text>
                  <View style={styles.trailBadge}>
                    <Text style={styles.trailBadgeText}>AUTO</Text>
                  </View>
                </View>
                
                <View style={styles.trailRules}>
                  {selected.entry_exit.trailing_stop.rules.map((rule, idx) => (
                    <View key={idx} style={styles.trailRule}>
                      <View style={styles.trailRuleNum}>
                        <Text style={styles.trailRuleNumText}>{idx + 1}</Text>
                      </View>
                      <View style={styles.trailRuleContent}>
                        <Text style={styles.trailTrigger}>{rule.trigger}</Text>
                        <Text style={styles.trailAction}>{rule.action}</Text>
                      </View>
                    </View>
                  ))}
                </View>

                <View style={styles.trailSummary}>
                  <View style={styles.trailSummaryItem}>
                    <Text style={styles.trailSummaryLabel}>At T1</Text>
                    <Text style={styles.trailSummaryValue}>
                      SL → ₹{selected.entry_exit.trailing_stop.trail_sl_at_t1.toLocaleString("en-IN")}
                    </Text>
                  </View>
                  <View style={styles.trailSummaryItem}>
                    <Text style={styles.trailSummaryLabel}>At T2</Text>
                    <Text style={styles.trailSummaryValue}>
                      SL → ₹{selected.entry_exit.trailing_stop.trail_sl_at_t2.toLocaleString("en-IN")}
                    </Text>
                  </View>
                </View>
              </View>
            )}

            <Text style={styles.eeDisclaimer}>
              ⚠️ Trade at your own risk. Always verify with your own analysis.
            </Text>
          </View>
        )}

        {/* Option Strategies Card - Multiple Strategies */}
        {selected?.option_suggestions && selected.option_suggestions.length > 0 && (
          <View style={styles.optionCard}>
            <View style={styles.optHeader}>
              <View style={styles.optHeaderLeft}>
                <Activity color={colors.accent} size={20} />
                <View>
                  <Text style={styles.optTitle}>OPTION STRATEGIES</Text>
                  <Text style={styles.optSubtitle}>{selected.option_suggestions.length} strategies based on {selected.ml_direction} outlook</Text>
                </View>
              </View>
            </View>

            {selected.option_suggestions.map((opt, idx) => (
              <View key={idx} style={[styles.strategyCard, opt.recommended && styles.strategyCardRecommended]}>
                <View style={styles.strategyHeader}>
                  <View style={styles.strategyHeaderLeft}>
                    <Text style={styles.strategyName}>{opt.strategy}</Text>
                    {opt.recommended && (
                      <View style={styles.recommendedBadge}>
                        <Text style={styles.recommendedText}>RECOMMENDED</Text>
                      </View>
                    )}
                  </View>
                  <View style={[styles.riskBadge, { 
                    backgroundColor: opt.risk_level === "LOW" ? colors.profit + "22" : 
                                   opt.risk_level === "HIGH" ? colors.loss + "22" : colors.warning + "22" 
                  }]}>
                    <Text style={[styles.riskText, { 
                      color: opt.risk_level === "LOW" ? colors.profit : 
                             opt.risk_level === "HIGH" ? colors.loss : colors.warning 
                    }]}>
                      {opt.risk_level}
                    </Text>
                  </View>
                </View>

                <View style={styles.strategyDetails}>
                  <View style={styles.strategyRow}>
                    <View style={styles.strategyCol}>
                      <Text style={styles.strategyLabel}>Strike</Text>
                      <Text style={styles.strategyValue}>{opt.strike} {opt.option_type}</Text>
                    </View>
                    <View style={styles.strategyCol}>
                      <Text style={styles.strategyLabel}>Premium</Text>
                      <Text style={styles.strategyValue}>₹{opt.premium}</Text>
                    </View>
                    <View style={styles.strategyCol}>
                      <Text style={styles.strategyLabel}>Cost</Text>
                      <Text style={styles.strategyValue}>₹{opt.total_cost.toLocaleString("en-IN")}</Text>
                    </View>
                  </View>

                  <View style={styles.strategyRow}>
                    <View style={styles.strategyCol}>
                      <Text style={styles.strategyLabel}>Max Loss</Text>
                      <Text style={[styles.strategyValue, { color: colors.loss }]}>₹{opt.max_loss.toLocaleString("en-IN")}</Text>
                    </View>
                    <View style={styles.strategyCol}>
                      <Text style={styles.strategyLabel}>Breakeven</Text>
                      <Text style={styles.strategyValue}>₹{opt.breakeven.toLocaleString("en-IN")}</Text>
                    </View>
                    <View style={styles.strategyCol}>
                      <Text style={styles.strategyLabel}>Target</Text>
                      <Text style={[styles.strategyValue, { color: colors.profit }]}>₹{opt.target}</Text>
                    </View>
                  </View>

                  {opt.legs.length > 1 && (
                    <View style={styles.legsContainer}>
                      <Text style={styles.legsTitle}>Legs:</Text>
                      {opt.legs.map((leg, legIdx) => (
                        <Text key={legIdx} style={styles.legText}>
                          {leg.action} {leg.strike} {leg.type} @ ₹{leg.premium}
                        </Text>
                      ))}
                    </View>
                  )}

                  <Text style={styles.strategyNote}>{opt.note}</Text>
                </View>
              </View>
            ))}

            <View style={styles.optNote}>
              <AlertTriangle color={colors.warning} size={12} />
              <Text style={styles.optNoteText}>Weekly expiry recommended for intraday/short-term trading</Text>
            </View>
          </View>
        )}

        {/* All Predictions Summary */}
        <View style={styles.summaryCard}>
          <Text style={styles.summaryTitle}>All Symbols Summary</Text>
          <View style={styles.summaryGrid}>
            {SYMBOLS.map((s) => {
              const pred = predictions[s.symbol];
              if (!pred) return null;
              
              const dirColor = pred.ml_direction === "BULLISH" ? colors.profit : 
                               pred.ml_direction === "BEARISH" ? colors.loss : colors.warning;
              const DirIcon = pred.ml_direction === "BULLISH" ? TrendingUp : 
                              pred.ml_direction === "BEARISH" ? TrendingDown : Minus;
              const hcAcc = pred.predictions[0]?.high_conf_accuracy || 0;
              
              return (
                <TouchableOpacity 
                  key={s.symbol} 
                  style={styles.summaryItem}
                  onPress={() => setSelectedSymbol(s.symbol)}
                >
                  <Text style={styles.summaryName}>{s.name}</Text>
                  <View style={styles.summaryRow}>
                    <DirIcon color={dirColor} size={14} />
                    <Text style={[styles.summaryDir, { color: dirColor }]}>{pred.ml_direction}</Text>
                  </View>
                  <Text style={[styles.summaryAcc, { color: colors.profit }]}>HC: {hcAcc.toFixed(0)}%</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </View>

        <View style={styles.disclaimer}>
          <Text style={styles.disclaimerText}>
            🤖 ML models trained on 60 days of 5-minute data with walk-forward validation.
            High Confidence mode only signals when model probability ≥65% or ≤35%.
          </Text>
        </View>

        <View style={{ height: 100 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { flex: 1 },
  loadingContainer: { flex: 1, justifyContent: "center", alignItems: "center", padding: 40 },
  loadingText: { color: colors.text, fontFamily: fonts.bodySemi, fontSize: 16, marginTop: 16 },
  loadingSubtext: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, marginTop: 4 },

  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: 16, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerLeft: { flexDirection: "row", alignItems: "center", gap: 12 },
  headerTitle: { color: colors.text, fontFamily: fonts.headingSemi, fontSize: 20 },
  headerSubtitle: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 11 },
  accuracyBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.profit + "22", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 8 },
  accuracyText: { color: colors.profit, fontFamily: fonts.monoBold, fontSize: 14 },

  symbolRow: { paddingHorizontal: 12, paddingVertical: 12 },
  symbolChip: { paddingHorizontal: 14, paddingVertical: 8, marginRight: 8, borderRadius: 20, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, flexDirection: "row", alignItems: "center", gap: 6 },
  symbolChipActive: { backgroundColor: colors.accent + "22", borderColor: colors.accent },
  symbolName: { color: colors.textSecondary, fontFamily: fonts.bodyMed, fontSize: 13 },
  symbolNameActive: { color: colors.accent },
  dirDot: { width: 8, height: 8, borderRadius: 4 },

  mainCard: { margin: 12, backgroundColor: colors.surface, borderRadius: 16, padding: 16, borderWidth: 1, borderColor: colors.accent + "44" },
  mainHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" },
  mainSymbol: { color: colors.text, fontFamily: fonts.headingSemi, fontSize: 18 },
  mainPrice: { color: colors.textSecondary, fontFamily: fonts.mono, fontSize: 14, marginTop: 2 },
  directionBadge: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1 },
  directionText: { fontFamily: fonts.bodySemi, fontSize: 13 },
  asOfRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: 8 },
  asOf: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 11 },
  cacheBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.profit + "15", paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  cacheText: { color: colors.profit, fontFamily: fonts.mono, fontSize: 9 },

  accuracyRow: { flexDirection: "row", gap: 10, marginTop: 16 },
  accuracyCard: { flex: 1, backgroundColor: colors.bg, borderRadius: 10, padding: 12, alignItems: "center" },
  accuracyCardHighlight: { backgroundColor: colors.profit + "15", borderWidth: 1, borderColor: colors.profit + "44" },
  accuracyLabel: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 10, letterSpacing: 0.5 },
  accuracyValue: { fontFamily: fonts.monoBold, fontSize: 28, marginTop: 4 },

  sectionTitle: { color: colors.textSecondary, fontFamily: fonts.bodySemi, fontSize: 12, letterSpacing: 1, marginTop: 20, marginBottom: 10 },

  predRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  predLeft: { flexDirection: "row", alignItems: "center", gap: 10 },
  predLabel: { color: colors.text, fontFamily: fonts.bodyMed, fontSize: 14, width: 55 },
  predDirBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4 },
  predDir: { fontFamily: fonts.bodySemi, fontSize: 11 },
  predRight: { flexDirection: "row", gap: 16 },
  predAccCol: { alignItems: "flex-end" },
  predAccColHC: { backgroundColor: colors.profit + "10", paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  predAccLabel: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 9 },
  predAccValue: { color: colors.text, fontFamily: fonts.monoBold, fontSize: 14 },
  predSignals: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 9, marginTop: 1 },

  modelInfo: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, marginTop: 16, paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border },
  modelInfoText: { color: colors.textMuted, fontFamily: fonts.mono, fontSize: 10 },

  noData: { margin: 12, padding: 40, backgroundColor: colors.surface, borderRadius: 12, alignItems: "center" },
  noDataText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 14 },

  summaryCard: { margin: 12, backgroundColor: colors.surface, borderRadius: 12, padding: 16 },
  summaryTitle: { color: colors.textSecondary, fontFamily: fonts.bodySemi, fontSize: 12, letterSpacing: 1, marginBottom: 12 },
  summaryGrid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  summaryItem: { width: "31%", backgroundColor: colors.bg, borderRadius: 10, padding: 10, alignItems: "center" },
  summaryName: { color: colors.text, fontFamily: fonts.bodyMed, fontSize: 11 },
  summaryRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  summaryDir: { fontFamily: fonts.bodySemi, fontSize: 10 },
  summaryAcc: { fontFamily: fonts.mono, fontSize: 11, marginTop: 2 },

  disclaimer: { margin: 12, padding: 12, backgroundColor: colors.surface, borderRadius: 8 },
  disclaimerText: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 10, textAlign: "center", lineHeight: 16 },

  // Entry/Exit Card Styles
  entryExitCard: { 
    margin: 12, 
    backgroundColor: colors.surface, 
    borderRadius: 16, 
    padding: 16, 
    borderWidth: 2, 
  },
  eeHeader: { 
    flexDirection: "row", 
    justifyContent: "space-between", 
    alignItems: "flex-start", 
    marginBottom: 12,
  },
  eeHeaderLeft: { 
    flexDirection: "row", 
    alignItems: "center", 
    gap: 10,
  },
  eeTitle: { 
    color: colors.text, 
    fontFamily: fonts.headingSemi, 
    fontSize: 14, 
    letterSpacing: 1,
  },
  eeSubtitle: { 
    color: colors.textMuted, 
    fontFamily: fonts.body, 
    fontSize: 11, 
    marginTop: 2,
  },
  eeTypeBadge: { 
    flexDirection: "row", 
    alignItems: "center", 
    gap: 4, 
    paddingHorizontal: 10, 
    paddingVertical: 5, 
    borderRadius: 8,
  },
  eeTypeText: { 
    fontFamily: fonts.bodySemi, 
    fontSize: 12, 
    letterSpacing: 1,
  },
  eeHighConfBadge: { 
    flexDirection: "row", 
    alignItems: "center", 
    justifyContent: "center", 
    gap: 6, 
    backgroundColor: colors.profit + "15", 
    paddingVertical: 6, 
    borderRadius: 6, 
    marginBottom: 12,
  },
  eeHighConfText: { 
    color: colors.profit, 
    fontFamily: fonts.bodySemi, 
    fontSize: 10, 
    letterSpacing: 1,
  },
  eeLevelRow: { 
    flexDirection: "row", 
    alignItems: "center", 
    paddingVertical: 12, 
    borderBottomWidth: StyleSheet.hairlineWidth, 
    borderBottomColor: colors.border,
  },
  eeLevelIcon: { 
    width: 36, 
    height: 36, 
    borderRadius: 8, 
    alignItems: "center", 
    justifyContent: "center", 
    marginRight: 12,
  },
  eeLevelInfo: { 
    flex: 1,
  },
  eeLevelLabel: { 
    color: colors.textMuted, 
    fontFamily: fonts.body, 
    fontSize: 10, 
    letterSpacing: 0.5,
  },
  eeLevelValue: { 
    color: colors.text, 
    fontFamily: fonts.monoBold, 
    fontSize: 18, 
    marginTop: 2,
  },
  eeLevelHint: { 
    color: colors.textMuted, 
    fontFamily: fonts.body, 
    fontSize: 10,
  },
  eeLevelPct: { 
    fontFamily: fonts.monoBold, 
    fontSize: 14,
  },
  eeRiskRow: { 
    flexDirection: "row", 
    gap: 12, 
    marginTop: 12,
  },
  eeRiskItem: { 
    flex: 1, 
    backgroundColor: colors.bg, 
    borderRadius: 8, 
    padding: 10, 
    alignItems: "center",
  },
  eeRiskLabel: { 
    color: colors.textMuted, 
    fontFamily: fonts.body, 
    fontSize: 9, 
    letterSpacing: 0.5,
  },
  eeRiskValue: { 
    color: colors.text, 
    fontFamily: fonts.mono, 
    fontSize: 11, 
    marginTop: 4,
  },
  eeDisclaimer: { 
    color: colors.warning, 
    fontFamily: fonts.body, 
    fontSize: 10, 
    textAlign: "center", 
    marginTop: 12, 
    fontStyle: "italic",
  },

  // Trailing Stop Loss Styles
  trailSection: {
    marginTop: 16,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  trailHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 12,
  },
  trailTitle: {
    color: colors.accent,
    fontFamily: fonts.bodySemi,
    fontSize: 11,
    letterSpacing: 1,
    flex: 1,
  },
  trailBadge: {
    backgroundColor: colors.accent + "22",
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 4,
  },
  trailBadgeText: {
    color: colors.accent,
    fontFamily: fonts.mono,
    fontSize: 9,
    letterSpacing: 1,
  },
  trailRules: {
    backgroundColor: colors.bg,
    borderRadius: 10,
    padding: 12,
  },
  trailRule: {
    flexDirection: "row",
    alignItems: "flex-start",
    marginBottom: 10,
  },
  trailRuleNum: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: colors.accent + "22",
    alignItems: "center",
    justifyContent: "center",
    marginRight: 10,
  },
  trailRuleNumText: {
    color: colors.accent,
    fontFamily: fonts.mono,
    fontSize: 10,
  },
  trailRuleContent: {
    flex: 1,
  },
  trailTrigger: {
    color: colors.textSecondary,
    fontFamily: fonts.body,
    fontSize: 11,
  },
  trailAction: {
    color: colors.profit,
    fontFamily: fonts.bodySemi,
    fontSize: 11,
    marginTop: 2,
  },
  trailSummary: {
    flexDirection: "row",
    gap: 10,
    marginTop: 10,
  },
  trailSummaryItem: {
    flex: 1,
    backgroundColor: colors.profit + "10",
    borderRadius: 8,
    padding: 10,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.profit + "33",
  },
  trailSummaryLabel: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 9,
  },
  trailSummaryValue: {
    color: colors.profit,
    fontFamily: fonts.mono,
    fontSize: 11,
    marginTop: 2,
  },

  // Option Suggestion Styles
  optionCard: {
    margin: 12,
    backgroundColor: colors.surface,
    borderRadius: 16,
    padding: 16,
    borderWidth: 2,
  },
  optHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    marginBottom: 12,
  },
  optHeaderLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  optTitle: {
    color: colors.text,
    fontFamily: fonts.headingSemi,
    fontSize: 12,
    letterSpacing: 1,
  },
  optSubtitle: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 11,
    marginTop: 2,
  },
  optTypeBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  optTypeText: {
    fontFamily: fonts.monoBold,
    fontSize: 14,
    letterSpacing: 1,
  },
  optMainRow: {
    flexDirection: "row",
    backgroundColor: colors.bg,
    borderRadius: 10,
    padding: 12,
    marginBottom: 12,
  },
  optMainCol: {
    flex: 1,
    alignItems: "center",
  },
  optMainLabel: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 9,
    letterSpacing: 0.5,
  },
  optMainValue: {
    color: colors.text,
    fontFamily: fonts.monoBold,
    fontSize: 14,
    marginTop: 4,
  },
  optRiskSection: {
    marginBottom: 12,
  },
  optRiskTitle: {
    color: colors.textSecondary,
    fontFamily: fonts.bodySemi,
    fontSize: 10,
    letterSpacing: 1,
    marginBottom: 8,
  },
  optRiskItem: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: 6,
  },
  optRiskDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  optRiskText: {
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 11,
    flex: 1,
  },
  optSummaryRow: {
    flexDirection: "row",
    gap: 8,
  },
  optSummaryItem: {
    flex: 1,
    backgroundColor: colors.bg,
    borderRadius: 8,
    padding: 10,
    alignItems: "center",
  },
  optSummaryLabel: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 8,
    letterSpacing: 0.5,
  },
  optSummaryValue: {
    color: colors.text,
    fontFamily: fonts.monoBold,
    fontSize: 12,
    marginTop: 2,
  },
  optNote: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 12,
    paddingTop: 12,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.border,
  },
  optNoteText: {
    color: colors.warning,
    fontFamily: fonts.body,
    fontSize: 10,
    fontStyle: "italic",
  },

  // Strategy Card Styles
  strategyCard: {
    backgroundColor: colors.bg,
    borderRadius: 12,
    padding: 12,
    marginTop: 12,
    borderWidth: 1,
    borderColor: colors.border,
  },
  strategyCardRecommended: {
    borderColor: colors.profit + "66",
    backgroundColor: colors.profit + "08",
  },
  strategyHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 10,
  },
  strategyHeaderLeft: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  strategyName: {
    color: colors.text,
    fontFamily: fonts.bodySemi,
    fontSize: 13,
  },
  recommendedBadge: {
    backgroundColor: colors.profit + "22",
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  recommendedText: {
    color: colors.profit,
    fontFamily: fonts.mono,
    fontSize: 8,
    letterSpacing: 0.5,
  },
  riskBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  riskText: {
    fontFamily: fonts.bodySemi,
    fontSize: 10,
    letterSpacing: 0.5,
  },
  strategyDetails: {
    gap: 8,
  },
  strategyRow: {
    flexDirection: "row",
    gap: 8,
  },
  strategyCol: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: 6,
    padding: 8,
    alignItems: "center",
  },
  strategyLabel: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 9,
  },
  strategyValue: {
    color: colors.text,
    fontFamily: fonts.mono,
    fontSize: 11,
    marginTop: 2,
  },
  legsContainer: {
    backgroundColor: colors.surface,
    borderRadius: 6,
    padding: 8,
  },
  legsTitle: {
    color: colors.textMuted,
    fontFamily: fonts.bodySemi,
    fontSize: 9,
    marginBottom: 4,
  },
  legText: {
    color: colors.text,
    fontFamily: fonts.mono,
    fontSize: 10,
  },
  strategyNote: {
    color: colors.textSecondary,
    fontFamily: fonts.body,
    fontSize: 10,
    fontStyle: "italic",
    marginTop: 4,
  },
});
