from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import asyncio
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
import uuid
from datetime import datetime, timezone

import yfinance as yf
import pandas as pd
import numpy as np

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone

from options import (
    STRATEGIES, INDEX_SYMBOL, LOT_SIZE,
    suggest_strategy, calculate_payoff, fetch_option_chain,
    bs_price, bs_greeks, CalcRequest,
)
import fyers_integration as fyers_int
import bot_service
from fastapi.responses import HTMLResponse

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']
DEFAULT_USER = "default_user"
STARTING_CASH = 1_000_000.0  # 10 lakh paper money

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============ Popular Indian Stocks ============
POPULAR_STOCKS = [
    {"symbol": "RELIANCE.NS", "name": "Reliance Industries"},
    {"symbol": "TCS.NS", "name": "Tata Consultancy Services"},
    {"symbol": "HDFCBANK.NS", "name": "HDFC Bank"},
    {"symbol": "INFY.NS", "name": "Infosys"},
    {"symbol": "ICICIBANK.NS", "name": "ICICI Bank"},
    {"symbol": "SBIN.NS", "name": "State Bank of India"},
    {"symbol": "BHARTIARTL.NS", "name": "Bharti Airtel"},
    {"symbol": "ITC.NS", "name": "ITC Limited"},
    {"symbol": "LT.NS", "name": "Larsen & Toubro"},
    {"symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever"},
    {"symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank"},
    {"symbol": "ASIANPAINT.NS", "name": "Asian Paints"},
    {"symbol": "AXISBANK.NS", "name": "Axis Bank"},
    {"symbol": "MARUTI.NS", "name": "Maruti Suzuki"},
    {"symbol": "M&M.NS", "name": "Mahindra & Mahindra"},
    {"symbol": "WIPRO.NS", "name": "Wipro"},
    {"symbol": "BAJFINANCE.NS", "name": "Bajaj Finance"},
    {"symbol": "ADANIENT.NS", "name": "Adani Enterprises"},
    {"symbol": "TATASTEEL.NS", "name": "Tata Steel"},
    {"symbol": "SUNPHARMA.NS", "name": "Sun Pharma"},
]

INDICES = [
    {"symbol": "^NSEI", "name": "NIFTY 50"},
    {"symbol": "^BSESN", "name": "SENSEX"},
    {"symbol": "^NSEBANK", "name": "BANK NIFTY"},
]


# ============ Models ============
class WatchlistItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = DEFAULT_USER
    symbol: str
    name: str
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WatchlistAdd(BaseModel):
    symbol: str
    name: str


class PaperTradeRequest(BaseModel):
    symbol: str
    name: str
    side: Literal["BUY", "SELL"]
    quantity: int
    price: float


class PaperTrade(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = DEFAULT_USER
    symbol: str
    name: str
    side: Literal["BUY", "SELL"]
    quantity: int
    price: float
    total: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AIAnalyzeRequest(BaseModel):
    symbol: str


# ============ Helpers ============
_quote_cache: dict = {}
_cache_ttl = 30  # seconds


def _now_ts() -> float:
    return datetime.now(timezone.utc).timestamp()


def fetch_quote(symbol: str) -> dict:
    """Get latest price + 1-day change for a symbol with simple in-memory caching."""
    cached = _quote_cache.get(symbol)
    if cached and _now_ts() - cached["t"] < _cache_ttl:
        return cached["data"]
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="5d", interval="1d")
        if hist.empty:
            raise ValueError("no data")
        last = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else last
        change = last - prev
        change_pct = (change / prev * 100) if prev else 0.0
        data = {
            "symbol": symbol,
            "price": round(last, 2),
            "change": round(change, 2),
            "change_pct": round(change_pct, 2),
            "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0,
            "day_high": round(float(hist["High"].iloc[-1]), 2),
            "day_low": round(float(hist["Low"].iloc[-1]), 2),
        }
        _quote_cache[symbol] = {"t": _now_ts(), "data": data}
        return data
    except Exception as e:
        logger.warning(f"fetch_quote {symbol} failed: {e}")
        return {
            "symbol": symbol, "price": 0.0, "change": 0.0,
            "change_pct": 0.0, "volume": 0, "day_high": 0.0, "day_low": 0.0,
            "error": "Data unavailable",
        }


def fetch_history(symbol: str, period: str = "3mo", interval: str = "1d") -> pd.DataFrame:
    t = yf.Ticker(symbol)
    return t.history(period=period, interval=interval)


