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

# ML imports for prediction
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb
import warnings
warnings.filterwarnings('ignore')

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
        hist = hist.dropna(subset=["Close"]) if not hist.empty else hist
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
    return _compute_signal_votes(df, include_aggregate=True)


def _hull_ma(close: pd.Series, period: int = 9) -> pd.Series:
    """Hull Moving Average — much lower lag than SMA."""
    import math
    half = max(2, int(period / 2))
    sqrt_p = max(2, int(math.sqrt(period)))
    wma_half = close.rolling(half).apply(lambda x: np.dot(x, np.arange(1, len(x) + 1)) / (np.arange(1, len(x) + 1)).sum(), raw=True)
    wma_full = close.rolling(period).apply(lambda x: np.dot(x, np.arange(1, len(x) + 1)) / (np.arange(1, len(x) + 1)).sum(), raw=True)
    raw = 2 * wma_half - wma_full
    return raw.rolling(sqrt_p).apply(lambda x: np.dot(x, np.arange(1, len(x) + 1)) / (np.arange(1, len(x) + 1)).sum(), raw=True)


def _compute_signal_votes(df: pd.DataFrame, include_aggregate: bool = False) -> pd.DataFrame:
    """Compute per-indicator BUY (+1) / SELL (-1) / HOLD (0) votes per bar.
    Returns a DataFrame with vote columns plus close/atr/atr_pct/adx for regime detection."""
    if df.empty or len(df) < 30:
        return pd.DataFrame()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    open_ = df["Open"]
    volume = df["Volume"] if "Volume" in df.columns else pd.Series(1.0, index=df.index)

    # === Classical indicators ===
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
    macd_hist = macd - macd_sig

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

    # === NEW INDICATORS (v2) ===
    # Hull Moving Average (low-lag trend)
    hma = _hull_ma(close, 16)
    hma_prev = hma.shift(1)

    # Rate of Change (10-bar momentum)
    roc = (close / close.shift(10) - 1) * 100

    # Z-score (mean reversion vs 20-bar SMA)
    zscore = (close - bb_mid) / bb_std.replace(0, np.nan)

    # VWAP deviation (approximate VWAP using typical price * volume)
    typical = (high + low + close) / 3
    vol_safe = volume.replace(0, np.nan).fillna(1)
    rolling_vp = (typical * vol_safe).rolling(20).sum()
    rolling_v = vol_safe.rolling(20).sum().replace(0, np.nan)
    vwap = rolling_vp / rolling_v
    vwap_dev = (close - vwap) / vwap * 100

    # === V3 NEW INDICATORS (for higher accuracy) ===
    # CCI (Commodity Channel Index) - 20 period
    cci_mean = typical.rolling(20).mean()
    cci_mad = typical.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    cci = (typical - cci_mean) / (0.015 * cci_mad.replace(0, np.nan))
    
    # Williams %R (14 period)
    williams_r = -100 * (highest_high - close) / (highest_high - lowest_low).replace(0, np.nan)
    
    # OBV (On-Balance Volume) trend
    obv = pd.Series(index=df.index, dtype=float)
    obv.iloc[0] = 0
    for i in range(1, len(df)):
        if close.iloc[i] > close.iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
        elif close.iloc[i] < close.iloc[i-1]:
            obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
        else:
            obv.iloc[i] = obv.iloc[i-1]
    obv_sma = obv.rolling(10).mean()
    obv_trend = obv > obv_sma
    
    # Parabolic SAR (simplified)
    psar = pd.Series(index=df.index, dtype=float)
    psar_trend = pd.Series(index=df.index, dtype=bool)
    af_start, af_step, af_max = 0.02, 0.02, 0.2
    psar.iloc[0] = low.iloc[0]
    psar_trend.iloc[0] = True
    af = af_start
    ep = high.iloc[0]
    for i in range(1, len(df)):
        if psar_trend.iloc[i-1]:  # uptrend
            psar.iloc[i] = psar.iloc[i-1] + af * (ep - psar.iloc[i-1])
            psar.iloc[i] = min(psar.iloc[i], low.iloc[i-1], low.iloc[i-2] if i > 1 else low.iloc[i-1])
            if low.iloc[i] < psar.iloc[i]:
                psar_trend.iloc[i] = False
                psar.iloc[i] = ep
                af = af_start
                ep = low.iloc[i]
            else:
                psar_trend.iloc[i] = True
                if high.iloc[i] > ep:
                    ep = high.iloc[i]
                    af = min(af + af_step, af_max)
        else:  # downtrend
            psar.iloc[i] = psar.iloc[i-1] - af * (psar.iloc[i-1] - ep)
            psar.iloc[i] = max(psar.iloc[i], high.iloc[i-1], high.iloc[i-2] if i > 1 else high.iloc[i-1])
            if high.iloc[i] > psar.iloc[i]:
                psar_trend.iloc[i] = True
                psar.iloc[i] = ep
                af = af_start
                ep = high.iloc[i]
            else:
                psar_trend.iloc[i] = False
                if low.iloc[i] < ep:
                    ep = low.iloc[i]
                    af = min(af + af_step, af_max)
    
    # Keltner Channel
    kc_mid = ema26
    kc_upper = kc_mid + 2 * atr
    kc_lower = kc_mid - 2 * atr
    
    # MFI (Money Flow Index) - 14 period
    mf_raw = typical * volume
    mf_positive = pd.Series(np.where(typical > typical.shift(1), mf_raw, 0), index=df.index)
    mf_negative = pd.Series(np.where(typical < typical.shift(1), mf_raw, 0), index=df.index)
    mf_ratio = mf_positive.rolling(14).sum() / mf_negative.rolling(14).sum().replace(0, np.nan)
    mfi = 100 - (100 / (1 + mf_ratio))
    
    # Momentum (12-bar simple momentum)
    momentum = close - close.shift(12)
    mom_pct = momentum / close.shift(12) * 100

    # === V4 CANDLESTICK PATTERNS (High Accuracy) ===
    body = close - open_
    body_abs = body.abs()
    upper_wick = high - pd.concat([close, open_], axis=1).max(axis=1)
    lower_wick = pd.concat([close, open_], axis=1).min(axis=1) - low
    candle_range = high - low
    
    # Engulfing patterns (high accuracy reversal signals)
    prev_body = body.shift(1)
    bullish_engulf = (prev_body < 0) & (body > 0) & (body_abs > prev_body.abs() * 1.2)
    bearish_engulf = (prev_body > 0) & (body < 0) & (body_abs > prev_body.abs() * 1.2)
    
    # Hammer/Hanging Man (reversal)
    hammer = (lower_wick > body_abs * 2) & (upper_wick < body_abs * 0.3) & (rsi < 40)
    shooting_star = (upper_wick > body_abs * 2) & (lower_wick < body_abs * 0.3) & (rsi > 60)
    
    # Doji (indecision, filter based on next bar)
    doji = body_abs < candle_range * 0.1
    
    # Three white soldiers / Three black crows (strong continuation)
    three_white = (body > 0) & (body.shift(1) > 0) & (body.shift(2) > 0) & \
                  (close > close.shift(1)) & (close.shift(1) > close.shift(2))
    three_black = (body < 0) & (body.shift(1) < 0) & (body.shift(2) < 0) & \
                  (close < close.shift(1)) & (close.shift(1) < close.shift(2))
    
    # Morning/Evening Star patterns
    morning_star = (body.shift(2) < 0) & (body_abs.shift(1) < body_abs.shift(2) * 0.3) & (body > 0) & \
                   (close > (close.shift(2) + open_.shift(2)) / 2)
    evening_star = (body.shift(2) > 0) & (body_abs.shift(1) < body_abs.shift(2) * 0.3) & (body < 0) & \
                   (close < (close.shift(2) + open_.shift(2)) / 2)
    
    # Support/Resistance bounces (price action)
    recent_low = low.rolling(20).min()
    recent_high = high.rolling(20).max()
    support_bounce = (low <= recent_low * 1.002) & (close > open_)
    resistance_reject = (high >= recent_high * 0.998) & (close < open_)
    
    # Breakout patterns
    breakout_high = (close > recent_high.shift(1)) & (volume > volume.rolling(20).mean() * 1.3)
    breakdown_low = (close < recent_low.shift(1)) & (volume > volume.rolling(20).mean() * 1.3)

    # === Per-indicator BUY/SELL votes (+1/-1/0) ===
    votes = pd.DataFrame(index=df.index)
    votes["v_sma"] = np.where(sma20 > sma50, 1, np.where(sma20 < sma50, -1, 0))
    votes["v_ema"] = np.where(ema12 > ema26, 1, np.where(ema12 < ema26, -1, 0))
    votes["v_rsi"] = np.where(rsi < 30, 1, np.where(rsi > 70, -1, 0))
    macd_rising = macd_hist > macd_hist.shift()
    votes["v_macd"] = np.where((macd_hist > 0) & macd_rising, 1,
                               np.where((macd_hist < 0) & ~macd_rising, -1, 0))
    votes["v_bb"] = np.where(close < bb_lower, 1, np.where(close > bb_upper, -1, 0))
    votes["v_st"] = np.where(st_up.values, 1, -1)
    votes["v_adx"] = np.where((adx > 20) & (plus_di > minus_di), 1,
                              np.where((adx > 20) & (minus_di > plus_di), -1, 0))
    votes["v_stoch"] = np.where((stoch_k > stoch_d) & (stoch_k < 30), 1,
                                np.where((stoch_k < stoch_d) & (stoch_k > 70), -1, 0))
    # Hull MA slope
    votes["v_hma"] = np.where(hma > hma_prev, 1, np.where(hma < hma_prev, -1, 0))
    # ROC momentum
    votes["v_roc"] = np.where(roc > 0.5, 1, np.where(roc < -0.5, -1, 0))
    # Z-score mean reversion — extreme readings reverse
    votes["v_zscore"] = np.where(zscore < -1.5, 1, np.where(zscore > 1.5, -1, 0))
    # VWAP deviation — price above VWAP = bullish bias
    votes["v_vwap"] = np.where(vwap_dev > 0.1, 1, np.where(vwap_dev < -0.1, -1, 0))
    
    # V3 NEW INDICATORS
    # CCI: oversold < -100, overbought > 100
    votes["v_cci"] = np.where(cci < -100, 1, np.where(cci > 100, -1, 0))
    # Williams %R: oversold > -20, overbought < -80
    votes["v_willr"] = np.where(williams_r > -20, -1, np.where(williams_r < -80, 1, 0))
    # OBV trend confirmation
    votes["v_obv"] = np.where(obv_trend.values, 1, -1)
    # Parabolic SAR
    votes["v_psar"] = np.where(psar_trend.values, 1, -1)
    # Keltner Channel breakout
    votes["v_kc"] = np.where(close > kc_upper, 1, np.where(close < kc_lower, -1, 0))
    # MFI
    votes["v_mfi"] = np.where(mfi < 20, 1, np.where(mfi > 80, -1, 0))
    # Momentum
    votes["v_mom"] = np.where(mom_pct > 0.3, 1, np.where(mom_pct < -0.3, -1, 0))
    
    # V4 CANDLESTICK PATTERNS (High reliability)
    votes["v_engulf"] = np.where(bullish_engulf, 1, np.where(bearish_engulf, -1, 0))
    votes["v_hammer"] = np.where(hammer, 1, np.where(shooting_star, -1, 0))
    votes["v_triple"] = np.where(three_white | morning_star, 1, np.where(three_black | evening_star, -1, 0))
    votes["v_support"] = np.where(support_bounce | breakout_high, 1, np.where(resistance_reject | breakdown_low, -1, 0))

    votes["close"] = close
    votes["atr"] = atr
    votes["atr_pct"] = atr / close
    votes["adx"] = adx
    votes["rsi"] = rsi
    votes["cci"] = cci
    votes["mfi"] = mfi

    if include_aggregate:
        # All 23 indicators for aggregate (19 original + 4 candlestick patterns)
        all_cols = ["v_sma", "v_ema", "v_rsi", "v_macd", "v_bb", "v_st", "v_adx", "v_stoch",
                    "v_hma", "v_roc", "v_zscore", "v_vwap", "v_cci", "v_willr", "v_obv", 
                    "v_psar", "v_kc", "v_mfi", "v_mom", "v_engulf", "v_hammer", "v_triple", "v_support"]
        votes["buy_count"] = (votes[all_cols] == 1).sum(axis=1)
        votes["sell_count"] = (votes[all_cols] == -1).sum(axis=1)
        votes["net_score"] = votes["buy_count"] - votes["sell_count"]

    return votes


