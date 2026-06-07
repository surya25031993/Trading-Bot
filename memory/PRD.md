# Algo Trading Bot — PRD

## Overview
Mobile-first algo trading bot for Indian stock market (NSE/BSE). Paper trading + multi-algorithm signals + AI analysis. Built fully on-phone deployable (Emergent Publish), no laptop required.

## Stack
- **Backend**: FastAPI + MongoDB
- **Data**: yfinance (free Yahoo Finance — supports NSE `.NS` and BSE `.BO` symbols, no API key)
- **AI**: Claude Sonnet 4.6 via Emergent LLM key (streaming SSE)
- **Frontend**: Expo Router + React Native (Android/iOS/Web)
- **Theme**: Dark "Performance Pro" trading theme (Outfit / IBM Plex Sans / JetBrains Mono)

## Features (Shipped)
- **Market tab** — live NIFTY 50, SENSEX, BANK NIFTY indices + 20 popular stocks (Reliance, TCS, HDFC, Infy, etc.)
- **Signals tab** — scans all stocks, ranks BUY/SELL/HOLD using 5 algorithms (SMA 20/50 crossover, EMA 12/26 crossover, RSI 14, MACD, Bollinger Bands). Filter chips ALL/BUY/SELL/HOLD.
- **Options tab** — NIFTY / SENSEX / BANKNIFTY index switcher. Auto-recommends an option strategy (Long Call, Long Put, Bull/Bear Spread, Iron Condor, Long Straddle, Short Strangle) based on the index's technical view. Shows concrete legs with ATM/OTM strikes, Black-Scholes premium estimates, Greeks (Δ Γ Θ V), payoff diagram with breakevens, Max Profit/Loss and Probability of Profit %.
- **Watchlist tab** — add/remove tracked stocks with live quotes; search modal
- **Portfolio tab** — paper portfolio starting at ₹10,00,000; cash, invested, current value, holdings with P&L %, reset button
- **History tab** — full trade history (BUY/SELL tag, qty, price, timestamp)
- **Stock detail screen** — 60-day price chart (SVG), all 5 algo signals with reasoning, indicator grid (RSI/MACD/SMA/BB), BUY/SELL action buttons with quantity modal, **AI Analysis** ("Run" button streams Claude's technical view)

## API Endpoints
- Stocks: `GET /api/market/indices` · `/stocks/popular` · `/stocks/search` · `/stocks/{symbol}` · `/stocks/{symbol}/signals` · `/signals/top`
- Watchlist: `GET/POST/DELETE /api/watchlist`
- Trades: `POST /api/trades/paper` · `GET /api/trades`
- Portfolio: `GET /api/portfolio` · `POST /api/portfolio/reset`
- AI: `POST /api/ai/analyze` (streams text)
- **Options: `GET /api/options/strategies` · `/options/suggest?index=` · `POST /api/options/calculate` · `GET /api/options/chain?index=` (best-effort NSE)**

## Important Notes
- All trades are PAPER (simulated). No real broker connected — no broker API key was provided.
- Yahoo Finance data is typically delayed 15 minutes during market hours; some symbols (rarely) return "Data unavailable" — backend degrades gracefully.
- "Profit" is never guaranteed. The app surfaces signals; user decides.

## Future Hooks
- Plug in Zerodha Kite / Upstox / Angel One Smart API for real orders (only needs auth + 1 endpoint swap in `place_paper_trade`).
- Add price alerts and scheduled scans.
- Add candlestick charts and intraday intervals.
