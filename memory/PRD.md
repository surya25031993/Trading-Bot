# Algo & ML Trading Prediction App — PRD

## Original problem statement
"Fix my repo ui is not working properly" — algo + ML-based prediction app (Indian markets: NSE/BSE). Frontend (Expo Web) was failing to start and backend was crashing on import, leaving the UI unusable.

## Architecture
- Frontend: Expo (React Native Web) + expo-router, served as a static web export on port 3000 (`serve dist --single`).
- Backend: FastAPI (uvicorn) on port 8001, MongoDB (motor), yfinance, scikit-learn, xgboost, fyers-apiv3, emergentintegrations.
- DB: MongoDB local.

## What was broken & fixed (2026-06-09)
1. **Frontend crash loop (ENOSPC: too many file watchers).** Metro's FallbackWatcher exhausted `fs.inotify.max_user_watches` (12288, cannot be raised in the container). Watchman also fails for the same reason.
   - Fix: switched `yarn start` to serve a prebuilt static export — `expo export --platform web` → `serve dist -l tcp://0.0.0.0:3000 --single`. Added `dev` and `build:web` scripts.
2. **Backend startup ModuleNotFoundError chain.** Missing deps for yfinance, sklearn, fyers-apiv3.
   - Installed: `pytz multitasking peewee beautifulsoup4 frozendict curl_cffi scipy joblib threadpoolctl narwhals aws_lambda_powertools`.
3. **Backend missing `/app/backend/.env`.** `KeyError: 'MONGO_URL'`, `EMERGENT_LLM_KEY`.
   - Created `.env` with `MONGO_URL`, `DB_NAME=algo_ml_app`, `EMERGENT_LLM_KEY`, `CORS_ORIGINS=*`.
4. **Frontend `EXPO_PUBLIC_BACKEND_URL` undefined** → all API calls hit `undefined/api/...`.
   - Created `/app/frontend/.env` and rebuilt with cleared metro cache; URL now baked into the bundle.
5. **`/api/stocks/popular` → 500 "Out of range float values are not JSON compliant"** (yfinance returning a half-formed NaN row for the current trading day).
   - `fetch_quote()` now `hist.dropna(subset=["Close"])` before reading the last close.

## How to develop (important note for future iterations)
Hot reload (`expo start`) cannot run in this container because of the inotify limit.
- After ANY change in `/app/frontend/app/**` or `/app/frontend/src/**`, run:
  ```
  cd /app/frontend && yarn build:web && sudo supervisorctl restart frontend
  ```
- Backend has uvicorn `--reload` so backend changes apply automatically.

## What's working
- Markets dashboard (Indian Markets header, NIFTY 50 / SENSEX / BANK NIFTY indices, Popular Stocks list with live prices, change %, volume).
- Bottom tab navigation: Market, ML Predict, Signals, Options, Watchlist, Portfolio, Bot.
- Backend `/api/`, `/api/market/indices`, `/api/stocks/popular`, `/api/stocks/{symbol}` returning data.

## Backlog / Next actions
- P1: Verify each tab (ML Predict, Signals, Options, Watchlist, Portfolio, Bot) end-to-end via testing agent.
- P1: Add a dev-mode option (e.g., `expo export --dev` watch-rebuild loop) so iteration doesn't require manual rebuilds.
- P2: Pin requirements.txt to the actually-installed transitive deps (pytz, scipy, joblib, threadpoolctl, narwhals, multitasking, peewee, beautifulsoup4, frozendict, curl_cffi, aws_lambda_powertools) so the env is reproducible.
- P2: Harden `fetch_quote`/other yfinance callers against NaN across all downstream endpoints (signals, history, ML predict).
