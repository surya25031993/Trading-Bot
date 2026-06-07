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
    {"symbol": "TATAMOTORS.NS", "name": "Tata Motors"},
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

    # Overall consensus
    buys = sum(1 for s in signals if s["action"] == "BUY")
    sells = sum(1 for s in signals if s["action"] == "SELL")
    if buys > sells and buys >= 2:
        consensus = "BUY"
    elif sells > buys and sells >= 2:
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
