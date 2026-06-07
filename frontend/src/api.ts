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
};
