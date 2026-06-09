#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================

user_problem_statement: |
  "This is a trading algo bot. New python code added for quant algorithm — verify it's implemented and fix real-time data not loading."

backend:
  - task: "Quant indicators (Supertrend, ADX, Stochastic) in compute_indicators"
    implemented: true
    working: true
    file: "backend/server.py"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Verified: 8 signals now returned (SMA, EMA, RSI, MACD, BB, Supertrend(10,3), ADX(14), Stochastic). Endpoint /api/stocks/TCS.NS/signals returns supertrend, supertrend_uptrend, adx, stoch_k, stoch_d fields and matching signals with reason strings."

  - task: "Real-time data loading"
    implemented: true
    working: true
    file: "backend/requirements.txt, backend/.env"
    stuck_count: 0
    priority: "high"
    needs_retesting: false
    status_history:
      - working: false
        agent: "user"
        comment: "User reported data not loading in real time."
      - working: true
        agent: "main"
        comment: "Root cause: backend was crashing on startup. Fixed (a) requirements.txt had `emergentintegrations==0.2.0yfinance>=1.4.1` merged without newline — split into separate lines; (b) yfinance, scipy, fyers-apiv3 not installed — pip installed; (c) /app/backend/.env and /app/frontend/.env files missing — recreated with MONGO_URL, DB_NAME, EMERGENT_LLM_KEY, EXPO_PUBLIC_BACKEND_URL. Backend healthy, /api/market/indices and /api/stocks/{sym}/signals returning live yfinance data (NIFTY 23242, SENSEX 73918, BANK NIFTY 55194)."

  - task: "Bot service reason text updated for 8-indicator quant suite"
    implemented: true
    working: true
    file: "backend/bot_service.py"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: true
        agent: "main"
        comment: "Updated reason strings from '/5' to '/8' since Supertrend, ADX, Stochastic added. Mentions quant algos in decisions log."

frontend:
  - task: "Stock detail screen surfaces new quant indicators"
    implemented: true
    working: "NA"
    file: "frontend/app/stock/[symbol].tsx, frontend/src/api.ts"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Extended IndicatorData type with supertrend, supertrend_uptrend, adx, stoch_k, stoch_d. Indicator grid in stock detail now shows SUPERTREND ↑/↓, ADX(14) and STOCH %K cells when backend returns them."

  - task: "Auto-refresh polling for real-time feel"
    implemented: true
    working: "NA"
    file: "frontend/app/(tabs)/index.tsx, signals.tsx, watchlist.tsx"
    stuck_count: 0
    priority: "medium"
    needs_retesting: false
    status_history:
      - working: "NA"
        agent: "main"
        comment: "Added setInterval polling — Market 30s, Signals 60s, Watchlist 30s. Quote cache TTL stays 30s server side."

metadata:
  created_by: "main_agent"
  version: "1.1"
  test_sequence: 1
  run_ui: false

test_plan:
  current_focus:
    - "Quant indicators (Supertrend, ADX, Stochastic) in compute_indicators"
    - "Real-time data loading"
  stuck_tasks: []
  test_all: false
  test_priority: "high_first"

agent_communication:
  - agent: "main"
    message: |
      Fixed root cause of dead backend. requirements.txt had two packages merged on one line preventing yfinance from installing; .env files were missing. Installed yfinance, scipy, fyers-apiv3, recreated .env. Backend healthy. Confirmed all 8 quant signals returned by /api/stocks/{sym}/signals (incl. Supertrend, ADX, Stochastic). Frontend now exposes new indicators on stock detail and auto-polls every 30-60s.
  - agent: "main"
    message: |
      Added Intraday 5/10/15/30-min Prediction with Walk-Forward Backtest. New backend endpoint /api/stocks/{symbol}/intraday-forecast fetches 60-day 5-min candles, computes vectorized 8-indicator series (no look-ahead), and returns:
      (a) Live predictions for next 1/2/3/6 bars (5/10/15/30 min) with target, 1σ range, P(UP) and direction;
      (b) Walk-forward backtest over last ~250 bars producing per-horizon directional accuracy, long/short accuracy, within-1σ hit rate and MAE;
      (c) Overall ensemble accuracy across all horizons.
      New IntradayPredictionCard component renders timeframe tabs (5/10/15/30 min), live target+P(UP)+range, backtest accuracy with progress bars, mini-stats row (long/short/MAE/vol), and overall accuracy banner. Wired into Options tab and stock detail. Verified on NIFTY 5-min — 244 bars (~3.3 days), 193 signals, 44.6% direction accuracy, 86.9% in-range hits, MAE 0.06%, overall 42.4%.