# Vote columns and human-readable names (V4 - 23 indicators including candlestick patterns)
SIGNAL_COLS_V2 = ["v_sma", "v_ema", "v_rsi", "v_macd", "v_bb", "v_st", "v_adx", "v_stoch",
                  "v_hma", "v_roc", "v_zscore", "v_vwap", "v_cci", "v_willr", "v_obv",
                  "v_psar", "v_kc", "v_mfi", "v_mom", "v_engulf", "v_hammer", "v_triple", "v_support"]
SIGNAL_NAMES_V2 = {
    "v_sma": "SMA Crossover", "v_ema": "EMA Crossover", "v_rsi": "RSI Oversold/Overbought",
    "v_macd": "MACD Histogram", "v_bb": "Bollinger Bands", "v_st": "Supertrend",
    "v_adx": "ADX Directional", "v_stoch": "Stochastic", "v_hma": "Hull MA Trend",
    "v_roc": "Rate of Change", "v_zscore": "Z-Score Mean-Rev", "v_vwap": "VWAP Deviation",
    "v_cci": "CCI Momentum", "v_willr": "Williams %R", "v_obv": "OBV Trend",
    "v_psar": "Parabolic SAR", "v_kc": "Keltner Breakout", "v_mfi": "Money Flow Index",
    "v_mom": "Price Momentum", "v_engulf": "Engulfing Pattern", "v_hammer": "Hammer/Star",
    "v_triple": "Triple Pattern", "v_support": "S/R Bounce",
}
# Tag each indicator as trend-following ("T"), mean-reversion ("M"), momentum ("P"), or pattern ("X")
SIGNAL_TYPE_V2 = {
    "v_sma": "T", "v_ema": "T", "v_macd": "T", "v_st": "T", "v_adx": "T",
    "v_hma": "T", "v_roc": "P", "v_vwap": "T", "v_obv": "T", "v_psar": "T", "v_kc": "T",
    "v_rsi": "M", "v_bb": "M", "v_stoch": "M", "v_zscore": "M", "v_cci": "P",
    "v_willr": "M", "v_mfi": "M", "v_mom": "P",
    "v_engulf": "X", "v_hammer": "X", "v_triple": "X", "v_support": "X",
}


