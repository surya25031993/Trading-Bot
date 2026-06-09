"""Signal Bot — one-tap per-prediction execution.

Spawned from the ML Predict screen. Each instance manages a single trade:
- places the entry (paper or live)
- ticks the price every TICK_SECONDS
- auto-exits at Stop Loss / Target 1 / Target 2
- applies trailing-SL logic (move SL to BE after T1, lock T1 after T2)
- persists state in MongoDB collection `signal_bot_trades`
"""
from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

TICK_SECONDS = 15

# In-process registry of running bots so we can stop/list them quickly.
_running: dict = {}  # trade_id -> asyncio.Task


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _persist(db, trade: dict):
    await db.signal_bot_trades.update_one(
        {"id": trade["id"]}, {"$set": trade}, upsert=True
    )


async def _live_price(server_module, db, symbol: str) -> Optional[float]:
    """Fetch the live price — Fyers first, yfinance fallback."""
    try:
        import fyers_integration as fyers_int
        fy_sym = server_module._yf_to_fyers_symbol(symbol)
        if fy_sym:
            client = await fyers_int.get_client(db)
            if client:
                quotes = await asyncio.to_thread(
                    fyers_int.fetch_quotes_sync, client, [fy_sym]
                )
                if quotes and quotes[0].get("price"):
                    return float(quotes[0]["price"])
    except Exception as e:
        logger.warning(f"SignalBot: fyers price for {symbol} failed: {e}")
    # Fallback to yfinance (cached, 30s ttl)
    try:
        q = await asyncio.to_thread(server_module.fetch_quote, symbol)
        return float(q.get("price") or 0) or None
    except Exception:
        return None


async def _place_entry(db, server_module, trade: dict) -> bool:
    """Place paper trade and (if live) a real Fyers order."""
    symbol = trade["symbol"]
    side = "BUY" if trade["trade_type"] == "LONG" else "SELL"
    qty = trade["qty"]
    price = trade["entry_price"]
    # Always log a paper trade as our internal ledger
    name = symbol.replace(".NS", "").replace(".BO", "").replace("^", "")
    try:
        body = server_module.PaperTradeRequest(
            symbol=symbol, name=name, side="BUY" if side == "BUY" else "SELL",
            quantity=qty, price=price,
        )
        await server_module.place_paper_trade(body)
    except Exception as e:
        logger.warning(f"SignalBot: paper entry failed: {e}")
        # For SHORT we still try to record the position; if it failed, abort.
        if trade["trade_type"] == "LONG":
            return False

    if trade["mode"] == "live":
        try:
            import fyers_integration as fyers_int
            client = await fyers_int.get_client(db)
            if client:
                fy_sym = server_module._yf_to_fyers_symbol(symbol)
                if fy_sym:
                    order = fyers_int.FyersOrderRequest(
                        symbol=fy_sym, qty=qty, side=side,
                        order_type="MARKET", product_type="INTRADAY",
                    )
                    resp = await asyncio.to_thread(fyers_int.place_order_sync, client, order)
                    trade["fyers_order_id"] = (resp or {}).get("id") or (resp or {}).get("orderId")
                    logger.info(f"SignalBot LIVE entry: {side} {qty} {fy_sym} → {resp}")
            else:
                trade["events"].append({
                    "t": _now_iso(),
                    "msg": "Live mode requested but Fyers not connected — paper-only entry recorded.",
                })
        except Exception as e:
            logger.exception("SignalBot: Fyers entry failed")
            trade["events"].append({"t": _now_iso(), "msg": f"Fyers entry error: {e}"})
    return True


