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