def compute_signal_series(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorized indicator scores per bar (for backtesting & multi-step prediction).
    Returns DataFrame with: buy_count, sell_count, net_score, atr, atr_pct per bar.
    Each bar uses only past data (no look-ahead)."""
    if df.empty or len(df) < 30:
        return pd.DataFrame()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # SMA / EMA
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    # RSI(14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # MACD
    macd = ema12 - ema26
    macd_sig = macd.ewm(span=9, adjust=False).mean()

    # Bollinger
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # ATR
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # Supertrend(10,3)
    hl2 = (high + low) / 2
    ub = hl2 + 3.0 * atr
    lb = hl2 - 3.0 * atr
    supertrend = pd.Series(index=df.index, dtype=float)
    st_up = pd.Series(index=df.index, dtype=bool)
    in_up = True
    for i in range(len(df)):
        if i == 0 or pd.isna(atr.iloc[i]):
            supertrend.iloc[i] = float(ub.iloc[i]) if not pd.isna(ub.iloc[i]) else float(close.iloc[i])
            st_up.iloc[i] = True
            continue
        prev_close = float(close.iloc[i-1])
        prev_st = float(supertrend.iloc[i-1])
        if prev_close > prev_st:
            supertrend.iloc[i] = max(float(lb.iloc[i]), prev_st)
            in_up = True
        else:
            supertrend.iloc[i] = min(float(ub.iloc[i]), prev_st)
            in_up = False
        if float(close.iloc[i]) > supertrend.iloc[i] and not in_up:
            in_up = True
            supertrend.iloc[i] = float(lb.iloc[i])
        elif float(close.iloc[i]) < supertrend.iloc[i] and in_up:
            in_up = False
            supertrend.iloc[i] = float(ub.iloc[i])
        st_up.iloc[i] = in_up

    # ADX(14)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr14 = tr.rolling(14).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(14).mean()

    # Stochastic(14,3)
    lowest_low = low.rolling(14).min()
    highest_high = high.rolling(14).max()
    stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    stoch_d = stoch_k.rolling(3).mean()

    # === Score signals per bar (boolean votes) ===
    # SMA crossover: buy if sma20 > sma50, sell if <
    sma_buy = (sma20 > sma50).astype(int)
    sma_sell = (sma20 < sma50).astype(int)
    # EMA: buy if ema12 > ema26
    ema_buy = (ema12 > ema26).astype(int)
    ema_sell = (ema12 < ema26).astype(int)
    # RSI: buy if < 30 (oversold reversal), sell if > 70
    rsi_buy = (rsi < 30).astype(int)
    rsi_sell = (rsi > 70).astype(int)
    # MACD: buy if histogram > 0 and rising, sell if < 0 and falling
    macd_hist = macd - macd_sig
    macd_buy = ((macd_hist > 0) & (macd_hist > macd_hist.shift())).astype(int)
    macd_sell = ((macd_hist < 0) & (macd_hist < macd_hist.shift())).astype(int)
    # Bollinger: buy if close < lower (oversold bounce), sell if > upper
    bb_buy = (close < bb_lower).astype(int)
    bb_sell = (close > bb_upper).astype(int)
    # Supertrend
    st_buy = st_up.astype(int)
    st_sell = (~st_up).astype(int)
    # ADX directional
    adx_buy = ((adx > 20) & (plus_di > minus_di)).astype(int)
    adx_sell = ((adx > 20) & (minus_di > plus_di)).astype(int)
    # Stochastic: buy if k crossed above d under 20; sell if crossed below over 80
    stoch_buy = ((stoch_k > stoch_d) & (stoch_k < 30)).astype(int)
    stoch_sell = ((stoch_k < stoch_d) & (stoch_k > 70)).astype(int)

    buy_count = sma_buy + ema_buy + rsi_buy + macd_buy + bb_buy + st_buy + adx_buy + stoch_buy
    sell_count = sma_sell + ema_sell + rsi_sell + macd_sell + bb_sell + st_sell + adx_sell + stoch_sell

    return pd.DataFrame({
        "close": close,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "net_score": buy_count - sell_count,
        "atr": atr,
        "atr_pct": atr / close,
    })


def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute SMA, EMA, RSI, MACD, Bollinger Bands. Returns latest values + signals."""
    if df.empty or len(df) < 30:
        return {"error": "Not enough data"}
    close = df["Close"]

    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean() if len(close) >= 50 else close.rolling(len(close)).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # MACD
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - signal

    # Bollinger
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    # === QUANT INDICATORS ===
    high = df["High"]
    low = df["Low"]

    # ATR (14) — Average True Range
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # Supertrend (10, 3) — VERY popular Indian quant indicator
    hl2 = (high + low) / 2
    multiplier = 3.0
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr
    supertrend = pd.Series(index=df.index, dtype=float)
    in_uptrend = pd.Series(index=df.index, dtype=bool)
    for i in range(len(df)):
        if i == 0:
            supertrend.iloc[i] = upper_band.iloc[i]
            in_uptrend.iloc[i] = True
            continue
        prev_close = float(close.iloc[i-1])
        prev_st = float(supertrend.iloc[i-1])
        if prev_close > prev_st:
            supertrend.iloc[i] = max(float(lower_band.iloc[i]), prev_st)
            in_uptrend.iloc[i] = True
        else:
            supertrend.iloc[i] = min(float(upper_band.iloc[i]), prev_st)
            in_uptrend.iloc[i] = False
        if float(close.iloc[i]) > supertrend.iloc[i] and not in_uptrend.iloc[i]:
            in_uptrend.iloc[i] = True
            supertrend.iloc[i] = float(lower_band.iloc[i])
        elif float(close.iloc[i]) < supertrend.iloc[i] and in_uptrend.iloc[i]:
            in_uptrend.iloc[i] = False
            supertrend.iloc[i] = float(upper_band.iloc[i])
    latest_st = float(supertrend.iloc[-1])
    st_uptrend = bool(in_uptrend.iloc[-1])

    # ADX (14) — Average Directional Index, trend strength
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr14 = tr.rolling(14).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(14).mean()
    latest_adx = float(adx.iloc[-1]) if not np.isnan(adx.iloc[-1]) else 20.0
    latest_plus_di = float(plus_di.iloc[-1]) if not np.isnan(plus_di.iloc[-1]) else 0.0
    latest_minus_di = float(minus_di.iloc[-1]) if not np.isnan(minus_di.iloc[-1]) else 0.0

    # Stochastic Oscillator (14, 3, 3) — momentum
    period = 14
    lowest_low = low.rolling(period).min()
    highest_high = high.rolling(period).max()
    pk = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    pd_line = pk.rolling(3).mean()
    latest_stoch_k = float(pk.iloc[-1]) if not np.isnan(pk.iloc[-1]) else 50.0
    latest_stoch_d = float(pd_line.iloc[-1]) if not np.isnan(pd_line.iloc[-1]) else 50.0

    latest_close = float(close.iloc[-1])
    latest_rsi = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else 50.0
    latest_macd = float(macd.iloc[-1])
    latest_signal_line = float(signal.iloc[-1])
    latest_hist = float(macd_hist.iloc[-1])
    latest_sma20 = float(sma20.iloc[-1])
    latest_sma50 = float(sma50.iloc[-1]) if not np.isnan(sma50.iloc[-1]) else latest_sma20
    latest_bb_u = float(bb_upper.iloc[-1])
    latest_bb_l = float(bb_lower.iloc[-1])

    # Generate signals
    signals = []

    # SMA Crossover (20 vs 50)
    prev_sma20 = float(sma20.iloc[-2])
    prev_sma50 = float(sma50.iloc[-2]) if not np.isnan(sma50.iloc[-2]) else prev_sma20
    if prev_sma20 <= prev_sma50 and latest_sma20 > latest_sma50:
        signals.append({"name": "SMA Crossover (20/50)", "action": "BUY", "reason": "Golden cross — short MA crossed above long MA"})
    elif prev_sma20 >= prev_sma50 and latest_sma20 < latest_sma50:
        signals.append({"name": "SMA Crossover (20/50)", "action": "SELL", "reason": "Death cross — short MA crossed below long MA"})
    else:
        trend = "BUY" if latest_sma20 > latest_sma50 else "SELL"
        signals.append({"name": "SMA Crossover (20/50)", "action": "HOLD", "reason": f"Trend: {trend} bias"})

    # EMA Crossover (12 vs 26)
    if float(ema12.iloc[-2]) <= float(ema26.iloc[-2]) and float(ema12.iloc[-1]) > float(ema26.iloc[-1]):
        signals.append({"name": "EMA Crossover (12/26)", "action": "BUY", "reason": "EMA12 crossed above EMA26"})
    elif float(ema12.iloc[-2]) >= float(ema26.iloc[-2]) and float(ema12.iloc[-1]) < float(ema26.iloc[-1]):
        signals.append({"name": "EMA Crossover (12/26)", "action": "SELL", "reason": "EMA12 crossed below EMA26"})
    else:
        signals.append({"name": "EMA Crossover (12/26)", "action": "HOLD", "reason": "No crossover"})

    # RSI
    if latest_rsi < 30:
        signals.append({"name": "RSI (14)", "action": "BUY", "reason": f"Oversold at {latest_rsi:.1f}"})
    elif latest_rsi > 70:
        signals.append({"name": "RSI (14)", "action": "SELL", "reason": f"Overbought at {latest_rsi:.1f}"})
    else:
        signals.append({"name": "RSI (14)", "action": "HOLD", "reason": f"Neutral at {latest_rsi:.1f}"})

    # MACD
    prev_hist = float(macd_hist.iloc[-2])
    if prev_hist <= 0 and latest_hist > 0:
        signals.append({"name": "MACD", "action": "BUY", "reason": "MACD histogram turned positive"})
    elif prev_hist >= 0 and latest_hist < 0:
        signals.append({"name": "MACD", "action": "SELL", "reason": "MACD histogram turned negative"})
    else:
        signals.append({"name": "MACD", "action": "HOLD", "reason": "No fresh signal"})

    # Bollinger Bands
    if latest_close <= latest_bb_l:
        signals.append({"name": "Bollinger Bands", "action": "BUY", "reason": "Price at/below lower band"})
    elif latest_close >= latest_bb_u:
        signals.append({"name": "Bollinger Bands", "action": "SELL", "reason": "Price at/above upper band"})
    else:
        signals.append({"name": "Bollinger Bands", "action": "HOLD", "reason": "Price within bands"})

    # Supertrend (QUANT) — primary trend follower in Indian markets
    prev_uptrend = bool(in_uptrend.iloc[-2])
    if st_uptrend and not prev_uptrend:
        signals.append({"name": "Supertrend (10,3)", "action": "BUY", "reason": f"Trend flipped UP at ₹{latest_st:.0f}"})
    elif not st_uptrend and prev_uptrend:
        signals.append({"name": "Supertrend (10,3)", "action": "SELL", "reason": f"Trend flipped DOWN at ₹{latest_st:.0f}"})
    elif st_uptrend:
        signals.append({"name": "Supertrend (10,3)", "action": "BUY", "reason": "Uptrend continues"})
    else:
        signals.append({"name": "Supertrend (10,3)", "action": "SELL", "reason": "Downtrend continues"})

    # ADX (QUANT) — trend strength + direction
    if latest_adx > 25:  # strong trend
        if latest_plus_di > latest_minus_di:
            signals.append({"name": "ADX (14)", "action": "BUY", "reason": f"Strong uptrend (ADX {latest_adx:.0f})"})
        else:
            signals.append({"name": "ADX (14)", "action": "SELL", "reason": f"Strong downtrend (ADX {latest_adx:.0f})"})
    else:
        signals.append({"name": "ADX (14)", "action": "HOLD", "reason": f"Weak trend (ADX {latest_adx:.0f})"})

    # Stochastic (QUANT) — overbought/oversold momentum
    if latest_stoch_k < 20 and latest_stoch_k > latest_stoch_d:
        signals.append({"name": "Stochastic", "action": "BUY", "reason": f"Oversold cross-up at {latest_stoch_k:.0f}"})
    elif latest_stoch_k > 80 and latest_stoch_k < latest_stoch_d:
        signals.append({"name": "Stochastic", "action": "SELL", "reason": f"Overbought cross-down at {latest_stoch_k:.0f}"})
    else:
        signals.append({"name": "Stochastic", "action": "HOLD", "reason": f"Neutral at {latest_stoch_k:.0f}"})

    # Overall consensus
    buys = sum(1 for s in signals if s["action"] == "BUY")
    sells = sum(1 for s in signals if s["action"] == "SELL")
    if buys > sells and buys >= 3:
        consensus = "BUY"
    elif sells > buys and sells >= 3:
        consensus = "SELL"
    else:
        consensus = "HOLD"

    return {
        "indicators": {
            "rsi": round(latest_rsi, 2),
            "macd": round(latest_macd, 2),
            "macd_signal": round(latest_signal_line, 2),
            "macd_hist": round(latest_hist, 2),
            "sma20": round(latest_sma20, 2),
            "sma50": round(latest_sma50, 2),
            "bb_upper": round(latest_bb_u, 2),
            "bb_lower": round(latest_bb_l, 2),
            "price": round(latest_close, 2),
            "supertrend": round(latest_st, 2),
            "supertrend_uptrend": st_uptrend,
            "adx": round(latest_adx, 2),
            "stoch_k": round(latest_stoch_k, 2),
            "stoch_d": round(latest_stoch_d, 2),
        },
        "signals": signals,
        "consensus": consensus,
        "buy_count": buys,
        "sell_count": sells,
        "hold_count": len(signals) - buys - sells,
    }


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    if "timestamp" in doc and isinstance(doc["timestamp"], datetime):
        doc["timestamp"] = doc["timestamp"].isoformat()
    if "added_at" in doc and isinstance(doc["added_at"], datetime):
        doc["added_at"] = doc["added_at"].isoformat()
    return doc


# ============ Endpoints ============
@api_router.get("/")
async def root():
    return {"message": "Algo Trading Bot API", "status": "ok"}


@api_router.get("/market/indices")
async def market_indices():
    out = []
    for idx in INDICES:
        q = await asyncio.to_thread(fetch_quote, idx["symbol"])
        out.append({**idx, **q})
    return out


@api_router.get("/stocks/popular")
async def popular_stocks():
    sem = asyncio.Semaphore(8)

    async def one(s):
        async with sem:
            q = await asyncio.to_thread(fetch_quote, s["symbol"])
            return {**s, **q}

    results = await asyncio.gather(*[one(s) for s in POPULAR_STOCKS])
    return results


@api_router.get("/stocks/search")
async def search_stocks(q: str):
    q_lower = q.lower()
    matches = [s for s in POPULAR_STOCKS if q_lower in s["symbol"].lower() or q_lower in s["name"].lower()]
    return matches[:10]


@api_router.get("/stocks/{symbol}")
async def stock_detail(symbol: str):
    q = await asyncio.to_thread(fetch_quote, symbol)
    df = await asyncio.to_thread(fetch_history, symbol, "3mo", "1d")
    chart = []
    if not df.empty:
        # last 60 days
        df_tail = df.tail(60)
        for ts, row in df_tail.iterrows():
            chart.append({
                "date": ts.strftime("%Y-%m-%d"),
                "close": round(float(row["Close"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "volume": int(row["Volume"]) if not np.isnan(row["Volume"]) else 0,
            })
    return {"quote": q, "chart": chart}


@api_router.get("/stocks/{symbol}/signals")
async def stock_signals(symbol: str):
    df = await asyncio.to_thread(fetch_history, symbol, "6mo", "1d")
    if df.empty:
        raise HTTPException(status_code=404, detail="No data for symbol")
    result = await asyncio.to_thread(compute_indicators, df)
    return result


@api_router.get("/stocks/{symbol}/predict")
async def stock_predict(symbol: str):
    """Predict next move using all 8 indicators + volatility-based probability bands."""
    import math
    try:
        from scipy.stats import norm  # type: ignore
        _has_scipy = True
    except Exception:
        _has_scipy = False

    df = await asyncio.to_thread(fetch_history, symbol, "6mo", "1d")
    if df.empty or len(df) < 30:
        raise HTTPException(status_code=404, detail="Insufficient data for prediction")

    ind = await asyncio.to_thread(compute_indicators, df)
    if "error" in ind:
        raise HTTPException(status_code=500, detail="Indicator computation failed")

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    spot = float(close.iloc[-1])

    # ATR(14) for volatility
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])
    atr_pct = atr / spot if spot > 0 else 0.01

    # Historical daily log volatility (last 60 days)
    log_ret = np.log(close / close.shift(1)).dropna().tail(60)
    daily_sigma = float(log_ret.std()) if len(log_ret) > 1 else 0.015

    bull = int(ind.get("buy_count", 0))
    bear = int(ind.get("sell_count", 0))
    total = 8
    net = bull - bear
    confidence_pct = round(max(bull, bear) / total * 100)

    if net >= 2:
        direction = "BULLISH"
    elif net <= -2:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    # Directional bias: net signal score scaled to [-0.7, 0.7] of ATR magnitude
    bias = (net / total) * 0.7

    horizons = [
        ("Next Day", 1),
        ("1 Week", 5),
        ("1 Month", 22),
    ]
    predictions = []
    for label, days in horizons:
        sigma_h = daily_sigma * math.sqrt(days)
        # Expected directional move proportional to ATR and bias
        expected_move = bias * atr * math.sqrt(days)
        target = spot + expected_move
        # 1-sigma probability band (~68% confidence)
        band_low = target * math.exp(-sigma_h)
        band_high = target * math.exp(sigma_h)
        # P(close > spot) using normal CDF on log-return drift
        if _has_scipy and sigma_h > 0:
            drift = math.log(target / spot) if target > 0 else 0
            prob_up = round(float(norm.cdf(drift / sigma_h)) * 100, 1)
        else:
            # fallback heuristic
            prob_up = 50.0 + (bias * 35) - (0 if days == 1 else (days - 1) * 0.5)
            prob_up = max(5.0, min(95.0, round(prob_up, 1)))
        predictions.append({
            "horizon": label,
            "days": days,
            "target": round(target, 2),
            "low": round(band_low, 2),
            "high": round(band_high, 2),
            "prob_up": prob_up,
            "expected_change_pct": round((target / spot - 1) * 100, 2),
        })

    # Key drivers — top signals aligned with prevailing direction
    align = "BUY" if net >= 0 else "SELL"
    counter = "SELL" if net >= 0 else "BUY"
    drivers = [{"name": s["name"], "reason": s["reason"]} for s in ind["signals"] if s["action"] == align][:4]
    risks = [{"name": s["name"], "reason": s["reason"]} for s in ind["signals"] if s["action"] == counter][:3]

    # Recommendation logic
    if confidence_pct >= 60 and direction == "BULLISH":
        rec = "BUY / ACCUMULATE"
        rec_color = "profit"
    elif confidence_pct >= 60 and direction == "BEARISH":
        rec = "SELL / EXIT LONGS"
        rec_color = "loss"
    elif direction == "NEUTRAL":
        rec = "RANGE-BOUND · OPTIONS PLAY"
        rec_color = "warning"
    else:
        rec = "WAIT · WEAK CONSENSUS"
        rec_color = "neutral"

    # Plain English summary
    pred_1d = predictions[0]
    move_direction_word = "rise" if pred_1d["expected_change_pct"] > 0.05 else "fall" if pred_1d["expected_change_pct"] < -0.05 else "consolidate"
    narrative = (
        f"{bull} of {total} algorithms signal BUY, {bear} signal SELL. "
        f"Expected to {move_direction_word} to ₹{pred_1d['target']:.2f} tomorrow "
        f"({pred_1d['prob_up']:.0f}% probability of close above current price). "
        f"Volatility ATR ~{atr_pct*100:.1f}%. "
        + (f"Strong {direction.lower()} setup." if confidence_pct >= 60 else "Mixed signals — trade with caution.")
    )

    return {
        "symbol": symbol,
        "current_price": round(spot, 2),
        "direction": direction,
        "confidence_pct": confidence_pct,
        "bull_count": bull,
        "bear_count": bear,
        "neutral_count": int(ind.get("hold_count", 0)),
        "net_score": net,
        "atr_pct": round(atr_pct * 100, 2),
        "volatility_pct": round(daily_sigma * 100, 2),
        "predictions": predictions,
        "key_drivers": drivers,
        "risk_factors": risks,
        "recommendation": rec,
        "recommendation_color": rec_color,
        "narrative": narrative,
    }


@api_router.get("/stocks/{symbol}/intraday-forecast")
async def stock_intraday_forecast(symbol: str):
    """5-min candle predictions for next 5/10/15/30 min + walk-forward backtest accuracy."""
    import math
    df = await asyncio.to_thread(fetch_history, symbol, "60d", "5m")
    if df.empty or len(df) < 100:
        raise HTTPException(status_code=404, detail="Insufficient intraday data")

    series = await asyncio.to_thread(compute_signal_series, df)
    if series.empty:
        raise HTTPException(status_code=500, detail="Indicator computation failed")

    horizons = [
        {"label": "5 min", "bars": 1},
        {"label": "10 min", "bars": 2},
        {"label": "15 min", "bars": 3},
        {"label": "30 min", "bars": 6},
    ]

    last_idx = len(series) - 1
    last = series.iloc[last_idx]
    spot = float(last["close"])
    atr = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
    net = int(last["net_score"]) if not pd.isna(last["net_score"]) else 0
    bull = int(last["buy_count"]) if not pd.isna(last["buy_count"]) else 0
    bear = int(last["sell_count"]) if not pd.isna(last["sell_count"]) else 0
    confidence_pct = round(max(bull, bear) / 8 * 100)
    if net >= 2:
        direction = "BULLISH"
    elif net <= -2:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"

    close_s = series["close"]
    log_ret = np.log(close_s / close_s.shift(1)).dropna().tail(200)
    sigma_5m = float(log_ret.std()) if len(log_ret) > 1 else 0.001
    bias = (net / 8) * 0.55

    live_predictions = []
    for h in horizons:
        bars = h["bars"]
        sigma_h = sigma_5m * math.sqrt(bars)
        expected_move = bias * atr * math.sqrt(bars)
        target = spot + expected_move
        band_low = target * math.exp(-sigma_h) if sigma_h > 0 else target * 0.998
        band_high = target * math.exp(sigma_h) if sigma_h > 0 else target * 1.002
        try:
            from scipy.stats import norm  # type: ignore
            drift = math.log(target / spot) if target > 0 and spot > 0 else 0
            prob_up = round(float(norm.cdf(drift / sigma_h)) * 100, 1) if sigma_h > 0 else 50.0
        except Exception:
            prob_up = max(5.0, min(95.0, 50.0 + (bias * 30)))
        live_predictions.append({
            "label": h["label"],
            "bars": bars,
            "target": round(target, 2),
            "low": round(band_low, 2),
            "high": round(band_high, 2),
            "prob_up": prob_up,
            "expected_change_pct": round((target / spot - 1) * 100, 3),
            "predicted_direction": "UP" if expected_move > 0.001 * spot else "DOWN" if expected_move < -0.001 * spot else "FLAT",
        })

    # Walk-forward backtest
    max_future = max(h["bars"] for h in horizons)
    backtest_start = max(60, len(series) - 250)
    backtest_end = len(series) - max_future
    indices = list(range(backtest_start, backtest_end))
    if len(indices) > 200:
        step = max(1, len(indices) // 200)
        indices = indices[::step]

    bt = {h["label"]: {
        "bars": h["bars"], "total": 0, "correct": 0,
        "long_total": 0, "long_correct": 0,
        "short_total": 0, "short_correct": 0,
        "within_band": 0, "preds": [], "acts": []
    } for h in horizons}

    for i in indices:
        row = series.iloc[i]
        if pd.isna(row["net_score"]) or pd.isna(row["atr"]):
            continue
        bar_net = int(row["net_score"])
        bar_spot = float(row["close"])
        bar_atr = float(row["atr"])
        bar_bias = (bar_net / 8) * 0.55
        if bar_net >= 2:
            pred_dir = 1
        elif bar_net <= -2:
            pred_dir = -1
        else:
            pred_dir = 0

        for h in horizons:
            bars = h["bars"]
            if i + bars >= len(series):
                continue
            future_close = float(series.iloc[i + bars]["close"])
            actual_change = future_close - bar_spot
            actual_dir = 1 if actual_change > 0 else -1 if actual_change < 0 else 0
            sigma_h = sigma_5m * math.sqrt(bars)
            expected_move = bar_bias * bar_atr * math.sqrt(bars)
            target = bar_spot + expected_move
            band_low = target * math.exp(-sigma_h) if sigma_h > 0 else target * 0.998
            band_high = target * math.exp(sigma_h) if sigma_h > 0 else target * 1.002

            b = bt[h["label"]]
            if pred_dir != 0:
                b["total"] += 1
                if pred_dir == actual_dir:
                    b["correct"] += 1
                if pred_dir == 1:
                    b["long_total"] += 1
                    if actual_dir == 1:
                        b["long_correct"] += 1
                else:
                    b["short_total"] += 1
                    if actual_dir == -1:
                        b["short_correct"] += 1
            if band_low <= future_close <= band_high:
                b["within_band"] += 1
            b["preds"].append(target / bar_spot - 1)
            b["acts"].append(future_close / bar_spot - 1)

    total_samples = len(indices)
    backtest_summary = []
    for h in horizons:
        b = bt[h["label"]]
        total = b["total"]
        acc = round(b["correct"] / total * 100, 1) if total > 0 else 0.0
        long_acc = round(b["long_correct"] / b["long_total"] * 100, 1) if b["long_total"] > 0 else 0.0
        short_acc = round(b["short_correct"] / b["short_total"] * 100, 1) if b["short_total"] > 0 else 0.0
        band_hit = round(b["within_band"] / total_samples * 100, 1) if total_samples > 0 else 0.0
        if b["preds"]:
            errs = [abs(p - a) for p, a in zip(b["preds"], b["acts"])]
            mae_pct = round(float(np.mean(errs)) * 100, 3)
        else:
            mae_pct = 0.0
        backtest_summary.append({
            "label": h["label"],
            "bars": h["bars"],
            "total_signals": total,
            "directional_accuracy_pct": acc,
            "long_accuracy_pct": long_acc,
            "short_accuracy_pct": short_acc,
            "within_1sigma_band_pct": band_hit,
            "mae_pct": mae_pct,
            "samples": total_samples,
        })

    sum_total = sum(b["total_signals"] for b in backtest_summary)
    overall_acc = round(
        sum(b["directional_accuracy_pct"] * b["total_signals"] for b in backtest_summary) / sum_total, 1
    ) if sum_total > 0 else 0.0

    last_ts = df.index[-1]
    last_ts_str = last_ts.strftime("%Y-%m-%d %H:%M") if hasattr(last_ts, "strftime") else str(last_ts)

    return {
        "symbol": symbol,
        "interval": "5m",
        "current_price": round(spot, 2),
        "as_of": last_ts_str,
        "direction": direction,
        "confidence_pct": confidence_pct,
        "bull_count": bull,
        "bear_count": bear,
        "net_score": net,
        "volatility_5m_pct": round(sigma_5m * 100, 3),
        "atr_pct": round(atr / spot * 100, 3) if spot > 0 else 0.0,
        "predictions": live_predictions,
        "backtest": backtest_summary,
        "overall_accuracy_pct": overall_acc,
        "backtest_window_bars": total_samples,
        "backtest_window_days_approx": round(total_samples * 5 / 60 / 6.25, 1),
    }



@api_router.get("/signals/top")
async def top_signals():
    """Scan popular stocks and return BUY/SELL signal recommendations."""
    sem = asyncio.Semaphore(5)

    async def one(s):
        async with sem:
            try:
                df = await asyncio.to_thread(fetch_history, s["symbol"], "6mo", "1d")
                if df.empty:
                    return None
                ind = await asyncio.to_thread(compute_indicators, df)
                if "error" in ind:
                    return None
                q = await asyncio.to_thread(fetch_quote, s["symbol"])
                return {
                    **s,
                    "price": q["price"],
                    "change_pct": q["change_pct"],
                    "consensus": ind["consensus"],
                    "buy_count": ind["buy_count"],
                    "sell_count": ind["sell_count"],
                    "rsi": ind["indicators"]["rsi"],
                }
            except Exception as e:
                logger.warning(f"top_signals {s['symbol']}: {e}")
                return None

    results = await asyncio.gather(*[one(s) for s in POPULAR_STOCKS])
    results = [r for r in results if r]
    # Sort: BUY first, then by buy_count desc
    order = {"BUY": 0, "SELL": 1, "HOLD": 2}
    results.sort(key=lambda r: (order.get(r["consensus"], 3), -r["buy_count"]))
    return results


# ============ Watchlist ============
@api_router.get("/watchlist")
async def get_watchlist():
    items = await db.watchlist.find({"user_id": DEFAULT_USER}, {"_id": 0}).to_list(200)
    # enrich with live quote
    sem = asyncio.Semaphore(8)

    async def enrich(it):
        async with sem:
            q = await asyncio.to_thread(fetch_quote, it["symbol"])
            return {**it, **q}

    enriched = await asyncio.gather(*[enrich(i) for i in items])
    return enriched


@api_router.post("/watchlist")
async def add_watchlist(body: WatchlistAdd):
    exists = await db.watchlist.find_one({"user_id": DEFAULT_USER, "symbol": body.symbol})
    if exists:
        return {"ok": True, "message": "Already in watchlist"}
    item = WatchlistItem(symbol=body.symbol, name=body.name)
    doc = item.model_dump()
    await db.watchlist.insert_one(doc.copy())
    return {"ok": True, "item": _clean(doc)}


@api_router.delete("/watchlist/{symbol}")
async def remove_watchlist(symbol: str):
    await db.watchlist.delete_one({"user_id": DEFAULT_USER, "symbol": symbol})
    return {"ok": True}


# ============ Paper Trading ============
@api_router.post("/trades/paper")
async def place_paper_trade(body: PaperTradeRequest):
    # ensure portfolio exists
    port = await db.portfolio.find_one({"user_id": DEFAULT_USER})
    if not port:
        await db.portfolio.insert_one({"user_id": DEFAULT_USER, "cash": STARTING_CASH, "positions": {}})
        port = {"user_id": DEFAULT_USER, "cash": STARTING_CASH, "positions": {}}

    cash = float(port.get("cash", STARTING_CASH))
    positions = port.get("positions", {})
    total = body.price * body.quantity

    if body.side == "BUY":
        if cash < total:
            raise HTTPException(status_code=400, detail=f"Insufficient cash. Need ₹{total:.2f}, have ₹{cash:.2f}")
        cash -= total
        pos = positions.get(body.symbol, {"name": body.name, "quantity": 0, "avg_price": 0.0})
        new_qty = pos["quantity"] + body.quantity
        new_avg = ((pos["avg_price"] * pos["quantity"]) + total) / new_qty if new_qty else body.price
        positions[body.symbol] = {"name": body.name, "quantity": new_qty, "avg_price": round(new_avg, 2)}
    else:  # SELL
        pos = positions.get(body.symbol)
        if not pos or pos["quantity"] < body.quantity:
            raise HTTPException(status_code=400, detail="Not enough shares to sell")
        cash += total
        new_qty = pos["quantity"] - body.quantity
        if new_qty == 0:
            positions.pop(body.symbol, None)
        else:
            positions[body.symbol] = {**pos, "quantity": new_qty}

    await db.portfolio.update_one(
        {"user_id": DEFAULT_USER},
        {"$set": {"cash": round(cash, 2), "positions": positions}},
    )

    trade = PaperTrade(symbol=body.symbol, name=body.name, side=body.side,
                      quantity=body.quantity, price=body.price, total=round(total, 2))
    doc = trade.model_dump()
    await db.trades.insert_one(doc.copy())
    return {"ok": True, "trade": _clean(doc), "cash_remaining": round(cash, 2)}


@api_router.get("/trades")
async def get_trades():
    items = await db.trades.find({"user_id": DEFAULT_USER}, {"_id": 0}).sort("timestamp", -1).to_list(200)
    return [_clean(i) for i in items]


@api_router.get("/portfolio")
async def get_portfolio():
    port = await db.portfolio.find_one({"user_id": DEFAULT_USER}, {"_id": 0})
    if not port:
        port = {"user_id": DEFAULT_USER, "cash": STARTING_CASH, "positions": {}}

    positions = port.get("positions", {})
    enriched_positions = []
    total_invested = 0.0
    total_current = 0.0

    sem = asyncio.Semaphore(8)

    async def enrich(sym, pos):
        async with sem:
            q = await asyncio.to_thread(fetch_quote, sym)
            cur_price = q["price"] if q["price"] else pos["avg_price"]
            invested = pos["avg_price"] * pos["quantity"]
            current = cur_price * pos["quantity"]
            pnl = current - invested
            pnl_pct = (pnl / invested * 100) if invested else 0
            return {
                "symbol": sym,
                "name": pos["name"],
                "quantity": pos["quantity"],
                "avg_price": pos["avg_price"],
                "current_price": cur_price,
                "invested": round(invested, 2),
                "current_value": round(current, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
            }

    if positions:
        enriched_positions = await asyncio.gather(*[enrich(s, p) for s, p in positions.items()])
        total_invested = sum(p["invested"] for p in enriched_positions)
        total_current = sum(p["current_value"] for p in enriched_positions)

    cash = float(port.get("cash", STARTING_CASH))
    total_pnl = total_current - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0
    net_worth = cash + total_current

    return {
        "cash": round(cash, 2),
        "starting_cash": STARTING_CASH,
        "invested": round(total_invested, 2),
        "current_value": round(total_current, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "net_worth": round(net_worth, 2),
        "overall_pnl": round(net_worth - STARTING_CASH, 2),
        "overall_pnl_pct": round((net_worth - STARTING_CASH) / STARTING_CASH * 100, 2),
        "positions": enriched_positions,
    }


@api_router.post("/portfolio/reset")
async def reset_portfolio():
    await db.portfolio.delete_many({"user_id": DEFAULT_USER})
    await db.trades.delete_many({"user_id": DEFAULT_USER})
    return {"ok": True}


# ============ AI Analysis ============
@api_router.post("/ai/analyze")
async def ai_analyze(body: AIAnalyzeRequest):
    df = await asyncio.to_thread(fetch_history, body.symbol, "6mo", "1d")
    if df.empty:
        raise HTTPException(status_code=404, detail="No data")
    ind = await asyncio.to_thread(compute_indicators, df)
    if "error" in ind:
        raise HTTPException(status_code=400, detail=ind["error"])
    q = await asyncio.to_thread(fetch_quote, body.symbol)

    signals_text = "\n".join([f"- {s['name']}: {s['action']} ({s['reason']})" for s in ind["signals"]])
    prompt = (
        f"Stock: {body.symbol}\n"
        f"Current Price: ₹{q['price']} (change today: {q['change_pct']}%)\n"
        f"Indicators:\n"
        f"- RSI(14): {ind['indicators']['rsi']}\n"
        f"- MACD: {ind['indicators']['macd']} (signal {ind['indicators']['macd_signal']})\n"
        f"- SMA20: ₹{ind['indicators']['sma20']}, SMA50: ₹{ind['indicators']['sma50']}\n"
        f"- Bollinger: lower ₹{ind['indicators']['bb_lower']}, upper ₹{ind['indicators']['bb_upper']}\n"
        f"Algorithm signals:\n{signals_text}\n"
        f"Algorithm consensus: {ind['consensus']}\n\n"
        f"In 4-5 short bullet points, give a clear technical view: trend, momentum, risk levels (stop loss & target), and final recommendation. Keep it crisp and actionable for a retail trader. End with a 1-line disclaimer."
    )

    async def gen():
        try:
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"analyze-{body.symbol}-{uuid.uuid4().hex[:6]}",
                system_message="You are an experienced technical analyst for Indian equity markets. Be concise, neutral, and risk-aware. Never promise profits.",
            ).with_model("anthropic", "claude-sonnet-4-6")
            async for ev in chat.stream_message(UserMessage(text=prompt)):
                if isinstance(ev, TextDelta):
                    yield ev.content
                elif isinstance(ev, StreamDone):
                    break
        except Exception as e:
            logger.exception("AI analyze failed")
            yield f"\n[AI analysis unavailable: {e}]"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ============ OPTIONS TRADING ============
@api_router.get("/options/strategies")
async def options_list_strategies():
    """List all available option strategy templates."""
    return [{"key": k, **{kk: vv for kk, vv in v.items() if kk != "legs"}, "legs": v["legs"]} for k, v in STRATEGIES.items()]


@api_router.get("/options/suggest")
async def options_suggest(index: str = "NIFTY"):
    """Suggest an options strategy based on index technical analysis."""
    sym = INDEX_SYMBOL.get(index.upper())
    if not sym:
        raise HTTPException(status_code=400, detail=f"Unknown index. Try NIFTY, SENSEX, BANKNIFTY.")
    q = await asyncio.to_thread(fetch_quote, sym)
    df = await asyncio.to_thread(fetch_history, sym, "6mo", "1d")
    if df.empty:
        raise HTTPException(status_code=503, detail="Index data unavailable")
    ind = await asyncio.to_thread(compute_indicators, df)
    if "error" in ind:
        raise HTTPException(status_code=503, detail=ind["error"])
    strat = suggest_strategy(ind["consensus"], ind["indicators"]["rsi"], q["change_pct"])
    # Build concrete legs with strike numbers around ATM (rounded to 50 for NIFTY, 100 for BANKNIFTY, 100 for SENSEX)
    spot = q["price"]
    step = 100 if index.upper() in ("BANKNIFTY", "SENSEX") else 50
    atm = round(spot / step) * step
    concrete_legs = []
    for leg in strat["legs"]:
        strike = atm + leg["strike_offset"]
        # Estimate premium via Black-Scholes with ~15% IV, 7 days to expiry
        T = 7 / 365.0
        prem = bs_price(spot, strike, T, 0.07, 0.15, leg["type"])
        concrete_legs.append({
            "side": leg["side"], "type": leg["type"], "strike": strike,
            "premium_est": round(prem, 2), "qty": leg["qty"],
        })
    return {
        "index": index.upper(),
        "spot": spot,
        "atm": atm,
        "lot_size": LOT_SIZE.get(index.upper(), 75),
        "consensus": ind["consensus"],
        "rsi": ind["indicators"]["rsi"],
        "change_pct": q["change_pct"],
        "strategy": strat,
        "concrete_legs": concrete_legs,
        "note": "Premium estimates use Black-Scholes (15% IV, weekly expiry). Use NSE option chain for live prices.",
    }


@api_router.post("/options/calculate")
async def options_calculate(req: CalcRequest):
    """Compute payoff diagram, greeks, breakevens for an options strategy."""
    return calculate_payoff(req)


@api_router.get("/options/chain")
async def options_chain(index: str = "NIFTY"):
    """Best-effort NSE option chain (may be blocked from server)."""
    return await asyncio.to_thread(fetch_option_chain, index.upper())


# ============ FYERS BROKER INTEGRATION ============
@api_router.get("/fyers/status")
async def fyers_status():
    if not fyers_int.is_configured():
        return {"configured": False, "connected": False}
    s = await fyers_int.get_status(db)
    return {"configured": True, **s}


@api_router.get("/fyers/login-url")
async def fyers_login_url():
    if not fyers_int.is_configured():
        raise HTTPException(status_code=400, detail="Fyers not configured")
    url = fyers_int.get_login_url()
    return {"login_url": url}


@api_router.get("/fyers/callback")
async def fyers_callback(auth_code: Optional[str] = None, s: Optional[str] = None, code: Optional[str] = None):
    ac = auth_code or code
    if not ac or (s and s != "ok"):
        return HTMLResponse(
            f"<html><body style='background:#0A0A0A;color:#fff;font-family:sans-serif;padding:32px;text-align:center'>"
            f"<h2 style='color:#EF4444'>Fyers login failed</h2><p>No auth code received. You can close this window and try again.</p></body></html>"
        )
    try:
        await fyers_int.exchange_auth_code(db, ac)
    except Exception as e:
        logger.exception("fyers callback failed")
        return HTMLResponse(
            f"<html><body style='background:#0A0A0A;color:#fff;font-family:sans-serif;padding:32px;text-align:center'>"
            f"<h2 style='color:#EF4444'>Connection failed</h2><p>{e}</p></body></html>"
        )
    return HTMLResponse(
        "<html><body style='background:#0A0A0A;color:#fff;font-family:sans-serif;padding:48px;text-align:center'>"
        "<h2 style='color:#10B981'>✓ Fyers Connected</h2>"
        "<p>You can close this window and return to the AlgoBot app.</p>"
        "<p style='color:#71717A;font-size:13px;margin-top:24px'>Access token valid for 24 hours.</p>"
        "</body></html>"
    )


@api_router.post("/fyers/disconnect")
async def fyers_disconnect():
    return await fyers_int.disconnect(db)


@api_router.get("/fyers/profile")
async def fyers_profile():
    client = await fyers_int.get_client(db)
    if not client:
        raise HTTPException(status_code=401, detail="Fyers not connected. Please re-login.")
    return await asyncio.to_thread(fyers_int.get_profile_sync, client)


@api_router.get("/fyers/funds")
async def fyers_funds():
    client = await fyers_int.get_client(db)
    if not client:
        raise HTTPException(status_code=401, detail="Fyers not connected. Please re-login.")
    return await asyncio.to_thread(fyers_int.get_funds_sync, client)


@api_router.get("/fyers/holdings")
async def fyers_holdings():
    client = await fyers_int.get_client(db)
    if not client:
        raise HTTPException(status_code=401, detail="Fyers not connected. Please re-login.")
    return await asyncio.to_thread(fyers_int.get_holdings_sync, client)


@api_router.get("/fyers/positions")
async def fyers_positions():
    client = await fyers_int.get_client(db)
    if not client:
        raise HTTPException(status_code=401, detail="Fyers not connected. Please re-login.")
    return await asyncio.to_thread(fyers_int.get_positions_sync, client)


@api_router.get("/fyers/option-chain")
async def fyers_option_chain(index: str = "NIFTY", strike_count: int = 10):
    client = await fyers_int.get_client(db)
    if not client:
        return {"available": False, "reason": "Fyers not connected. Connect from Settings to see live option chain."}
    return await asyncio.to_thread(fyers_int.fetch_option_chain_sync, client, index, strike_count)


@api_router.get("/fyers/history")
async def fyers_history(symbol: str, resolution: str = "5"):
    """Get intraday/historical candles for any Fyers symbol (eg NSE:NIFTY24JUN23400CE)."""
    client = await fyers_int.get_client(db)
    if not client:
        return {"available": False, "reason": "Fyers not connected"}
    return await asyncio.to_thread(fyers_int.get_history_sync, client, symbol, resolution)


@api_router.post("/fyers/orders")
async def fyers_place_order(order: fyers_int.FyersOrderRequest, live_mode: bool = False):
    """Place a real order on Fyers. ⚠ live_mode=true required to actually fire — safety check."""
    if not live_mode:
        raise HTTPException(status_code=400, detail="SAFETY: Pass live_mode=true to place real order. This is a real-money trade.")
    client = await fyers_int.get_client(db)
    if not client:
        raise HTTPException(status_code=401, detail="Fyers not connected.")
    result = await asyncio.to_thread(fyers_int.place_order_sync, client, order)
    return result


import sys


# ============ AUTO-TRADING BOT ============
@api_router.get("/bot/status")
async def bot_status():
    return bot_service.get_status()


@api_router.post("/bot/start")
async def bot_start(mode: str = "paper"):
    if mode == "live":
        client = await fyers_int.get_client(db)
        if not client:
            raise HTTPException(status_code=400, detail="Live mode requires Fyers connection. Connect Fyers first.")
    server_module = sys.modules[__name__]
    return await bot_service.start(db, server_module, mode=mode)


@api_router.post("/bot/stop")
async def bot_stop():
    return await bot_service.stop()


@api_router.get("/bot/config")
async def bot_get_config():
    return bot_service.get_config()


@api_router.post("/bot/config")
async def bot_set_config(updates: dict):
    return bot_service.set_config(updates)


@api_router.get("/bot/decisions")
async def bot_decisions(limit: int = 50):
    in_mem = bot_service.get_decisions(limit)
    if in_mem:
        return in_mem
    # Fallback: load from MongoDB if backend just restarted
    docs = await db.bot_decisions.find({}, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
    return docs


@api_router.delete("/bot/decisions")
async def bot_clear_decisions():
    await db.bot_decisions.delete_many({})
    bot_service._decisions.clear()
    return {"ok": True}


@api_router.get("/bot/stats")
async def bot_stats():
    """Compute win rate, avg P&L, best/worst symbol from completed round-trip trades."""
    trades = await db.trades.find({"user_id": DEFAULT_USER}, {"_id": 0}).sort("timestamp", 1).to_list(2000)
    # Pair BUY → matching SELL on same symbol (FIFO)
    open_lots: dict[str, list] = {}
    completed: list[dict] = []
    for t in trades:
        sym = t["symbol"]
        if t["side"] == "BUY":
            open_lots.setdefault(sym, []).append(t)
        else:  # SELL
            qty_left = t["quantity"]
            while qty_left > 0 and open_lots.get(sym):
                buy = open_lots[sym][0]
                take = min(qty_left, buy["quantity"])
                pnl = (t["price"] - buy["price"]) * take
                completed.append({
                    "symbol": sym, "name": t.get("name", sym),
                    "buy_price": buy["price"], "sell_price": t["price"],
                    "qty": take, "pnl": round(pnl, 2),
                    "pct": round((t["price"] - buy["price"]) / buy["price"] * 100, 2) if buy["price"] else 0,
                    "buy_time": buy["timestamp"], "sell_time": t["timestamp"],
                })
                buy["quantity"] -= take
                qty_left -= take
                if buy["quantity"] == 0:
                    open_lots[sym].pop(0)

    if not completed:
        return {
            "completed_trades": 0, "wins": 0, "losses": 0, "win_rate": 0,
            "total_pnl": 0, "avg_pnl": 0, "avg_win": 0, "avg_loss": 0,
            "best_trade": None, "worst_trade": None,
            "by_symbol": [],
        }

    wins = [c for c in completed if c["pnl"] > 0]
    losses = [c for c in completed if c["pnl"] < 0]
    total_pnl = sum(c["pnl"] for c in completed)
    by_sym: dict[str, dict] = {}
    for c in completed:
        s = by_sym.setdefault(c["symbol"], {"symbol": c["symbol"], "name": c["name"], "trades": 0, "pnl": 0.0, "wins": 0})
        s["trades"] += 1
        s["pnl"] += c["pnl"]
        if c["pnl"] > 0:
            s["wins"] += 1
    by_symbol = sorted(
        [{**v, "pnl": round(v["pnl"], 2), "win_rate": round(v["wins"] / v["trades"] * 100, 1)} for v in by_sym.values()],
        key=lambda r: -r["pnl"],
    )
    return {
        "completed_trades": len(completed),
        "wins": len(wins), "losses": len(losses),
        "win_rate": round(len(wins) / len(completed) * 100, 1),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / len(completed), 2),
        "avg_win": round(sum(c["pnl"] for c in wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(c["pnl"] for c in losses) / len(losses), 2) if losses else 0,
        "best_trade": max(completed, key=lambda c: c["pnl"]),
        "worst_trade": min(completed, key=lambda c: c["pnl"]),
        "by_symbol": by_symbol,
    }


@api_router.post("/options/paper-trade")
async def options_paper_trade(body: dict):
    """Place paper trades for all legs of an option strategy."""
    index = body.get("index", "NIFTY")
    legs = body.get("legs", [])
    lot = LOT_SIZE.get(index, 75)
    placed = []
    for leg in legs:
        try:
            # Create a synthetic option symbol like "NIFTY 23400 CE BUY"
            sym = f"{index} {leg['strike']} {leg['type']}"
            qty = int(leg.get("qty", 1)) * lot  # convert lots to units
            price = float(leg.get("premium", leg.get("premium_est", 0)))
            side = leg["side"]
            req = PaperTradeRequest(symbol=sym, name=sym, side=side, quantity=qty, price=price)
            result = await place_paper_trade(req)
            placed.append({"leg": sym, "side": side, "qty": qty, "price": price, "ok": True})
        except Exception as e:
            placed.append({"leg": str(leg), "ok": False, "error": str(e)[:100]})
    return {"ok": all(p.get("ok") for p in placed), "placed": placed}


@api_router.get("/stocks/{symbol}/chart")
async def stock_chart(symbol: str, period: str = "3mo"):
    """Return chart data + all indicator series for plotting."""
    df = await asyncio.to_thread(fetch_history, symbol, period, "1d")
    if df.empty:
        raise HTTPException(status_code=404, detail="No data")
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    # SMA / Bollinger
    sma20 = close.rolling(20).mean()
    sma50 = close.rolling(50).mean()
    bb_mid = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - signal

    # === QUANT INDICATOR SERIES ===
    # ATR for Supertrend & ADX
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()

    # Supertrend (10, 3)
    hl2 = (high + low) / 2
    multiplier = 3.0
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr
    supertrend = pd.Series(index=df.index, dtype=float)
    st_dir = pd.Series(index=df.index, dtype=float)  # 1 = up, -1 = down
    in_up = True
    for i in range(len(df)):
        if i == 0:
            supertrend.iloc[i] = upper_band.iloc[i]
            st_dir.iloc[i] = 1.0
            continue
        prev_close = float(close.iloc[i-1])
        prev_st = float(supertrend.iloc[i-1])
        if prev_close > prev_st:
            supertrend.iloc[i] = max(float(lower_band.iloc[i]), prev_st)
            in_up = True
        else:
            supertrend.iloc[i] = min(float(upper_band.iloc[i]), prev_st)
            in_up = False
        if float(close.iloc[i]) > supertrend.iloc[i] and not in_up:
            in_up = True
            supertrend.iloc[i] = float(lower_band.iloc[i])
        elif float(close.iloc[i]) < supertrend.iloc[i] and in_up:
            in_up = False
            supertrend.iloc[i] = float(upper_band.iloc[i])
        st_dir.iloc[i] = 1.0 if in_up else -1.0

    # ADX (14)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
    atr14 = tr.rolling(14).mean().replace(0, np.nan)
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr14)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr14)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx = dx.rolling(14).mean()

    # Stochastic (14, 3, 3)
    period_st = 14
    lowest_low = low.rolling(period_st).min()
    highest_high = high.rolling(period_st).max()
    stoch_k = 100 * (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    stoch_d = stoch_k.rolling(3).mean()

    # Take last 60 points
    tail = 60
    dates = [d.strftime("%Y-%m-%d") for d in df.index[-tail:]]
    def safe_list(s):
        return [None if np.isnan(v) else round(float(v), 2) for v in s.iloc[-tail:]]
    return {
        "dates": dates,
        "close": safe_list(close),
        "high": safe_list(high),
        "low": safe_list(low),
        "sma20": safe_list(sma20),
        "sma50": safe_list(sma50),
        "bb_upper": safe_list(bb_upper),
        "bb_lower": safe_list(bb_lower),
        "rsi": safe_list(rsi),
        "macd": safe_list(macd),
        "macd_signal": safe_list(signal),
        "macd_hist": safe_list(macd_hist),
        "supertrend": safe_list(supertrend),
        "supertrend_dir": safe_list(st_dir),
        "adx": safe_list(adx),
        "plus_di": safe_list(plus_di),
        "minus_di": safe_list(minus_di),
        "stoch_k": safe_list(stoch_k),
        "stoch_d": safe_list(stoch_d),
    }


# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