async def _place_exit(db, server_module, trade: dict, exit_price: float, reason: str):
    symbol = trade["symbol"]
    qty = trade["qty"]
    # Opposite side to close
    close_side = "SELL" if trade["trade_type"] == "LONG" else "BUY"
    name = symbol.replace(".NS", "").replace(".BO", "").replace("^", "")
    try:
        body = server_module.PaperTradeRequest(
            symbol=symbol, name=name, side=close_side,
            quantity=qty, price=exit_price,
        )
        await server_module.place_paper_trade(body)
    except Exception as e:
        logger.warning(f"SignalBot: paper exit failed: {e}")

    if trade["mode"] == "live":
        try:
            import fyers_integration as fyers_int
            client = await fyers_int.get_client(db)
            if client:
                fy_sym = server_module._yf_to_fyers_symbol(symbol)
                if fy_sym:
                    order = fyers_int.FyersOrderRequest(
                        symbol=fy_sym, qty=qty, side=close_side,
                        order_type="MARKET", product_type="INTRADAY",
                    )
                    await asyncio.to_thread(fyers_int.place_order_sync, client, order)
                    logger.info(f"SignalBot LIVE exit: {close_side} {qty} {fy_sym}")
        except Exception as e:
            logger.exception("SignalBot: Fyers exit failed")
            trade["events"].append({"t": _now_iso(), "msg": f"Fyers exit error: {e}"})

    # Compute PnL
    entry = trade["entry_price"]
    if trade["trade_type"] == "LONG":
        pnl = (exit_price - entry) * qty
    else:
        pnl = (entry - exit_price) * qty
    pnl_pct = (pnl / (entry * qty) * 100) if entry and qty else 0
    trade["status"] = "CLOSED"
    trade["exit_price"] = round(exit_price, 2)
    trade["exit_reason"] = reason
    trade["closed_at"] = _now_iso()
    trade["pnl"] = round(pnl, 2)
    trade["pnl_pct"] = round(pnl_pct, 2)
    trade["events"].append({
        "t": _now_iso(),
        "msg": f"CLOSED via {reason} @ ₹{exit_price:.2f}  → PnL ₹{pnl:.2f} ({pnl_pct:+.2f}%)",
    })
    await _persist(db, trade)


async def _bot_loop(db, server_module, trade_id: str):
    """Per-trade monitor loop."""
    try:
        trade = await db.signal_bot_trades.find_one({"id": trade_id}, {"_id": 0})
        if not trade:
            return

        # Place entry
        trade["events"].append({"t": _now_iso(), "msg": f"Bot started in {trade['mode'].upper()} mode."})
        ok = await _place_entry(db, server_module, trade)
        if not ok:
            trade["status"] = "FAILED"
            trade["events"].append({"t": _now_iso(), "msg": "Entry rejected — bot stopped."})
            await _persist(db, trade)
            return
        trade["status"] = "OPEN"
        trade["events"].append({
            "t": _now_iso(),
            "msg": f"Entered {trade['trade_type']} {trade['qty']} @ ₹{trade['entry_price']:.2f}",
        })
        await _persist(db, trade)

        long_side = trade["trade_type"] == "LONG"
        # Mutable SL — moves with trailing logic
        current_sl = trade["stop_loss"]
        t1 = trade["target_1"]
        t2 = trade["target_2"]
        hit_t1 = False
        hit_t2 = False
        peak = trade["entry_price"]  # high (for LONG) or low (for SHORT) since entry
        trail_distance_pct = trade.get("trail_distance_pct", 0.2)

        while True:
            await asyncio.sleep(TICK_SECONDS)
            # Re-load (so external stop can take effect)
            current = await db.signal_bot_trades.find_one({"id": trade_id}, {"_id": 0})
            if not current or current.get("status") != "OPEN":
                logger.info(f"SignalBot {trade_id} no longer OPEN, ending loop.")
                return

            price = await _live_price(server_module, db, trade["symbol"])
            if price is None:
                continue

            trade["last_price"] = round(price, 2)
            trade["last_tick"] = _now_iso()

            # Track peak for trailing
            if long_side:
                if price > peak:
                    peak = price
            else:
                if price < peak:
                    peak = price

            # Trailing SL once T1 hit (BE) or T2 hit (lock T1)
            if hit_t2:
                # Trail by trail_distance_pct from peak, but never below the locked level (t1)
                if long_side:
                    trail_sl = peak * (1 - trail_distance_pct / 100)
                    new_sl = max(current_sl, trail_sl, t1)
                else:
                    trail_sl = peak * (1 + trail_distance_pct / 100)
                    new_sl = min(current_sl, trail_sl, t1)
                if new_sl != current_sl:
                    current_sl = round(new_sl, 2)
                    trade["stop_loss_current"] = current_sl
                    trade["events"].append({"t": _now_iso(), "msg": f"Trailing SL → ₹{current_sl:.2f}"})

            # Check exits
            if long_side:
                if price <= current_sl:
                    await _place_exit(db, server_module, trade, price, "STOP_LOSS")
                    return
                if not hit_t1 and price >= t1:
                    hit_t1 = True
                    current_sl = trade["entry_price"]  # move SL to BE
                    trade["stop_loss_current"] = current_sl
                    trade["events"].append({"t": _now_iso(), "msg": f"Target 1 hit @ ₹{price:.2f} — SL moved to breakeven."})
                if not hit_t2 and price >= t2:
                    hit_t2 = True
                    current_sl = t1  # lock T1
                    trade["stop_loss_current"] = current_sl
                    trade["events"].append({"t": _now_iso(), "msg": f"Target 2 hit @ ₹{price:.2f} — SL locked at T1 (₹{t1:.2f}). Trailing active."})
            else:  # SHORT
                if price >= current_sl:
                    await _place_exit(db, server_module, trade, price, "STOP_LOSS")
                    return
                if not hit_t1 and price <= t1:
                    hit_t1 = True
                    current_sl = trade["entry_price"]
                    trade["stop_loss_current"] = current_sl
                    trade["events"].append({"t": _now_iso(), "msg": f"Target 1 hit @ ₹{price:.2f} — SL moved to breakeven."})
                if not hit_t2 and price <= t2:
                    hit_t2 = True
                    current_sl = t1
                    trade["stop_loss_current"] = current_sl
                    trade["events"].append({"t": _now_iso(), "msg": f"Target 2 hit @ ₹{price:.2f} — SL locked at T1 (₹{t1:.2f}). Trailing active."})

            await _persist(db, trade)

    except asyncio.CancelledError:
        logger.info(f"SignalBot {trade_id} cancelled")
        raise
    except Exception as e:
        logger.exception(f"SignalBot {trade_id} crashed")
        try:
            t = await db.signal_bot_trades.find_one({"id": trade_id}, {"_id": 0})
            if t:
                t["status"] = "ERROR"
                t["error"] = str(e)[:300]
                t["events"].append({"t": _now_iso(), "msg": f"Bot crashed: {e}"})
                await _persist(db, t)
        except Exception:
            pass
    finally:
        _running.pop(trade_id, None)