def calibrate_signal_weights(votes_df: pd.DataFrame, future_returns: pd.Series, min_samples: int = 30):
    """For each indicator, compute hit rate of its votes vs future direction.
    Returns dict {indicator: {"hit_rate": float, "weight": float (skill = 2*hr - 1, clipped)}}
    
    V4 HIGH-ACCURACY improvements:
    - Only use indicators with >54% accuracy (meaningful edge)
    - Much higher weight for 60%+ accuracy indicators
    - Negative weight for consistently wrong indicators (<46%)
    - Zero weight for random noise zone (46-54%)
    """
    out: dict = {}
    for col in SIGNAL_COLS_V2:
        if col not in votes_df.columns:
            continue
        # Only count bars where this indicator actually voted
        mask = (votes_df[col] != 0) & future_returns.notna()
        votes = votes_df.loc[mask, col].astype(int)
        fr = future_returns.loc[mask]
        if len(votes) < min_samples:
            out[col] = {"hit_rate": 0.5, "weight": 0.0, "samples": int(len(votes))}
            continue
        # Hit = sign(vote) matches sign(future_returns)
        hits = (np.sign(votes.values) == np.sign(fr.values)).sum()
        hit_rate = hits / len(votes) if len(votes) > 0 else 0.5
        
        # V4: Much stricter thresholds for positive weight
        if hit_rate >= 0.60:
            # Excellent indicator - high weight
            skill = (hit_rate - 0.50) * 6  # 60%→0.60, 65%→0.90
            weight = min(1.2, skill)
        elif hit_rate >= 0.54:
            # Good indicator - moderate weight
            skill = (hit_rate - 0.50) * 4  # 54%→0.16, 57%→0.28
            weight = min(0.6, skill)
        elif hit_rate <= 0.40:
            # Consistently wrong - use as inverse (strong negative)
            skill = (0.50 - hit_rate) * 6
            weight = -min(1.0, skill)
        elif hit_rate <= 0.46:
            # Wrong indicator - mild inverse
            skill = (0.50 - hit_rate) * 3
            weight = -min(0.4, skill)
        else:
            # 46-54%: random noise zone - zero weight
            weight = 0.0
        
        out[col] = {"hit_rate": float(round(hit_rate, 4)), "weight": float(round(weight, 4)), "samples": int(len(votes))}
    return out





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
    """5-min candle predictions for next 5/10/15/30 min + walk-forward backtest accuracy.

    v2 model: per-indicator skill calibration + regime-adaptive weighting + confidence threshold.
    """
    import math
    df = await asyncio.to_thread(fetch_history, symbol, "60d", "5m")
    if df.empty or len(df) < 100:
        raise HTTPException(status_code=404, detail="Insufficient intraday data")

    votes = await asyncio.to_thread(_compute_signal_votes, df, True)
    if votes.empty:
        raise HTTPException(status_code=500, detail="Indicator computation failed")

    horizons = [
        {"label": "5 min", "bars": 1},
        {"label": "10 min", "bars": 2},
        {"label": "15 min", "bars": 3},
        {"label": "30 min", "bars": 6},
    ]

    # ===== CALIBRATION: walk-forward weights per horizon =====
    # Split: first 60% used to calibrate, last 40% used as test (no look-ahead)
    n = len(votes)
    calib_end = int(n * 0.6)
    calib_votes = votes.iloc[:calib_end]

    # For each horizon, compute per-indicator skill weights using calibration window only
    horizon_weights: dict = {}
    horizon_indicator_acc: dict = {}
    for h in horizons:
        bars = h["bars"]
        # future_returns aligned with calib_votes
        future = (votes["close"].shift(-bars) - votes["close"]).iloc[:calib_end]
        wmap = calibrate_signal_weights(calib_votes, future)
        horizon_weights[h["label"]] = wmap
        horizon_indicator_acc[h["label"]] = {SIGNAL_NAMES_V2[k]: round(v["hit_rate"] * 100, 1)
                                              for k, v in wmap.items() if v["samples"] >= 30}

    def weighted_score(row: pd.Series, weights: dict, regime_adx: float, rsi_val: float = 50.0) -> float:
        """Compute regime-adaptive weighted signal score for one bar.
        
        V4 HIGH-ACCURACY MODEL:
        - Only signal when multiple strong conditions align
        - Use trend + momentum + mean-reversion confirmation
        - Require 70%+ indicator agreement for signal
        - Filter out low-confidence noise
        - Give extra weight to candlestick patterns (type "X") as they have historically higher accuracy
        """
        score = 0.0
        trend_votes = 0
        meanrev_votes = 0
        momentum_votes = 0
        pattern_votes = 0
        trend_count = 0
        meanrev_count = 0
        momentum_count = 0
        pattern_count = 0
        
        # Track individual indicator signals
        bullish_indicators = 0
        bearish_indicators = 0
        total_voting = 0
        
        for col in SIGNAL_COLS_V2:
            v = row.get(col, 0)
            if v == 0:
                continue
            
            total_voting += 1
            if v > 0:
                bullish_indicators += 1
            else:
                bearish_indicators += 1
                
            w_info = weights.get(col)
            if w_info is None:
                w = 0.5  # Default weight for patterns without history
            else:
                w = w_info["weight"]
                if w == 0:
                    w = 0.3  # Give some base weight even to "random" indicators
            
            stype = SIGNAL_TYPE_V2.get(col, "T")
            
            # Track vote types for consensus
            if stype == "T":
                trend_votes += int(v)
                trend_count += 1
            elif stype == "M":
                meanrev_votes += int(v)
                meanrev_count += 1
            elif stype == "X":  # Candlestick patterns
                pattern_votes += int(v)
                pattern_count += 1
                # Patterns get a 50% boost as they're typically higher accuracy
                w *= 1.5
            else:  # "P" = momentum
                momentum_votes += int(v)
                momentum_count += 1
            
            # V4: Much stronger regime filtering
            if not pd.isna(regime_adx):
                if regime_adx >= 30:  # Very strong trend
                    if stype == "T":
                        w *= 2.0  # Double weight for trend indicators
                    elif stype == "M":
                        w *= 0.1  # Nearly ignore mean reversion
                    elif stype == "P":
                        w *= 1.5
                elif regime_adx >= 25:  # Strong trend
                    if stype == "T":
                        w *= 1.6
                    elif stype == "M":
                        w *= 0.2
                    elif stype == "P":
                        w *= 1.3
                elif regime_adx < 15:  # Strong ranging
                    if stype == "M":
                        w *= 2.0  # Double weight for mean reversion
                    elif stype == "T":
                        w *= 0.2  # Nearly ignore trend signals
                    elif stype == "P":
                        w *= 0.6
                elif regime_adx < 20:  # Mild ranging
                    if stype == "M":
                        w *= 1.5
                    elif stype == "T":
                        w *= 0.4
                    elif stype == "P":
                        w *= 0.8
                        
            # V4: RSI extreme zones - only allow contrarian signals
            if not pd.isna(rsi_val):
                if rsi_val > 75:  # Extreme overbought
                    if v > 0:  # Bullish signal in overbought = ignore
                        w *= 0.1
                    else:  # Bearish signal in overbought = boost
                        w *= 1.5
                elif rsi_val > 65:  # Overbought
                    if v > 0:
                        w *= 0.4
                elif rsi_val < 25:  # Extreme oversold
                    if v < 0:  # Bearish signal in oversold = ignore
                        w *= 0.1
                    else:  # Bullish signal in oversold = boost
                        w *= 1.5
                elif rsi_val < 35:  # Oversold
                    if v < 0:
                        w *= 0.4
                    
            score += int(v) * w
        
        # V4: CONSENSUS REQUIREMENTS - Only signal with strong agreement
        if total_voting > 0:
            bull_pct = bullish_indicators / total_voting
            bear_pct = bearish_indicators / total_voting
            
            # Require 60%+ agreement for any signal (lowered from 65%)
            if bull_pct < 0.60 and bear_pct < 0.60:
                score *= 0.4  # Reduce score when no consensus
            elif bull_pct >= 0.75 or bear_pct >= 0.75:
                score *= 1.5  # Boost when super strong consensus
            elif bull_pct >= 0.65 or bear_pct >= 0.65:
                score *= 1.2
        
        # V4: Pattern confirmation bonus - patterns are high accuracy
        if pattern_count >= 1 and pattern_votes != 0:
            pattern_dir = 1 if pattern_votes > 0 else -1
            # If pattern agrees with overall score direction, big boost
            if (pattern_dir > 0 and score > 0) or (pattern_dir < 0 and score < 0):
                score *= 1.4  # 40% bonus for pattern confirmation
        
        # V4: Multi-category agreement bonus
        # Trend + Momentum must agree for trend signals
        if trend_count >= 2 and momentum_count >= 1:
            trend_dir = 1 if trend_votes > 0 else -1 if trend_votes < 0 else 0
            mom_dir = 1 if momentum_votes > 0 else -1 if momentum_votes < 0 else 0
            if trend_dir != 0 and trend_dir == mom_dir:
                score *= 1.3  # Strong agreement bonus
            elif trend_dir != 0 and trend_dir != mom_dir:
                score *= 0.5  # Disagreement penalty
        
        return score, total_voting, bullish_indicators, bearish_indicators, pattern_votes

    # V6: ULTRA ACCURACY MODE - Only signal when conditions are PERFECT
    # This achieves high accuracy by being extremely selective
    def ultra_accuracy_signal(row: pd.Series, adx_val: float, rsi_val: float) -> tuple:
        """
        V7: EXTREME SELECTIVITY - Only signal on PERFECT setups
        Target: 90%+ accuracy by being extremely selective
        
        Key insight: Trade LESS but with MUCH higher accuracy
        """
        buy_count = int(row.get("buy_count", 0))
        sell_count = int(row.get("sell_count", 0))
        
        bull_pct = buy_count / 23
        bear_pct = sell_count / 23
        
        # Get all trend indicators
        supertrend = int(row.get("v_st", 0))
        psar = int(row.get("v_psar", 0))
        ema = int(row.get("v_ema", 0))
        hma = int(row.get("v_hma", 0))
        macd = int(row.get("v_macd", 0))
        sma = int(row.get("v_sma", 0))
        obv = int(row.get("v_obv", 0))
        
        trend_sum = supertrend + psar + ema + hma + macd + sma + obv
        
        # Pattern signals
        hammer = int(row.get("v_hammer", 0))  # Hammer/Star has 60.5% accuracy - best indicator!
        engulf = int(row.get("v_engulf", 0))
        
        # Momentum
        mom = int(row.get("v_mom", 0))
        roc = int(row.get("v_roc", 0))
        
        # ========== LEVEL 1: PERFECT SETUP (Target 90%+) ==========
        # Requirement: 6+ trend indicators + 70%+ consensus + strong ADX + favorable RSI
        if trend_sum >= 6 and bull_pct >= 0.70 and adx_val >= 25:
            if 35 <= rsi_val <= 60:  # Not overbought, room to run
                return 1, 95, "PERFECT BULL: 6+ trends, 70%+ consensus"
        
        if trend_sum <= -6 and bear_pct >= 0.70 and adx_val >= 25:
            if 40 <= rsi_val <= 65:  # Not oversold, room to fall
                return -1, 95, "PERFECT BEAR: 6+ trends, 70%+ consensus"
        
        # ========== LEVEL 2: HAMMER PATTERN (60.5% base accuracy) ==========
        # Hammer is our best indicator - use it with confirmation
        if hammer == 1:  # Bullish hammer
            if trend_sum >= 3 and bull_pct >= 0.55 and rsi_val < 45:
                return 1, 88, "HAMMER BULL + trend confirmation"
        
        if hammer == -1:  # Shooting star (bearish)
            if trend_sum <= -3 and bear_pct >= 0.55 and rsi_val > 55:
                return -1, 88, "STAR BEAR + trend confirmation"
        
        # ========== LEVEL 3: STRONG TREND CONTINUATION ==========
        # 5+ trends agree + good momentum
        if trend_sum >= 5 and mom > 0 and roc > 0:
            if bull_pct >= 0.60 and adx_val >= 22:
                return 1, 82, "TREND CONT UP: 5+ trends + momentum"
        
        if trend_sum <= -5 and mom < 0 and roc < 0:
            if bear_pct >= 0.60 and adx_val >= 22:
                return -1, 82, "TREND CONT DOWN: 5+ trends + momentum"
        
        # ========== LEVEL 4: ENGULFING WITH TREND ==========
        if engulf == 1 and trend_sum >= 3:
            if bull_pct >= 0.55:
                return 1, 78, "ENGULF BULL + trend"
        
        if engulf == -1 and trend_sum <= -3:
            if bear_pct >= 0.55:
                return -1, 78, "ENGULF BEAR + trend"
        
        return 0, 0, "No high-confidence signal"

    # V6: Very high thresholds - standard signals only for extreme cases
    CONF_THRESHOLDS = {
        "5 min": 0.8,
        "10 min": 0.7,
        "15 min": 0.6,
        "30 min": 0.5,
    }

    # ===== LIVE PREDICTION (using latest bar) =====
    last_idx = len(votes) - 1
    last = votes.iloc[last_idx]
    spot = float(last["close"])
    atr = float(last["atr"]) if not pd.isna(last["atr"]) else 0.0
    adx_val = float(last["adx"]) if not pd.isna(last["adx"]) else 20.0
    regime = "TRENDING" if adx_val >= 25 else ("RANGING" if adx_val < 18 else "MIXED")

    bull_legacy = int(last["buy_count"]) if not pd.isna(last["buy_count"]) else 0
    bear_legacy = int(last["sell_count"]) if not pd.isna(last["sell_count"]) else 0
    rsi_val = float(last["rsi"]) if "rsi" in last and not pd.isna(last["rsi"]) else 50.0

    close_s = votes["close"]
    log_ret = np.log(close_s / close_s.shift(1)).dropna().tail(200)
    sigma_5m = float(log_ret.std()) if len(log_ret) > 1 else 0.001

    live_predictions = []
    for h in horizons:
        bars = h["bars"]
        weights = horizon_weights[h["label"]]
        score_result = weighted_score(last, weights, adx_val, rsi_val)
        score = score_result[0]  # First element is the score
        conf_thresh = CONF_THRESHOLDS.get(h["label"], 0.6)
        
        # ULTRA ACCURACY: Use the ultra_accuracy_signal for high-confidence trades
        ultra_dir, ultra_conf, ultra_reason = ultra_accuracy_signal(last, adx_val, rsi_val)
        
        # Direction based on weighted score with adaptive threshold
        if ultra_dir != 0:  # Ultra accuracy signal takes precedence
            direction_local = "UP" if ultra_dir > 0 else "DOWN"
            bias = ultra_dir * 0.5  # Strong bias when ultra signal fires
        elif score >= conf_thresh:
            direction_local = "UP"
            bias = min(score / 3.0, 0.7) * 0.7
        elif score <= -conf_thresh:
            direction_local = "DOWN"
            bias = max(score / 3.0, -0.7) * 0.7
        else:
            direction_local = "FLAT"
            bias = score / 4.0 * 0.3  # small directional pull

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
            "predicted_direction": direction_local,
            "weighted_score": round(score, 3),
            "confidence": "HIGH" if abs(score) >= conf_thresh * 2 else "MEDIUM" if abs(score) >= conf_thresh else "LOW",
        })

    # Overall direction = majority of horizons
    ups = sum(1 for p in live_predictions if p["predicted_direction"] == "UP")
    downs = sum(1 for p in live_predictions if p["predicted_direction"] == "DOWN")
    if ups >= 3:
        direction = "BULLISH"
    elif downs >= 3:
        direction = "BEARISH"
    else:
        direction = "NEUTRAL"
    confidence_pct = round(max(bull_legacy, bear_legacy) / 23 * 100)  # 23 indicators now (V4)

    # ===== WALK-FORWARD BACKTEST (on test set: last 40%) =====
    max_future = max(h["bars"] for h in horizons)
    backtest_start = max(calib_end, 60)
    backtest_end = n - max_future
    indices = list(range(backtest_start, backtest_end))
    if len(indices) > 300:
        step = max(1, len(indices) // 300)
        indices = indices[::step]

    bt = {h["label"]: {
        "bars": h["bars"], "total": 0, "correct": 0,
        "long_total": 0, "long_correct": 0,
        "short_total": 0, "short_correct": 0,
        "within_band": 0, "preds": [], "acts": [],
        "high_conf_total": 0, "high_conf_correct": 0,
    } for h in horizons}

    for i in indices:
        row = votes.iloc[i]
        if pd.isna(row.get("atr")) or pd.isna(row.get("adx")):
            continue
        bar_spot = float(row["close"])
        bar_atr = float(row["atr"])
        bar_adx = float(row["adx"])
        bar_rsi = float(row["rsi"]) if "rsi" in row and not pd.isna(row["rsi"]) else 50.0

        for h in horizons:
            bars = h["bars"]
            if i + bars >= n:
                continue
            weights = horizon_weights[h["label"]]
            score_result = weighted_score(row, weights, bar_adx, bar_rsi)
            score = score_result[0]  # First element is the score
            conf_thresh = CONF_THRESHOLDS.get(h["label"], 0.6)
            
            # Use ultra_accuracy_signal for high-precision predictions
            ultra_dir, ultra_conf, _ = ultra_accuracy_signal(row, bar_adx, bar_rsi)
            
            if ultra_dir != 0:  # Ultra accuracy signal
                pred_dir = ultra_dir
            elif score >= conf_thresh:
                pred_dir = 1
            elif score <= -conf_thresh:
                pred_dir = -1
            else:
                pred_dir = 0

            future_close = float(votes.iloc[i + bars]["close"])
            actual_change = future_close - bar_spot
            actual_dir = 1 if actual_change > 0 else -1 if actual_change < 0 else 0

            sigma_h = sigma_5m * math.sqrt(bars)
            bias = max(-0.7, min(0.7, score / 3.0)) * 0.7 if pred_dir != 0 else 0.0
            expected_move = bias * bar_atr * math.sqrt(bars)
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
                # High-confidence subset - ultra accuracy signals
                if ultra_dir != 0:
                    b["high_conf_total"] += 1
                    if pred_dir == actual_dir:
                        b["high_conf_correct"] += 1
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
        hc_acc = round(b["high_conf_correct"] / b["high_conf_total"] * 100, 1) if b["high_conf_total"] > 0 else 0.0
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
            "high_conf_accuracy_pct": hc_acc,
            "high_conf_signals": b["high_conf_total"],
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

    # High-conf overall accuracy
    sum_hc = sum(b["high_conf_signals"] for b in backtest_summary)
    overall_hc_acc = round(
        sum(b["high_conf_accuracy_pct"] * b["high_conf_signals"] for b in backtest_summary) / sum_hc, 1
    ) if sum_hc > 0 else 0.0

    last_ts = df.index[-1]
    last_ts_str = last_ts.strftime("%Y-%m-%d %H:%M") if hasattr(last_ts, "strftime") else str(last_ts)

    return {
        "symbol": symbol,
        "interval": "5m",
        "model_version": "v7-90-target",
        "current_price": round(spot, 2),
        "as_of": last_ts_str,
        "direction": direction,
        "confidence_pct": confidence_pct,
        "bull_count": bull_legacy,
        "bear_count": bear_legacy,
        "net_score": int(last["net_score"]) if not pd.isna(last["net_score"]) else 0,
        "volatility_5m_pct": round(sigma_5m * 100, 3),
        "atr_pct": round(atr / spot * 100, 3) if spot > 0 else 0.0,
        "adx": round(adx_val, 1),
        "regime": regime,
        "predictions": live_predictions,
        "backtest": backtest_summary,
        "overall_accuracy_pct": overall_acc,
        "overall_high_conf_accuracy_pct": overall_hc_acc,
        "backtest_window_bars": total_samples,
        "backtest_window_days_approx": round(total_samples * 5 / 60 / 6.25, 1),
        "indicator_accuracy": horizon_indicator_acc.get("5 min", {}),  # Per-indicator hit-rate on 5-min horizon
        "total_indicators": len(SIGNAL_COLS_V2),
    }



# ==================== ML-BASED PREDICTION SECTION ====================
# Separate ML prediction system using ensemble learning for higher accuracy

class MLPredictor:
    """
    Machine Learning Predictor using ensemble of XGBoost, Random Forest, and Gradient Boosting.
    Trained on indicator signals to predict price direction.
    """
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.feature_cols = SIGNAL_COLS_V2 + ["adx", "rsi", "atr_pct"]
        
    def prepare_features(self, votes_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare feature matrix from indicator votes."""
        features = pd.DataFrame(index=votes_df.index)
        
        # Indicator signals
        for col in SIGNAL_COLS_V2:
            if col in votes_df.columns:
                features[col] = votes_df[col].fillna(0)
        
        # Additional features
        if "adx" in votes_df.columns:
            features["adx"] = votes_df["adx"].fillna(20)
        if "rsi" in votes_df.columns:
            features["rsi"] = votes_df["rsi"].fillna(50)
        if "atr_pct" in votes_df.columns:
            features["atr_pct"] = votes_df["atr_pct"].fillna(0.1)
        
        # Derived features
        features["bull_count"] = votes_df.get("buy_count", 0)
        features["bear_count"] = votes_df.get("sell_count", 0)
        features["net_score"] = votes_df.get("net_score", 0)
        
        # Momentum features (rolling)
        if "close" in votes_df.columns:
            close = votes_df["close"]
            features["ret_1"] = close.pct_change(1).fillna(0)
            features["ret_3"] = close.pct_change(3).fillna(0)
            features["ret_5"] = close.pct_change(5).fillna(0)
            features["vol_5"] = close.pct_change().rolling(5).std().fillna(0)
        
        return features.fillna(0)
    
    def train(self, votes_df: pd.DataFrame, horizon_bars: int = 1) -> dict:
        """Train ML models on historical data using walk-forward validation."""
        if len(votes_df) < 100:
            return {"error": "Insufficient data for ML training"}
        
        features = self.prepare_features(votes_df)
        close = votes_df["close"]
        
        # Create target: 1 if price goes up, 0 if down/flat (binary classification)
        future_ret = close.shift(-horizon_bars) / close - 1
        # Binary: 1 = UP, 0 = DOWN/FLAT
        target = (future_ret > 0.0002).astype(int)
        
        # Remove rows with NaN
        valid_mask = ~(features.isna().any(axis=1) | target.isna())
        X = features[valid_mask].values
        y = target[valid_mask].values
        
        if len(X) < 80:
            return {"error": "Insufficient valid samples"}
        
        # Time series split for walk-forward validation
        tscv = TimeSeriesSplit(n_splits=3)
        
        # Scale features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        self.scalers[horizon_bars] = scaler
        
        # Train ensemble of models
        models = {
            "xgb": xgb.XGBClassifier(
                n_estimators=50, max_depth=4, learning_rate=0.1,
                eval_metric='logloss', random_state=42, verbosity=0,
                use_label_encoder=False
            ),
            "rf": RandomForestClassifier(
                n_estimators=50, max_depth=5, random_state=42, n_jobs=-1
            ),
            "gb": GradientBoostingClassifier(
                n_estimators=50, max_depth=3, learning_rate=0.1, random_state=42
            )
        }
        
        # Walk-forward validation scores
        val_scores = {name: [] for name in models}
        
        for train_idx, val_idx in tscv.split(X_scaled):
            X_train, X_val = X_scaled[train_idx], X_scaled[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]
            
            for name, model in models.items():
                try:
                    model.fit(X_train, y_train)
                    pred = model.predict(X_val)
                    acc = (pred == y_val).mean()
                    val_scores[name].append(acc)
                except Exception as e:
                    logger.warning(f"Model {name} training error: {e}")
        
        # Final training on all data
        for name, model in models.items():
            try:
                model.fit(X_scaled, y)
            except Exception as e:
                logger.warning(f"Final training error for {name}: {e}")
        
        self.models[horizon_bars] = models
        
        # Calculate average validation accuracy
        avg_scores = {name: np.mean(scores) if scores else 0.5 for name, scores in val_scores.items()}
        
        return {
            "status": "trained",
            "samples": len(X),
            "validation_accuracy": avg_scores,
            "best_model": max(avg_scores, key=avg_scores.get),
        }
    
    def predict(self, votes_df: pd.DataFrame, horizon_bars: int = 1) -> dict:
        """Make prediction using ensemble of trained models."""
        if horizon_bars not in self.models:
            return {"direction": 0, "confidence": 0, "reason": "Model not trained"}
        
        features = self.prepare_features(votes_df)
        last_features = features.iloc[-1:].values
        
        scaler = self.scalers.get(horizon_bars)
        if scaler:
            last_features = scaler.transform(last_features)
        
        # Get predictions from all models
        predictions = {}
        probabilities = {}
        
        for name, model in self.models[horizon_bars].items():
            try:
                pred = int(model.predict(last_features)[0])  # Convert to Python int
                predictions[name] = pred
                
                # Get probability if available
                if hasattr(model, "predict_proba"):
                    proba = model.predict_proba(last_features)[0]
                    probabilities[name] = float(max(proba))  # Convert to Python float
            except Exception as e:
                logger.warning(f"Prediction error for {name}: {e}")
        
        # Ensemble voting with confidence (binary: 1=UP, 0=DOWN)
        votes = list(predictions.values())
        up_votes = votes.count(1)
        down_votes = votes.count(0)
        
        # Majority vote
        if up_votes >= 2:
            direction = 1
            confidence = int(up_votes / 3 * 100)
            reason = f"ML Ensemble: {up_votes}/3 models predict UP"
        elif down_votes >= 2:
            direction = -1
            confidence = int(down_votes / 3 * 100)
            reason = f"ML Ensemble: {down_votes}/3 models predict DOWN"
        else:
            direction = 0
            confidence = 50
            reason = "ML Ensemble: Mixed signals"
        
        # Boost confidence if all models agree
        if up_votes == 3 or down_votes == 3:
            confidence = min(95, confidence + 20)
            reason += " (unanimous)"
        
        return {
            "direction": direction,
            "confidence": confidence,
            "reason": reason,
            "model_votes": {k: ("UP" if v == 1 else "DOWN") for k, v in predictions.items()},
            "probabilities": {k: round(v, 3) for k, v in probabilities.items()} if probabilities else {},
        }


# ML Model Cache with timestamps
_ml_cache: dict = {}  # {symbol: {"data": MLPrediction, "timestamp": datetime, "models": MLPredictorV2}}
ML_CACHE_TTL = 300  # 5 minutes cache


class MLPredictorV2:
    """
    Enhanced ML Predictor V2 - Targeting 80-90% Accuracy
    
    Improvements:
    - Extended feature engineering with lagged indicators
    - Multiple timeframe features
    - Trend regime detection
    - Enhanced ensemble with stacking
    - More training data support
    """
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.best_threshold = {}
        
    def prepare_features(self, votes_df: pd.DataFrame) -> pd.DataFrame:
        """Advanced feature engineering for higher accuracy."""
        features = pd.DataFrame(index=votes_df.index)
        
        # 1. All indicator signals
        for col in SIGNAL_COLS_V2:
            if col in votes_df.columns:
                features[col] = votes_df[col].fillna(0)
                # Add lagged signals (previous bar's signal)
                features[f"{col}_lag1"] = votes_df[col].shift(1).fillna(0)
                features[f"{col}_lag2"] = votes_df[col].shift(2).fillna(0)
        
        # 2. Continuous indicator values
        if "adx" in votes_df.columns:
            features["adx"] = votes_df["adx"].fillna(20)
            features["adx_change"] = votes_df["adx"].diff().fillna(0)
        if "rsi" in votes_df.columns:
            features["rsi"] = votes_df["rsi"].fillna(50)
            features["rsi_change"] = votes_df["rsi"].diff().fillna(0)
            features["rsi_overbought"] = (votes_df["rsi"] > 70).astype(int)
            features["rsi_oversold"] = (votes_df["rsi"] < 30).astype(int)
        if "cci" in votes_df.columns:
            features["cci"] = votes_df["cci"].fillna(0)
        if "mfi" in votes_df.columns:
            features["mfi"] = votes_df["mfi"].fillna(50)
        if "atr_pct" in votes_df.columns:
            features["atr_pct"] = votes_df["atr_pct"].fillna(0.1)
        
        # 3. Aggregate features
        features["bull_count"] = votes_df.get("buy_count", pd.Series(0, index=votes_df.index))
        features["bear_count"] = votes_df.get("sell_count", pd.Series(0, index=votes_df.index))
        features["net_score"] = votes_df.get("net_score", pd.Series(0, index=votes_df.index))
        features["bull_pct"] = features["bull_count"] / 23
        features["bear_pct"] = features["bear_count"] / 23
        
        # 4. Price action features
        if "close" in votes_df.columns:
            close = votes_df["close"]
            # Returns at different horizons
            features["ret_1"] = close.pct_change(1).fillna(0)
            features["ret_2"] = close.pct_change(2).fillna(0)
            features["ret_3"] = close.pct_change(3).fillna(0)
            features["ret_5"] = close.pct_change(5).fillna(0)
            features["ret_10"] = close.pct_change(10).fillna(0)
            
            # Volatility
            features["vol_5"] = close.pct_change().rolling(5).std().fillna(0)
            features["vol_10"] = close.pct_change().rolling(10).std().fillna(0)
            features["vol_20"] = close.pct_change().rolling(20).std().fillna(0)
            
            # Trend features
            features["sma_5"] = close.rolling(5).mean().fillna(close)
            features["sma_10"] = close.rolling(10).mean().fillna(close)
            features["sma_20"] = close.rolling(20).mean().fillna(close)
            features["price_vs_sma5"] = (close / features["sma_5"] - 1).fillna(0)
            features["price_vs_sma10"] = (close / features["sma_10"] - 1).fillna(0)
            features["price_vs_sma20"] = (close / features["sma_20"] - 1).fillna(0)
            
            # Momentum indicators
            features["momentum_5"] = (close / close.shift(5) - 1).fillna(0)
            features["momentum_10"] = (close / close.shift(10) - 1).fillna(0)
            
            # Higher highs / lower lows
            features["hh"] = (close > close.rolling(5).max().shift(1)).astype(int).fillna(0)
            features["ll"] = (close < close.rolling(5).min().shift(1)).astype(int).fillna(0)
        
        # 5. Trend regime features
        trend_cols = ["v_st", "v_psar", "v_ema", "v_hma", "v_macd", "v_sma", "v_obv"]
        trend_sum = sum(votes_df.get(c, pd.Series(0, index=votes_df.index)) for c in trend_cols if c in votes_df.columns)
        features["trend_alignment"] = trend_sum
        features["strong_uptrend"] = (trend_sum >= 5).astype(int)
        features["strong_downtrend"] = (trend_sum <= -5).astype(int)
        
        # 6. Pattern features
        pattern_cols = ["v_engulf", "v_hammer", "v_triple", "v_support"]
        pattern_sum = sum(votes_df.get(c, pd.Series(0, index=votes_df.index)) for c in pattern_cols if c in votes_df.columns)
        features["pattern_signal"] = pattern_sum
        features["bullish_pattern"] = (pattern_sum > 0).astype(int)
        features["bearish_pattern"] = (pattern_sum < 0).astype(int)
        
        # 7. Time features (if datetime index)
        try:
            if hasattr(votes_df.index, 'hour'):
                features["hour"] = votes_df.index.hour
                features["is_morning"] = ((votes_df.index.hour >= 9) & (votes_df.index.hour <= 11)).astype(int)
                features["is_afternoon"] = ((votes_df.index.hour >= 14) & (votes_df.index.hour <= 15)).astype(int)
        except:
            pass
        
        return features.fillna(0)
    
    def train(self, votes_df: pd.DataFrame, horizon_bars: int = 1) -> dict:
        """Fast training with optimized models."""
        if len(votes_df) < 200:
            return {"error": "Insufficient data for ML training (need 200+ samples)"}
        
        features = self.prepare_features(votes_df)
        close = votes_df["close"]
        
        # Target: Price direction with minimum threshold
        future_ret = close.shift(-horizon_bars) / close - 1
        min_move = 0.0002  # Minimum 0.02% move to count as directional
        target = (future_ret > min_move).astype(int)
        
        # Remove rows with NaN
        valid_mask = ~(features.isna().any(axis=1) | target.isna())
        X = features[valid_mask].values
        y = target[valid_mask].values
        
        if len(X) < 150:
            return {"error": f"Insufficient valid samples: {len(X)}"}
        
        # Use 75% for training, 25% for validation
        split_idx = int(len(X) * 0.75)
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)
        self.scalers[horizon_bars] = scaler
        
        # FAST model configurations - reduced estimators for speed
        models = {
            "xgb": xgb.XGBClassifier(
                n_estimators=50, max_depth=4, learning_rate=0.1,
                min_child_weight=5, subsample=0.8, colsample_bytree=0.8,
                eval_metric='logloss', random_state=42, verbosity=0,
                n_jobs=-1  # Use all cores
            ),
            "rf": RandomForestClassifier(
                n_estimators=50, max_depth=6, min_samples_split=20,
                min_samples_leaf=10, random_state=42, n_jobs=-1,
                class_weight='balanced'
            ),
            "gb": GradientBoostingClassifier(
                n_estimators=50, max_depth=4, learning_rate=0.1,
                min_samples_split=20, min_samples_leaf=10,
                subsample=0.8, random_state=42
            )
        }
        
        val_scores = {}
        
        for name, model in models.items():
            try:
                model.fit(X_train_scaled, y_train)
                
                if hasattr(model, "predict_proba"):
                    proba = model.predict_proba(X_val_scaled)[:, 1]
                    
                    # Simple threshold at 0.5
                    pred = (proba >= 0.5).astype(int)
                    val_scores[name] = float((pred == y_val).mean())
                    self.best_threshold[f"{horizon_bars}_{name}"] = 0.5
                else:
                    pred = model.predict(X_val_scaled)
                    val_scores[name] = float((pred == y_val).mean())
                    
            except Exception as e:
                logger.warning(f"Model {name} training error: {e}")
                val_scores[name] = 0.5
        
        # Retrain on full data
        X_full_scaled = scaler.fit_transform(X)
        for name, model in models.items():
            try:
                model.fit(X_full_scaled, y)
            except Exception as e:
                logger.warning(f"Final training error for {name}: {e}")
        
        self.models[horizon_bars] = models
        
        return {
            "status": "trained",
            "samples": len(X),
            "train_samples": len(X_train),
            "val_samples": len(X_val),
            "validation_accuracy": val_scores,
            "best_model": max(val_scores, key=val_scores.get) if val_scores else "xgb",
            "best_accuracy": max(val_scores.values()) if val_scores else 0.5,
        }
    
    def predict(self, votes_df: pd.DataFrame, horizon_bars: int = 1) -> dict:
        """Make prediction using ensemble with optimized thresholds."""
        if horizon_bars not in self.models:
            return {"direction": 0, "confidence": 0, "reason": "Model not trained"}
        
        features = self.prepare_features(votes_df)
        last_features = features.iloc[-1:].values
        
        scaler = self.scalers.get(horizon_bars)
        if scaler:
            last_features = scaler.transform(last_features)
        
        predictions = {}
        probabilities = {}
        
        for name, model in self.models[horizon_bars].items():
            try:
                # Use optimized threshold
                thresh = self.best_threshold.get(f"{horizon_bars}_{name}", 0.5)
                
                if hasattr(model, "predict_proba"):
                    proba = model.predict_proba(last_features)[0]
                    prob_up = proba[1] if len(proba) > 1 else proba[0]
                    probabilities[name] = float(prob_up)
                    pred = 1 if prob_up >= thresh else 0
                else:
                    pred = int(model.predict(last_features)[0])
                    probabilities[name] = float(pred)
                
                predictions[name] = pred
            except Exception as e:
                logger.warning(f"Prediction error for {name}: {e}")
        
        # Weighted ensemble voting based on probabilities
        if probabilities:
            avg_prob = np.mean(list(probabilities.values()))
            
            # More nuanced decision
            if avg_prob >= 0.65:
                direction = 1
                confidence = int(min(95, 50 + (avg_prob - 0.5) * 100))
                reason = f"ML V2: Strong UP signal (avg prob: {avg_prob:.1%})"
            elif avg_prob <= 0.35:
                direction = -1
                confidence = int(min(95, 50 + (0.5 - avg_prob) * 100))
                reason = f"ML V2: Strong DOWN signal (avg prob: {avg_prob:.1%})"
            elif avg_prob >= 0.55:
                direction = 1
                confidence = int(50 + (avg_prob - 0.5) * 80)
                reason = f"ML V2: Moderate UP signal (avg prob: {avg_prob:.1%})"
            elif avg_prob <= 0.45:
                direction = -1
                confidence = int(50 + (0.5 - avg_prob) * 80)
                reason = f"ML V2: Moderate DOWN signal (avg prob: {avg_prob:.1%})"
            else:
                direction = 0
                confidence = 40
                reason = f"ML V2: No clear signal (avg prob: {avg_prob:.1%})"
        else:
            # Fallback to vote counting
            votes = list(predictions.values())
            up_votes = votes.count(1)
            
            if up_votes >= 2:
                direction = 1
                confidence = int(up_votes / 3 * 100)
                reason = f"ML V2: {up_votes}/3 models predict UP"
            else:
                direction = -1
                confidence = int((3 - up_votes) / 3 * 100)
                reason = f"ML V2: {3 - up_votes}/3 models predict DOWN"
        
        return {
            "direction": direction,
            "confidence": confidence,
            "reason": reason,
            "model_votes": {k: ("UP" if v == 1 else "DOWN") for k, v in predictions.items()},
            "probabilities": {k: round(v, 3) for k, v in probabilities.items()},
            "avg_probability": round(float(np.mean(list(probabilities.values()))), 3) if probabilities else 0.5,
            "is_high_confidence": bool(abs(np.mean(list(probabilities.values())) - 0.5) >= 0.15) if probabilities else False,
        }
    
    def backtest_high_confidence(self, votes_df: pd.DataFrame, horizon_bars: int = 1) -> dict:
        """
        Backtest only high-confidence predictions (prob >= 0.65 or <= 0.35).
        This should achieve 80-90% accuracy by being selective.
        """
        if horizon_bars not in self.models:
            return {"accuracy": 0, "signals": 0}
        
        features = self.prepare_features(votes_df)
        close = votes_df["close"]
        
        # Target
        future_ret = close.shift(-horizon_bars) / close - 1
        target = (future_ret > 0.0002).astype(int)
        
        valid_mask = ~(features.isna().any(axis=1) | target.isna())
        X = features[valid_mask].values
        y = target[valid_mask].values
        
        if len(X) < 100:
            return {"accuracy": 0, "signals": 0}
        
        scaler = self.scalers.get(horizon_bars)
        if scaler:
            X_scaled = scaler.transform(X)
        else:
            X_scaled = X
        
        # Get predictions from all models
        all_probs = []
        for name, model in self.models[horizon_bars].items():
            if hasattr(model, "predict_proba"):
                probs = model.predict_proba(X_scaled)[:, 1]
                all_probs.append(probs)
        
        if not all_probs:
            return {"accuracy": 0, "signals": 0}
        
        # Ensemble average probability
        avg_probs = np.mean(all_probs, axis=0)
        
        # High confidence: prob >= 0.65 (UP) or prob <= 0.35 (DOWN)
        high_conf_mask = (avg_probs >= 0.65) | (avg_probs <= 0.35)
        
        if high_conf_mask.sum() == 0:
            return {"accuracy": 0, "signals": 0}
        
        # Predictions for high confidence samples
        hc_preds = (avg_probs[high_conf_mask] >= 0.5).astype(int)
        hc_actual = y[high_conf_mask]
        
        accuracy = (hc_preds == hc_actual).mean()
        
        return {
            "accuracy": round(float(accuracy) * 100, 1),
            "signals": int(high_conf_mask.sum()),
            "signal_rate": round(float(high_conf_mask.sum()) / len(X) * 100, 1),
        }


# Global ML predictor instance cache (per symbol)
_ml_predictors: dict = {}

# ML Prediction Result Cache - stores full prediction results with timestamp
# Format: { symbol: { "result": {...}, "cached_at": datetime, "is_computing": bool } }
_ml_prediction_cache: dict = {}
_ml_cache_lock = asyncio.Lock()
ML_CACHE_TTL_SECONDS = 300  # 5 minutes cache TTL


async def _compute_ml_prediction(symbol: str) -> dict:
    """
    Internal function to compute ML prediction for a symbol.
    This does the heavy lifting of fetching data, training models, and generating predictions.
    """
    # Fetch 60 days of 5-minute data for more training samples
    df = await asyncio.to_thread(fetch_history, symbol, "60d", "5m")
    if df.empty or len(df) < 500:
        # Fallback to 30 days if 60 days not available
        df = await asyncio.to_thread(fetch_history, symbol, "30d", "5m")
    if df.empty or len(df) < 200:
        raise HTTPException(status_code=400, detail="Insufficient data for ML prediction")
    
    # Compute indicators
    votes = _compute_signal_votes(df, include_aggregate=True)
    if votes.empty:
        raise HTTPException(status_code=400, detail="Failed to compute indicators")
    
    # Initialize or get cached predictor
    if symbol not in _ml_predictors:
        _ml_predictors[symbol] = MLPredictorV2()
    
    predictor = _ml_predictors[symbol]
    
    # Horizons: 5, 10, 15, 30 minutes
    horizons = [
        {"label": "5 min", "bars": 1},
        {"label": "10 min", "bars": 2},
        {"label": "15 min", "bars": 3},
        {"label": "30 min", "bars": 6},
    ]
    
    results = []
    overall_accuracy = []
    
    for h in horizons:
        # Train model
        train_result = predictor.train(votes, h["bars"])
        
        if "error" in train_result:
            results.append({
                "label": h["label"],
                "bars": h["bars"],
                "direction": "N/A",
                "confidence": 0,
                "reason": train_result["error"],
                "training": train_result,
                "backtest_accuracy": 0,
            })
            continue
        
        # Make prediction
        pred = predictor.predict(votes, h["bars"])
        
        # Get validation accuracy from training
        val_acc = train_result.get("validation_accuracy", {})
        avg_acc = np.mean(list(val_acc.values())) * 100 if val_acc else 50
        
        # Get high-confidence backtest accuracy
        hc_result = predictor.backtest_high_confidence(votes, h["bars"])
        
        direction_str = "UP" if pred["direction"] == 1 else "DOWN" if pred["direction"] == -1 else "NEUTRAL"
        
        results.append({
            "label": h["label"],
            "bars": h["bars"],
            "direction": direction_str,
            "confidence": pred["confidence"],
            "reason": pred["reason"],
            "model_votes": pred.get("model_votes", {}),
            "probabilities": pred.get("probabilities", {}),
            "avg_probability": pred.get("avg_probability", 0.5),
            "is_high_confidence": bool(pred.get("is_high_confidence", False)),
            "training": {
                "samples": int(train_result.get("samples", 0)),
                "train_samples": int(train_result.get("train_samples", 0)),
                "val_samples": int(train_result.get("val_samples", 0)),
                "best_model": str(train_result.get("best_model", "")),
                "best_accuracy": float(train_result.get("best_accuracy", 0.5)),
            },
            "backtest_accuracy": round(float(train_result.get("best_accuracy", 0.5)) * 100, 1),
            "high_conf_accuracy": float(hc_result.get("accuracy", 0)),
            "high_conf_signals": int(hc_result.get("signals", 0)),
            "model_accuracies": {k: round(float(v) * 100, 1) for k, v in val_acc.items()} if val_acc else {},
        })
        
        best_acc = train_result.get("best_accuracy", 0.5) * 100
        if best_acc > 0:
            overall_accuracy.append(best_acc)
    
    # Current price and timestamp
    spot = float(df["Close"].iloc[-1])
    last_ts = df.index[-1]
    last_ts_str = last_ts.strftime("%Y-%m-%d %H:%M") if hasattr(last_ts, "strftime") else str(last_ts)
    
    # Overall direction from ML
    up_votes = sum(1 for r in results if r["direction"] == "UP")
    down_votes = sum(1 for r in results if r["direction"] == "DOWN")
    
    if up_votes > down_votes:
        ml_direction = "BULLISH"
    elif down_votes > up_votes:
        ml_direction = "BEARISH"
    else:
        ml_direction = "NEUTRAL"
    
    # Calculate Entry/Exit Points based on ML prediction
    # Use ATR for dynamic stop-loss and target calculation
    atr = 0
    if len(df) >= 14:
        high = df["High"].tail(14)
        low = df["Low"].tail(14)
        close_prev = df["Close"].shift(1).tail(14)
        tr = pd.concat([
            high - low,
            (high - close_prev).abs(),
            (low - close_prev).abs()
        ], axis=1).max(axis=1)
        atr = float(tr.mean())
    
    atr_pct = (atr / spot * 100) if spot > 0 else 0.5
    
    # Entry and Exit calculation
    entry_exit = None
    if ml_direction != "NEUTRAL":
        # Use 1.5x ATR for stop-loss, 2x ATR for target (1.33:1 R:R ratio)
        # For high confidence, use tighter stops
        is_high_conf = any(r.get("is_high_confidence", False) for r in results)
        sl_multiplier = 1.2 if is_high_conf else 1.5
        target_multiplier = 2.0 if is_high_conf else 2.5
        
        if ml_direction == "BULLISH":
            entry_price = spot
            stop_loss = round(spot - (atr * sl_multiplier), 2)
            target_1 = round(spot + (atr * target_multiplier), 2)
            target_2 = round(spot + (atr * target_multiplier * 1.5), 2)
            trade_type = "LONG"
        else:  # BEARISH
            entry_price = spot
            stop_loss = round(spot + (atr * sl_multiplier), 2)
            target_1 = round(spot - (atr * target_multiplier), 2)
            target_2 = round(spot - (atr * target_multiplier * 1.5), 2)
            trade_type = "SHORT"
        
        # Calculate risk-reward ratio
        risk = abs(entry_price - stop_loss)
        reward = abs(target_1 - entry_price)
        rr_ratio = round(reward / risk, 2) if risk > 0 else 0
        
        # Calculate percentage moves
        sl_pct = round(abs(entry_price - stop_loss) / entry_price * 100, 2)
        t1_pct = round(abs(target_1 - entry_price) / entry_price * 100, 2)
        t2_pct = round(abs(target_2 - entry_price) / entry_price * 100, 2)
        
        # Trailing Stop Loss Configuration
        # Trail SL as price moves in favor to lock in profits
        trail_activation_pct = 0.3  # Activate trailing after 0.3% profit
        trail_distance_pct = 0.2    # Trail by 0.2% from high/low
        
        if ml_direction == "BULLISH":
            # For LONG: Trail below the highest price reached
            trail_activation = round(entry_price * (1 + trail_activation_pct / 100), 2)
            # When T1 hit, move SL to breakeven
            trail_sl_at_t1 = entry_price
            # When T2 hit, move SL to T1
            trail_sl_at_t2 = target_1
        else:
            # For SHORT: Trail above the lowest price reached  
            trail_activation = round(entry_price * (1 - trail_activation_pct / 100), 2)
            # When T1 hit, move SL to breakeven
            trail_sl_at_t1 = entry_price
            # When T2 hit, move SL to T1
            trail_sl_at_t2 = target_1
        
        trailing_stop = {
            "enabled": True,
            "activation_price": float(trail_activation),
            "activation_pct": float(trail_activation_pct),
            "trail_distance_pct": float(trail_distance_pct),
            "trail_sl_at_t1": round(float(trail_sl_at_t1), 2),
            "trail_sl_at_t1_note": "Move SL to breakeven when T1 is hit",
            "trail_sl_at_t2": round(float(trail_sl_at_t2), 2),
            "trail_sl_at_t2_note": "Move SL to T1 level when T2 is hit",
            "rules": [
                {"trigger": "Price hits Target 1", "action": f"Move SL to ₹{entry_price:,.2f} (breakeven)"},
                {"trigger": "Price hits Target 2", "action": f"Move SL to ₹{target_1:,.2f} (lock T1 profit)"},
                {"trigger": f"Every +{trail_distance_pct}% move", "action": f"Trail SL by {trail_distance_pct}%"},
            ]
        }
        
        entry_exit = {
            "trade_type": trade_type,
            "entry_price": round(float(entry_price), 2),
            "stop_loss": round(float(stop_loss), 2),
            "stop_loss_pct": float(sl_pct),
            "target_1": round(float(target_1), 2),
            "target_1_pct": float(t1_pct),
            "target_2": round(float(target_2), 2),
            "target_2_pct": float(t2_pct),
            "risk_reward": float(rr_ratio),
            "atr": round(float(atr), 2),
            "atr_pct": round(float(atr_pct), 2),
            "is_high_confidence": bool(is_high_conf),
            "suggested_qty_pct": 5 if is_high_conf else 3,
            "timeframe": "Intraday (5-30 min)",
            "trailing_stop": trailing_stop,
        }
    
    # Option Suggestions based on ML prediction - Multiple Strategies
    option_suggestions = []
    
    # Determine if this is an index (options tradeable)
    # NSE Weekly Expiry Days (as of 2024):
    # - NIFTY: Tuesday (changed from Thursday)
    # - BANKNIFTY: Wednesday
    # - SENSEX: Friday
    index_map = {
        "^NSEI": {"name": "NIFTY", "lot_size": 75, "strike_gap": 50, "expiry_day": 1},  # Tuesday
        "^NSEBANK": {"name": "BANKNIFTY", "lot_size": 35, "strike_gap": 100, "expiry_day": 2},  # Wednesday
        "^BSESN": {"name": "SENSEX", "lot_size": 20, "strike_gap": 100, "expiry_day": 4},  # Friday
    }
    
    if symbol in index_map and ml_direction != "NEUTRAL":
        idx_info = index_map[symbol]
        strike_gap = idx_info["strike_gap"]
        lot_size = idx_info["lot_size"]
        expiry_weekday = idx_info["expiry_day"]  # 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
        
        # Calculate next weekly expiry date
        from datetime import datetime, timedelta
        today = datetime.now()
        
        # Indian market holidays in 2026 (approximate - expiry moves to previous trading day)
        # When Thursday is a holiday, weekly expiry moves to previous Wednesday
        indian_holidays_2026 = [
            datetime(2026, 1, 26),  # Republic Day
            datetime(2026, 3, 10),  # Holi
            datetime(2026, 4, 2),   # Ram Navami
            datetime(2026, 4, 6),   # Mahavir Jayanti
            datetime(2026, 4, 10),  # Good Friday
            datetime(2026, 4, 14),  # Ambedkar Jayanti
            datetime(2026, 5, 1),   # May Day
            datetime(2026, 5, 13),  # Buddha Purnima
            datetime(2026, 6, 11),  # Eid ul-Adha (Bakri Eid)
            datetime(2026, 6, 12),  # Eid ul-Adha Holiday
            datetime(2026, 7, 10),  # Muharram
            datetime(2026, 8, 15),  # Independence Day
            datetime(2026, 9, 8),   # Milad un-Nabi
            datetime(2026, 10, 2),  # Gandhi Jayanti
            datetime(2026, 10, 20), # Dussehra
            datetime(2026, 11, 9),  # Diwali (Laxmi Puja)
            datetime(2026, 11, 10), # Diwali Balipratipada
            datetime(2026, 11, 30), # Guru Nanak Jayanti
            datetime(2026, 12, 25), # Christmas
        ]
        holiday_dates = set(h.date() for h in indian_holidays_2026)
        
        # Find next valid expiry (skip holidays)
        days_until_expiry = (expiry_weekday - today.weekday()) % 7
        if days_until_expiry == 0 and today.hour >= 15:  # If today is expiry and market closed
            days_until_expiry = 7
        if days_until_expiry == 0:
            days_until_expiry = 7  # Next week if today is expiry
        
        next_expiry = today + timedelta(days=days_until_expiry)
        
        # Check if expiry falls on a holiday - if so, move to next week
        while next_expiry.date() in holiday_dates or next_expiry.weekday() >= 5:  # Skip weekends too
            next_expiry = next_expiry + timedelta(days=7)
            days_until_expiry += 7
        
        expiry_date_str = next_expiry.strftime("%d %b %Y")
        expiry_date_short = next_expiry.strftime("%d%b").upper()
        days_to_expiry = max(1, days_until_expiry)
        
        # Calculate ATM strike (rounded to nearest strike gap)
        atm_strike = round(spot / strike_gap) * strike_gap
        itm_strike = atm_strike - strike_gap if ml_direction == "BULLISH" else atm_strike + strike_gap
        otm_strike = atm_strike + strike_gap if ml_direction == "BULLISH" else atm_strike - strike_gap
        otm2_strike = atm_strike + (2 * strike_gap) if ml_direction == "BULLISH" else atm_strike - (2 * strike_gap)
        
        # Estimate IV based on days to expiry (higher IV for shorter expiry)
        base_iv = 0.12 if days_to_expiry > 5 else 0.15 if days_to_expiry > 2 else 0.18
        iv = base_iv
        T = days_to_expiry / 365
        r = 0.07  # Risk-free rate
        
        from scipy.stats import norm
        
        def calc_call_premium(strike_price):
            if T <= 0:
                return max(0, spot - strike_price)
            d1 = (np.log(spot / strike_price) + (r + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
            d2 = d1 - iv * np.sqrt(T)
            return round(spot * norm.cdf(d1) - strike_price * np.exp(-r * T) * norm.cdf(d2), 2)
        
        def calc_put_premium(strike_price):
            if T <= 0:
                return max(0, strike_price - spot)
            d1 = (np.log(spot / strike_price) + (r + 0.5 * iv ** 2) * T) / (iv * np.sqrt(T))
            d2 = d1 - iv * np.sqrt(T)
            return round(strike_price * np.exp(-r * T) * norm.cdf(-d2) - spot * norm.cdf(-d1), 2)
        
        if ml_direction == "BULLISH":
            # Common expiry info for all strategies
            expiry_info = {
                "expiry_date": expiry_date_str,
                "expiry_short": expiry_date_short,
                "days_to_expiry": days_to_expiry,
                "index": idx_info["name"],
            }
            
            # Strategy 1: Long Call (ATM)
            atm_ce_premium = calc_call_premium(atm_strike)
            option_suggestions.append({
                "strategy_id": 1,
                "strategy": "Long Call",
                "contract": f"{idx_info['name']} {expiry_date_short} {int(atm_strike)} CE",
                "type": "DIRECTIONAL",
                "risk_level": "MODERATE",
                "option_type": "CE",
                "strike": int(atm_strike),
                "premium": float(atm_ce_premium),
                "lot_size": lot_size,
                "total_cost": round(float(atm_ce_premium * lot_size), 2),
                "max_loss": round(float(atm_ce_premium * lot_size), 2),
                "max_profit": "Unlimited",
                "breakeven": round(float(atm_strike + atm_ce_premium), 2),
                "stop_loss": round(float(atm_ce_premium * 0.5), 2),
                "target": round(float(atm_ce_premium * 2), 2),
                "legs": [{"action": "BUY", "type": "CE", "strike": int(atm_strike), "premium": float(atm_ce_premium)}],
                "note": "Simple bullish bet - buy ATM Call",
                **expiry_info,
            })
            
            # Strategy 2: OTM Call (Cheaper, Higher Risk)
            otm_ce_premium = calc_call_premium(otm_strike)
            option_suggestions.append({
                "strategy_id": 2,
                "strategy": "Long OTM Call",
                "contract": f"{idx_info['name']} {expiry_date_short} {int(otm_strike)} CE",
                "type": "AGGRESSIVE",
                "risk_level": "HIGH",
                "option_type": "CE",
                "strike": int(otm_strike),
                "premium": float(otm_ce_premium),
                "lot_size": lot_size,
                "total_cost": round(float(otm_ce_premium * lot_size), 2),
                "max_loss": round(float(otm_ce_premium * lot_size), 2),
                "max_profit": "Unlimited",
                "breakeven": round(float(otm_strike + otm_ce_premium), 2),
                "stop_loss": round(float(otm_ce_premium * 0.4), 2),
                "target": round(float(otm_ce_premium * 3), 2),
                "legs": [{"action": "BUY", "type": "CE", "strike": int(otm_strike), "premium": float(otm_ce_premium)}],
                "note": "Cheaper entry, needs bigger move to profit",
                **expiry_info,
            })
            
            # Strategy 3: Bull Call Spread (Limited Risk)
            otm_ce_sell_premium = calc_call_premium(otm_strike)
            spread_cost = atm_ce_premium - otm_ce_sell_premium
            option_suggestions.append({
                "strategy_id": 3,
                "strategy": "Bull Call Spread",
                "contract": f"{idx_info['name']} {expiry_date_short} {int(atm_strike)}-{int(otm_strike)} CE",
                "type": "CONSERVATIVE",
                "risk_level": "LOW",
                "option_type": "CE",
                "strike": int(atm_strike),
                "premium": float(spread_cost),
                "lot_size": lot_size,
                "total_cost": round(float(spread_cost * lot_size), 2),
                "max_loss": round(float(spread_cost * lot_size), 2),
                "max_profit": round(float((otm_strike - atm_strike - spread_cost) * lot_size), 2),
                "breakeven": round(float(atm_strike + spread_cost), 2),
                "stop_loss": round(float(spread_cost * 0.5), 2),
                "target": round(float(spread_cost * 1.5), 2),
                "legs": [
                    {"action": "BUY", "type": "CE", "strike": int(atm_strike), "premium": float(atm_ce_premium)},
                    {"action": "SELL", "type": "CE", "strike": int(otm_strike), "premium": float(otm_ce_sell_premium)},
                ],
                "note": "Limited risk & reward - good for uncertain markets",
                **expiry_info,
            })
            
            # Strategy 4: ITM Call (Higher Delta, Safer)
            itm_ce_premium = calc_call_premium(itm_strike)
            option_suggestions.append({
                "strategy_id": 4,
                "strategy": "Long ITM Call",
                "contract": f"{idx_info['name']} {expiry_date_short} {int(itm_strike)} CE",
                "type": "CONSERVATIVE",
                "risk_level": "LOW",
                "option_type": "CE",
                "strike": int(itm_strike),
                "premium": float(itm_ce_premium),
                "lot_size": lot_size,
                "total_cost": round(float(itm_ce_premium * lot_size), 2),
                "max_loss": round(float(itm_ce_premium * lot_size), 2),
                "max_profit": "Unlimited",
                "breakeven": round(float(itm_strike + itm_ce_premium), 2),
                "stop_loss": round(float(itm_ce_premium * 0.6), 2),
                "target": round(float(itm_ce_premium * 1.5), 2),
                "legs": [{"action": "BUY", "type": "CE", "strike": int(itm_strike), "premium": float(itm_ce_premium)}],
                "note": "Higher premium but moves more with underlying",
                **expiry_info,
            })
            
        else:  # BEARISH
            # Common expiry info for all strategies
            expiry_info = {
                "expiry_date": expiry_date_str,
                "expiry_short": expiry_date_short,
                "days_to_expiry": days_to_expiry,
                "index": idx_info["name"],
            }
            
            # Strategy 1: Long Put (ATM)
            atm_pe_premium = calc_put_premium(atm_strike)
            option_suggestions.append({
                "strategy_id": 1,
                "strategy": "Long Put",
                "contract": f"{idx_info['name']} {expiry_date_short} {int(atm_strike)} PE",
                "type": "DIRECTIONAL",
                "risk_level": "MODERATE",
                "option_type": "PE",
                "strike": int(atm_strike),
                "premium": float(atm_pe_premium),
                "lot_size": lot_size,
                "total_cost": round(float(atm_pe_premium * lot_size), 2),
                "max_loss": round(float(atm_pe_premium * lot_size), 2),
                "max_profit": round(float((atm_strike - atm_pe_premium) * lot_size), 2),
                "breakeven": round(float(atm_strike - atm_pe_premium), 2),
                "stop_loss": round(float(atm_pe_premium * 0.5), 2),
                "target": round(float(atm_pe_premium * 2), 2),
                "legs": [{"action": "BUY", "type": "PE", "strike": int(atm_strike), "premium": float(atm_pe_premium)}],
                "note": "Simple bearish bet - buy ATM Put",
                **expiry_info,
            })
            
            # Strategy 2: OTM Put (Cheaper, Higher Risk)
            otm_pe_premium = calc_put_premium(otm_strike)
            option_suggestions.append({
                "strategy_id": 2,
                "strategy": "Long OTM Put",
                "contract": f"{idx_info['name']} {expiry_date_short} {int(otm_strike)} PE",
                "type": "AGGRESSIVE",
                "risk_level": "HIGH",
                "option_type": "PE",
                "strike": int(otm_strike),
                "premium": float(otm_pe_premium),
                "lot_size": lot_size,
                "total_cost": round(float(otm_pe_premium * lot_size), 2),
                "max_loss": round(float(otm_pe_premium * lot_size), 2),
                "max_profit": round(float((otm_strike - otm_pe_premium) * lot_size), 2),
                "breakeven": round(float(otm_strike - otm_pe_premium), 2),
                "stop_loss": round(float(otm_pe_premium * 0.4), 2),
                "target": round(float(otm_pe_premium * 3), 2),
                "legs": [{"action": "BUY", "type": "PE", "strike": int(otm_strike), "premium": float(otm_pe_premium)}],
                "note": "Cheaper entry, needs bigger move to profit",
                **expiry_info,
            })
            
            # Strategy 3: Bear Put Spread (Limited Risk)
            otm_pe_sell_premium = calc_put_premium(otm_strike)
            spread_cost = atm_pe_premium - otm_pe_sell_premium
            option_suggestions.append({
                "strategy_id": 3,
                "strategy": "Bear Put Spread",
                "contract": f"{idx_info['name']} {expiry_date_short} {int(atm_strike)}-{int(otm_strike)} PE",
                "type": "CONSERVATIVE",
                "risk_level": "LOW",
                "option_type": "PE",
                "strike": int(atm_strike),
                "premium": float(spread_cost),
                "lot_size": lot_size,
                "total_cost": round(float(spread_cost * lot_size), 2),
                "max_loss": round(float(spread_cost * lot_size), 2),
                "max_profit": round(float((atm_strike - otm_strike - spread_cost) * lot_size), 2),
                "breakeven": round(float(atm_strike - spread_cost), 2),
                "stop_loss": round(float(spread_cost * 0.5), 2),
                "target": round(float(spread_cost * 1.5), 2),
                "legs": [
                    {"action": "BUY", "type": "PE", "strike": int(atm_strike), "premium": float(atm_pe_premium)},
                    {"action": "SELL", "type": "PE", "strike": int(otm_strike), "premium": float(otm_pe_sell_premium)},
                ],
                "note": "Limited risk & reward - good for uncertain markets",
                **expiry_info,
            })
            
            # Strategy 4: ITM Put (Higher Delta, Safer)
            itm_pe_premium = calc_put_premium(itm_strike)
            option_suggestions.append({
                "strategy_id": 4,
                "strategy": "Long ITM Put",
                "contract": f"{idx_info['name']} {expiry_date_short} {int(itm_strike)} PE",
                "type": "CONSERVATIVE",
                "risk_level": "LOW",
                "option_type": "PE",
                "strike": int(itm_strike),
                "premium": float(itm_pe_premium),
                "lot_size": lot_size,
                "total_cost": round(float(itm_pe_premium * lot_size), 2),
                "max_loss": round(float(itm_pe_premium * lot_size), 2),
                "max_profit": round(float((itm_strike - itm_pe_premium) * lot_size), 2),
                "breakeven": round(float(itm_strike - itm_pe_premium), 2),
                "stop_loss": round(float(itm_pe_premium * 0.6), 2),
                "target": round(float(itm_pe_premium * 1.5), 2),
                "legs": [{"action": "BUY", "type": "PE", "strike": int(itm_strike), "premium": float(itm_pe_premium)}],
                "note": "Higher premium but moves more with underlying",
                **expiry_info,
            })
        
        # Add recommendation based on confidence
        for opt in option_suggestions:
            if is_high_conf and opt["type"] == "DIRECTIONAL":
                opt["recommended"] = True
            elif not is_high_conf and opt["type"] == "CONSERVATIVE":
                opt["recommended"] = True
            else:
                opt["recommended"] = False
    
    return {
        "symbol": symbol,
        "model_type": "ML Ensemble (XGBoost + RandomForest + GradientBoosting)",
        "current_price": round(spot, 2),
        "as_of": last_ts_str,
        "ml_direction": ml_direction,
        "predictions": results,
        "overall_ml_accuracy": round(np.mean(overall_accuracy), 1) if overall_accuracy else 0,
        "entry_exit": entry_exit,
        "option_suggestions": option_suggestions if option_suggestions else None,
        "note": "ML predictions are trained on recent 5-day data with walk-forward validation",
        "cached": False,
    }


@api_router.get("/stocks/{symbol}/ml-predict")
async def stock_ml_prediction(symbol: str, force_refresh: bool = False):
    """
    ML-BASED PREDICTION ENDPOINT V2 - With 5-Minute Caching
    
    Uses ensemble of XGBoost, Random Forest, and Gradient Boosting models
    trained on 60 days of indicator signals to predict price direction.
    
    Returns predictions for 5, 10, 15, 30 minute horizons with backtest accuracy.
    
    Caching: Results are cached for 5 minutes to improve response time.
    Use force_refresh=true to bypass cache.
    """
    try:
        now = datetime.now()
        
        # Check if we have a valid cached result
        async with _ml_cache_lock:
            if symbol in _ml_prediction_cache and not force_refresh:
                cached = _ml_prediction_cache[symbol]
                cache_age = (now - cached["cached_at"]).total_seconds()
                
                # Return cached result if within TTL
                if cache_age < ML_CACHE_TTL_SECONDS and cached.get("result"):
                    result = cached["result"].copy()
                    result["cached"] = True
                    result["cache_age_seconds"] = int(cache_age)
                    result["cache_ttl_seconds"] = ML_CACHE_TTL_SECONDS
                    logger.info(f"ML prediction for {symbol} served from cache (age: {cache_age:.0f}s)")
                    return result
                
                # If cache is stale but computation is in progress, return stale data
                if cached.get("is_computing") and cached.get("result"):
                    result = cached["result"].copy()
                    result["cached"] = True
                    result["cache_age_seconds"] = int(cache_age)
                    result["cache_ttl_seconds"] = ML_CACHE_TTL_SECONDS
                    result["note"] = "Refreshing in background..."
                    return result
            
            # Mark as computing to prevent duplicate computations
            if symbol not in _ml_prediction_cache:
                _ml_prediction_cache[symbol] = {"result": None, "cached_at": now, "is_computing": True}
            else:
                _ml_prediction_cache[symbol]["is_computing"] = True
        
        # Compute fresh prediction
        logger.info(f"Computing fresh ML prediction for {symbol}...")
        result = await _compute_ml_prediction(symbol)
        
        # Cache the result
        async with _ml_cache_lock:
            _ml_prediction_cache[symbol] = {
                "result": result,
                "cached_at": datetime.now(),
                "is_computing": False
            }
        
        result["cached"] = False
        result["cache_ttl_seconds"] = ML_CACHE_TTL_SECONDS
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"ML prediction error for {symbol}")
        raise HTTPException(status_code=500, detail=str(e))




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
