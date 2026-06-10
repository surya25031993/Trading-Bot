---
title: AlgoBot India
emoji: 📈
colorFrom: green
colorTo: red
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: ML + algo trading bot for Indian markets — NSE/BSE, Fyers live
---

# AlgoBot India

ML & rule-based trading prediction app for Indian equities and indices (NIFTY 50, SENSEX, BANK NIFTY).

## Features
- Live market data (yfinance + Fyers when connected)
- ML Predictions (XGBoost + RandomForest + GradientBoosting ensemble)
- Options Trade Setup with real-time Fyers option chain
- Algo Signals on 50+ stocks
- Paper trading + live Fyers trading
- Auto-Trade Bot + per-signal Signal Bot
- Portfolio (LIVE Fyers + Paper)

## Required environment variables (Space → Settings → Variables and secrets)
- `MONGO_URL` — MongoDB Atlas connection string
- `DB_NAME` — `algo_ml_app`
- `EMERGENT_LLM_KEY` — your Emergent LLM key
- `CORS_ORIGINS` — `*`
- `FYERS_APP_ID` — your Fyers API App ID (must end in `-200` for live trading)
- `FYERS_SECRET_KEY` — your Fyers API secret
- `FYERS_REDIRECT_URL` — `https://<your-username>-algobot-india.hf.space/api/fyers/callback`

## Public URL pattern
After deploy, your Space lives at:
```
https://<your-username>-algobot-india.hf.space
```
