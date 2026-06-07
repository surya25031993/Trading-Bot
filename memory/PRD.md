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
- **Watchlist tab** — add/remove tracked stocks with live quotes; search modal
- **Portfolio tab** — paper portfolio starting at ₹10,00,000; cash, invested, current value, holdings with P&L %, reset button
- **History tab** — full trade history (BUY/SELL tag, qty, price, timestamp)
- **Stock detail screen** — 60-day price chart (SVG), all 5 algo signals with reasoning, indicator grid (RSI/MACD/SMA/BB), BUY/SELL action buttons with quantity modal, **AI Analysis** ("Run" button streams Claude's technical view)

## API Endpoints
- `GET /api/market/indices` · `GET /api/stocks/popular` · `GET /api/stocks/search?q=`
- `GET /api/stocks/{symbol}` · `GET /api/stocks/{symbol}/signals` · `GET /api/signals/top`
- `GET/POST/DELETE /api/watchlist`
- `POST /api/trades/paper` · `GET /api/trades`
- `GET /api/portfolio` · `POST /api/portfolio/reset`
- `POST /api/ai/analyze` (streams text)

## Important Notes
- All trades are PAPER (simulated). No real broker connected — no broker API key was provided.
- Yahoo Finance data is typically delayed 15 minutes during market hours; some symbols (rarely) return "Data unavailable" — backend degrades gracefully.
- "Profit" is never guaranteed. The app surfaces signals; user decides.

## Future Hooks
- Plug in Zerodha Kite / Upstox / Angel One Smart API for real orders (only needs auth + 1 endpoint swap in `place_paper_trade`).
- Add price alerts and scheduled scans.
- Add candlestick charts and intraday intervals.
