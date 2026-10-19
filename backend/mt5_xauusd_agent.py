"""MT5 XAUUSD signal-only agent.

Reads live candles from a locally running MetaTrader 5 terminal and emits
BUY / SELL / WAIT suggestions. It NEVER sends an order.
"""
import argparse
import json
import time
from datetime import datetime, timezone

import MetaTrader5 as mt5
import pandas as pd

TF = {"M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15}


def ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def atr(df, n=14):
    prev = df.close.shift(1)
    tr = pd.concat([(df.high-df.low).abs(), (df.high-prev).abs(), (df.low-prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def candles(symbol, timeframe, count=250):
    rates = mt5.copy_rates_from_pos(symbol, TF[timeframe], 0, count)
    if rates is None or len(rates) < 60:
        raise RuntimeError(f"Not enough {timeframe} data for {symbol}: {mt5.last_error()}")
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df["ema20"] = ema(df.close, 20)
    df["ema50"] = ema(df.close, 50)
    df["atr14"] = atr(df)
    return df


def trend(df):
    x = df.iloc[-2]  # last CLOSED candle
    if x.close > x.ema20 > x.ema50:
        return "bullish"
    if x.close < x.ema20 < x.ema50:
        return "bearish"
    return "mixed"


def analyse(symbol):
    m5, m15 = candles(symbol, "M5"), candles(symbol, "M15")
    c = m5.iloc[-2]
    prior = m5.iloc[-22:-2]
    resistance = float(prior.high.max())
    support = float(prior.low.min())
    a = float(c.atr14)
    t5, t15 = trend(m5), trend(m15)

    signal, reason = "WAIT", "No confirmed multi-timeframe breakout."
    entry = sl = tp1 = tp2 = None

    # Closed-candle breakout + M5/M15 alignment. Conservative by design.
    if t5 == t15 == "bullish" and c.close > resistance:
        signal = "BUY"
        entry = float(c.close)
        sl = entry - 1.2 * a
        risk = entry - sl
        tp1, tp2 = entry + 1.5 * risk, entry + 2.0 * risk
        reason = "M5/M15 bullish alignment with a closed-candle breakout."
    elif t5 == t15 == "bearish" and c.close < support:
        signal = "SELL"
        entry = float(c.close)
        sl = entry + 1.2 * a
        risk = sl - entry
        tp1, tp2 = entry - 1.5 * risk, entry - 2.0 * risk
        reason = "M5/M15 bearish alignment with a closed-candle breakdown."

    tick = mt5.symbol_info_tick(symbol)
    price = float(tick.bid) if tick else float(m5.iloc[-1].close)
    confidence = 75 if signal != "WAIT" else (55 if t5 == t15 and t5 != "mixed" else 40)
    return {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol, "price": round(price, 3), "signal": signal,
        "m5_trend": t5, "m15_trend": t15, "confidence": confidence,
        "support": round(support, 3), "resistance": round(resistance, 3),
        "entry": round(entry, 3) if entry else None,
        "stop_loss": round(sl, 3) if sl else None,
        "tp1": round(tp1, 3) if tp1 else None,
        "tp2": round(tp2, 3) if tp2 else None,
        "reason": reason,
        "execution": "SIGNAL_ONLY"
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default="XAUUSD")
    p.add_argument("--interval", type=int, default=10)
    p.add_argument("--once", action="store_true")
    args = p.parse_args()

    if not mt5.initialize():
        raise SystemExit(f"MT5 initialize failed: {mt5.last_error()}. Open/login to MT5 first.")
    try:
        if not mt5.symbol_select(args.symbol, True):
            raise SystemExit(f"Cannot select {args.symbol}. Your broker may use XAUUSDm/XAUUSD.a; pass --symbol.")
        while True:
            try:
                print(json.dumps(analyse(args.symbol), indent=2), flush=True)
            except Exception as e:
                print(json.dumps({"signal":"ERROR", "error":str(e)}), flush=True)
            if args.once:
                break
            time.sleep(max(args.interval, 5))
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