async def start_from_prediction(db, server_module, symbol: str, mode: str = "paper") -> dict:
    """Spawn a Signal Bot from the latest ML prediction for `symbol`."""
    pred = await server_module._compute_ml_prediction(symbol)
    ee = pred.get("entry_exit")
    if not ee or pred.get("ml_direction") == "NEUTRAL":
        return {"ok": False, "reason": "No actionable signal (ML direction NEUTRAL)."}

    qty = max(1, int(ee.get("suggested_qty_pct", 3)))  # crude: use suggested_qty_pct as qty
    trade = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "mode": "live" if mode == "live" else "paper",
        "trade_type": ee["trade_type"],
        "qty": qty,
        "entry_price": float(ee["entry_price"]),
        "stop_loss": float(ee["stop_loss"]),
        "stop_loss_current": float(ee["stop_loss"]),
        "target_1": float(ee["target_1"]),
        "target_2": float(ee["target_2"]),
        "trail_distance_pct": float(
            (ee.get("trailing_stop") or {}).get("trail_distance_pct", 0.2)
        ),
        "ml_direction": pred["ml_direction"],
        "ml_confidence": pred.get("predictions", [{}])[0].get("confidence"),
        "price_source": pred.get("price_source", "yfinance"),
        "status": "PENDING_ENTRY",
        "opened_at": _now_iso(),
        "closed_at": None,
        "exit_price": None,
        "exit_reason": None,
        "pnl": None,
        "pnl_pct": None,
        "last_price": float(ee["entry_price"]),
        "last_tick": None,
        "events": [],
    }
    await _persist(db, trade)
    task = asyncio.create_task(_bot_loop(db, server_module, trade["id"]))
    _running[trade["id"]] = task
    return {"ok": True, "trade_id": trade["id"], "trade": trade}


async def stop_trade(db, server_module, trade_id: str) -> dict:
    trade = await db.signal_bot_trades.find_one({"id": trade_id}, {"_id": 0})
    if not trade:
        return {"ok": False, "reason": "Trade not found"}
    if trade["status"] != "OPEN":
        # Just cancel any pending task and mark closed if not already
        task = _running.pop(trade_id, None)
        if task and not task.done():
            task.cancel()
        if trade["status"] == "PENDING_ENTRY":
            trade["status"] = "CANCELLED"
            trade["closed_at"] = _now_iso()
            trade["events"].append({"t": _now_iso(), "msg": "Cancelled before entry."})
            await _persist(db, trade)
        return {"ok": True, "trade": trade}

    # Force-exit at market
    price = await _live_price(server_module, db, trade["symbol"]) or trade["entry_price"]
    await _place_exit(db, server_module, trade, price, "MANUAL_STOP")
    task = _running.pop(trade_id, None)
    if task and not task.done():
        task.cancel()
    trade = await db.signal_bot_trades.find_one({"id": trade_id}, {"_id": 0})
    return {"ok": True, "trade": trade}


async def list_trades(db, limit: int = 50) -> list:
    cursor = db.signal_bot_trades.find({}, {"_id": 0}).sort("opened_at", -1).limit(limit)
    return [t async for t in cursor]


async def get_trade(db, trade_id: str) -> Optional[dict]:
    return await db.signal_bot_trades.find_one({"id": trade_id}, {"_id": 0})
