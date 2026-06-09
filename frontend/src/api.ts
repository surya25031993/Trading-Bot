import { API } from "./theme";

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...opts,
    headers: { "Content-Type": "application/json", ...(opts?.headers || {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.json();
}

export type Quote = {
  symbol: string;
  name?: string;
  price: number;
  change: number;
  change_pct: number;
  volume: number;
  day_high: number;
  day_low: number;
};

export type Signal = { name: string; action: "BUY" | "SELL" | "HOLD"; reason: string };
export type IndicatorData = {
  indicators: {
    rsi: number; macd: number; macd_signal: number; macd_hist: number;
    sma20: number; sma50: number; bb_upper: number; bb_lower: number; price: number;
    supertrend?: number; supertrend_uptrend?: boolean;
    adx?: number; stoch_k?: number; stoch_d?: number;
  };
  signals: Signal[];
  consensus: "BUY" | "SELL" | "HOLD";
  buy_count: number; sell_count: number; hold_count: number;
};

export type Position = {
  symbol: string; name: string; quantity: number; avg_price: number;
  current_price: number; invested: number; current_value: number; pnl: number; pnl_pct: number;
};

export type Portfolio = {
  cash: number; starting_cash: number; invested: number; current_value: number;
  total_pnl: number; total_pnl_pct: number; net_worth: number;
  overall_pnl: number; overall_pnl_pct: number;
  positions: Position[];
};

export type Prediction = {
  symbol: string;
  current_price: number;
  direction: "BULLISH" | "BEARISH" | "NEUTRAL";
  confidence_pct: number;
  bull_count: number;
  bear_count: number;
  neutral_count: number;
  net_score: number;
  atr_pct: number;
  volatility_pct: number;
  predictions: {
    horizon: string;
    days: number;
    target: number;
    low: number;
    high: number;
    prob_up: number;
    expected_change_pct: number;
  }[];
  key_drivers: { name: string; reason: string }[];
  risk_factors: { name: string; reason: string }[];
  recommendation: string;
  recommendation_color: "profit" | "loss" | "warning" | "neutral";
  narrative: string;
};

export type IntradayForecast = {
  symbol: string;
  interval: string;
  current_price: number;
  as_of: string;
  direction: "BULLISH" | "BEARISH" | "NEUTRAL";
  confidence_pct: number;
  bull_count: number;
  bear_count: number;
  net_score: number;
  volatility_5m_pct: number;
  atr_pct: number;
  predictions: {
    label: string;
    bars: number;
    target: number;
    low: number;
    high: number;
    prob_up: number;
    expected_change_pct: number;
    predicted_direction: "UP" | "DOWN" | "FLAT";
  }[];
  backtest: {
    label: string;
    bars: number;
    total_signals: number;
    directional_accuracy_pct: number;
    long_accuracy_pct: number;
    short_accuracy_pct: number;
    within_1sigma_band_pct: number;
    mae_pct: number;
    samples: number;
  }[];
  overall_accuracy_pct: number;
  backtest_window_bars: number;
  backtest_window_days_approx: number;
};

export type Trade = {
  id: string; symbol: string; name: string; side: "BUY" | "SELL";
  quantity: number; price: number; total: number; timestamp: string;
};

export const api = {
  indices: () => req<Quote[]>("/market/indices"),
  popular: () => req<Quote[]>("/stocks/popular"),
  stockDetail: (sym: string) => req<{ quote: Quote; chart: { date: string; close: number; high: number; low: number; volume: number }[] }>(`/stocks/${encodeURIComponent(sym)}`),
  stockSignals: (sym: string) => req<IndicatorData>(`/stocks/${encodeURIComponent(sym)}/signals`),
  topSignals: () => req<any[]>("/signals/top"),
  watchlist: () => req<Quote[]>("/watchlist"),
  addWatch: (symbol: string, name: string) => req("/watchlist", { method: "POST", body: JSON.stringify({ symbol, name }) }),
  removeWatch: (symbol: string) => req(`/watchlist/${encodeURIComponent(symbol)}`, { method: "DELETE" }),
  portfolio: () => req<Portfolio>("/portfolio"),
  trades: () => req<Trade[]>("/trades"),
  paperTrade: (body: { symbol: string; name: string; side: "BUY" | "SELL"; quantity: number; price: number }) =>
    req<{ ok: boolean; trade: Trade; cash_remaining: number }>("/trades/paper", { method: "POST", body: JSON.stringify(body) }),
  resetPortfolio: () => req("/portfolio/reset", { method: "POST" }),
  aiAnalyzeUrl: (sym: string) => `${API}/ai/analyze`,

  // ============ Fyers ============
  fyersStatus: () => req<{ configured: boolean; connected: boolean; access_expires_at?: string; needs_relogin?: boolean }>("/fyers/status"),
  fyersLoginUrl: () => req<{ login_url: string }>("/fyers/login-url"),
  fyersDisconnect: () => req("/fyers/disconnect", { method: "POST" }),
  fyersFunds: () => req<any>("/fyers/funds"),
  fyersHoldings: () => req<any>("/fyers/holdings"),
  fyersPositions: () => req<any>("/fyers/positions"),
  fyersProfile: () => req<any>("/fyers/profile"),
  fyersOptionChain: (index: string) => req<any>(`/fyers/option-chain?index=${index}`),

  // ============ Options ============
  optionsSuggest: (index: string) => req<OptionSuggestion>(`/options/suggest?index=${index}`),
  optionsStrategies: () => req<any[]>("/options/strategies"),
  optionsCalculate: (body: OptionCalcRequest) => req<OptionCalcResult>("/options/calculate", { method: "POST", body: JSON.stringify(body) }),
  optionsChain: (index: string) => req<any>(`/options/chain?index=${index}`),
  optionsPaperTrade: (body: { index: string; legs: any[] }) => req<any>("/options/paper-trade", { method: "POST", body: JSON.stringify(body) }),
  stockChart: (sym: string) => req<any>(`/stocks/${encodeURIComponent(sym)}/chart`),
  stockPredict: (sym: string) => req<Prediction>(`/stocks/${encodeURIComponent(sym)}/predict`),
  stockIntradayForecast: (sym: string) => req<IntradayForecast>(`/stocks/${encodeURIComponent(sym)}/intraday-forecast`),
  stockMLPredict: (sym: string) => req<MLPrediction>(`/stocks/${encodeURIComponent(sym)}/ml-predict`),

  // ============ Bot ============
  botStatus: () => req<any>("/bot/status"),
  botStart: (mode: "paper" | "live") => req("/bot/start?mode=" + mode, { method: "POST" }),
  botStop: () => req("/bot/stop", { method: "POST" }),
  botConfig: () => req<any>("/bot/config"),
  botSetConfig: (updates: any) => req("/bot/config", { method: "POST", body: JSON.stringify(updates) }),
  botDecisions: (limit = 50) => req<any[]>(`/bot/decisions?limit=${limit}`),
  botClearDecisions: () => req("/bot/decisions", { method: "DELETE" }),
  botStats: () => req<any>("/bot/stats"),
};

export type OptionLeg = { side: "BUY" | "SELL"; type: "CE" | "PE"; strike: number; premium: number; qty: number };
export type OptionCalcRequest = { index: "NIFTY" | "SENSEX" | "BANKNIFTY"; spot: number; days_to_expiry: number; iv: number; legs: OptionLeg[] };
export type OptionCalcResult = {
  lot_size: number; net_premium: number;
  max_profit: number | null; max_loss: number | null;
  breakevens: number[];
  payoff: { spot: number; pnl: number }[];
  greeks: { delta: number; gamma: number; theta: number; vega: number };
  probability_of_profit_pct: number | null;
};
export type OptionSuggestion = {
  index: string; spot: number; atm: number; lot_size: number;
  consensus: "BUY" | "SELL" | "HOLD"; rsi: number; change_pct: number;
  strategy: { key: string; name: string; view: string; risk: string; reward: string; description: string };
  concrete_legs: { side: "BUY" | "SELL"; type: "CE" | "PE"; strike: number; premium_est: number; qty: number }[];
  note: string;
};

// ML Prediction types
export type MLPredictionItem = {
  label: string;
  bars: number;
  direction: "UP" | "DOWN" | "NEUTRAL" | "N/A";
  confidence: number;
  reason: string;
  model_votes: { xgb?: string; rf?: string; gb?: string };
  probabilities?: { xgb?: number; rf?: number; gb?: number };
  avg_probability?: number;
  is_high_confidence?: boolean;
  training: { samples: number; train_samples?: number; val_samples?: number; best_model: string; best_accuracy?: number };
  backtest_accuracy: number;
  high_conf_accuracy?: number;
  high_conf_signals?: number;
  model_accuracies?: { xgb?: number; rf?: number; gb?: number };
};

export type TrailingStopRule = {
  trigger: string;
  action: string;
};

export type TrailingStop = {
  enabled: boolean;
  activation_price: number;
  activation_pct: number;
  trail_distance_pct: number;
  trail_sl_at_t1: number;
  trail_sl_at_t1_note: string;
  trail_sl_at_t2: number;
  trail_sl_at_t2_note: string;
  rules: TrailingStopRule[];
};

export type MLEntryExit = {
  trade_type: "LONG" | "SHORT";
  entry_price: number;
  stop_loss: number;
  stop_loss_pct: number;
  target_1: number;
  target_1_pct: number;
  target_2: number;
  target_2_pct: number;
  risk_reward: number;
  atr: number;
  atr_pct: number;
  is_high_confidence: boolean;
  suggested_qty_pct: number;
  timeframe: string;
  trailing_stop?: TrailingStop;
};

export type OptionLegML = {
  action: string;
  type: string;
  strike: number;
  premium: number;
  qty: number;
};

export type OptionRiskManagement = {
  entry: string;
  stop_loss: string;
  target_1: string;
  target_2: string;
  max_risk: string;
};

export type OptionSuggestionML = {
  strategy_id: number;
  strategy: string;
  type: string;
  risk_level: string;
  option_type: string;
  strike: number;
  premium: number;
  lot_size: number;
  total_cost: number;
  max_loss: number;
  max_profit: number | string;
  breakeven: number;
  stop_loss: number;
  target: number;
  legs: OptionLegML[];
  note: string;
  recommended?: boolean;
};

export type MLPrediction = {
  symbol: string;
  model_type: string;
  current_price: number;
  as_of: string;
  ml_direction: "BULLISH" | "BEARISH" | "NEUTRAL";
  predictions: MLPredictionItem[];
  overall_ml_accuracy: number;
  entry_exit?: MLEntryExit;
  option_suggestions?: OptionSuggestionML[];
  note: string;
  cached?: boolean;
  cache_age_seconds?: number;
  cache_ttl_seconds?: number;
};
