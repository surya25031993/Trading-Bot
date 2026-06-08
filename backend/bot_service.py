"""Auto-trading bot service — scans signals on a loop and places trades."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Single global bot state (one user)
_state = {
    "running": False,
    "mode": "paper",  # "paper" or "live"
    "task": None,
    "started_at": None,
    "stopped_at": None,
    "last_tick": None,
    "stats": {"scans": 0, "buy_orders": 0, "sell_orders": 0, "errors": 0, "last_error": None},
}

# Config (user-tunable via API)
_config = {
    "symbols": ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS"],
    "interval_seconds": 300,  # 5 min between scans
    "max_position_size": 50000.0,  # max ₹ per trade
    "max_trades_per_day": 10,
    "stop_loss_pct": 2.0,  # auto-sell if -2% from entry
    "take_profit_pct": 4.0,  # auto-sell if +4% from entry
    "min_buy_signals": 3,  # need 3+ of 5 algos saying BUY
    "min_sell_signals": 3,
    "trade_qty_mode": "value",  # "value" = ₹-based, "fixed" = fixed qty
    "fixed_qty": 1,
}

# In-memory decision log (last 200 entries)
_decisions: list = []


async def _log_decision(db, entry: dict):
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    _decisions.insert(0, entry)
    if len(_decisions) > 200:
        del _decisions[200:]
    try:
        await db.bot_decisions.insert_one(entry.copy())
    except Exception as e:
        logger.warning(f"Failed to persist decision: {e}")


def get_decisions(limit: int = 50) -> list:
    return _decisions[:limit]


def get_config() -> dict:
    return dict(_config)


def set_config(updates: dict) -> dict:
    allowed = set(_config.keys())
    for k, v in updates.items():
        if k in allowed:
            _config[k] = v
    return get_config()


def get_status() -> dict:
    return {
        "running": _state["running"],
        "mode": _state["mode"],
        "started_at": _state["started_at"],
        "stopped_at": _state["stopped_at"],
        "last_tick": _state["last_tick"],
        "stats": dict(_state["stats"]),
        "config": get_config(),
    }


async def _bot_loop(db, server_module):
    """Main bot loop — runs every interval_seconds, scans signals, trades."""
    logger.info("Bot loop started")
    today_trade_count = 0
    last_date = datetime.now(timezone.utc).date()

    while _state["running"]:
        try:
            now = datetime.now(timezone.utc)
            if now.date() != last_date:
                today_trade_count = 0
                last_date = now.date()

            _state["stats"]["scans"] += 1
            _state["last_tick"] = now.isoformat()

            # Skip if at trade limit
            if today_trade_count >= _config["max_trades_per_day"]:
                logger.info(f"Daily trade limit reached: {today_trade_count}")
                await asyncio.sleep(_config["interval_seconds"])
                continue

            # 1. Stop-loss / take-profit check on existing positions
            await _check_exits(db, server_module)

            # 2. Scan symbols for entry signals
            for symbol in _config["symbols"]:
                if today_trade_count >= _config["max_trades_per_day"]:
                    break
                try:
                    df = await asyncio.to_thread(server_module.fetch_history, symbol, "6mo", "1d")
                    if df.empty:
                        continue
                    ind = await asyncio.to_thread(server_module.compute_indicators, df)
                    if "error" in ind:
                        continue
                    quote = await asyncio.to_thread(server_module.fetch_quote, symbol)
                    price = quote.get("price", 0)
                    if not price:
                        continue

                    # Existing position?
                    port = await db.portfolio.find_one({"user_id": "default_user"})
                    positions = (port or {}).get("positions", {})
                    has_pos = symbol in positions

                    if ind["buy_count"] >= _config["min_buy_signals"] and not has_pos:
                        qty = _calc_qty(price)
                        if qty > 0:
                            await _execute_trade(db, server_module, symbol, "BUY", qty, price, ind)
                            await _log_decision(db, {
                                "symbol": symbol, "action": "BUY", "price": price, "qty": qty,
                                "buy_count": ind["buy_count"], "sell_count": ind["sell_count"],
                                "rsi": ind["indicators"]["rsi"],
                                "reason": f"{ind['buy_count']}/5 algos BUY",
                            })
                            today_trade_count += 1
                    elif ind["sell_count"] >= _config["min_sell_signals"] and has_pos:
                        held_qty = positions[symbol]["quantity"]
                        await _execute_trade(db, server_module, symbol, "SELL", held_qty, price, ind)
                        await _log_decision(db, {
                            "symbol": symbol, "action": "SELL", "price": price, "qty": held_qty,
                            "buy_count": ind["buy_count"], "sell_count": ind["sell_count"],
                            "rsi": ind["indicators"]["rsi"],
                            "reason": f"{ind['sell_count']}/5 algos SELL",
                        })
                        today_trade_count += 1
                    else:
                        await _log_decision(db, {
                            "symbol": symbol, "action": "HOLD", "price": price, "qty": 0,
                            "buy_count": ind["buy_count"], "sell_count": ind["sell_count"],
                            "rsi": ind["indicators"]["rsi"],
                            "reason": f"{ind['buy_count']}B/{ind['sell_count']}S — no consensus" + (" (already holding)" if has_pos else ""),
                        })
                except Exception as e:
                    logger.exception(f"Bot scan error for {symbol}")
                    _state["stats"]["errors"] += 1
                    _state["stats"]["last_error"] = str(e)[:200]

            await asyncio.sleep(_config["interval_seconds"])
        except asyncio.CancelledError:
            logger.info("Bot loop cancelled")
            break
        except Exception as e:
            logger.exception("Bot loop error")
            _state["stats"]["errors"] += 1
            _state["stats"]["last_error"] = str(e)[:200]
            await asyncio.sleep(10)
    logger.info("Bot loop ended")


def _calc_qty(price: float) -> int:
    """Calculate qty based on config."""
    if _config["trade_qty_mode"] == "fixed":
        return _config["fixed_qty"]
    max_value = _config["max_position_size"]
    return max(1, int(max_value // price))


async def _execute_trade(db, server_module, symbol, side, qty, price, ind):
    """Execute paper or live trade."""
    pos_data = await db.portfolio.find_one({"user_id": "default_user"})
    if not pos_data:
        await db.portfolio.insert_one({"user_id": "default_user", "cash": 1_000_000.0, "positions": {}})
        pos_data = {"cash": 1_000_000.0, "positions": {}}

    name = symbol.replace(".NS", "").replace(".BO", "")
    total = qty * price

    # Place paper trade (always — this is our internal ledger)
    body = server_module.PaperTradeRequest(
        symbol=symbol, name=name, side=side, quantity=qty, price=price
    )
    try:
        await server_module.place_paper_trade(body)
        if side == "BUY":
            _state["stats"]["buy_orders"] += 1
        else:
            _state["stats"]["sell_orders"] += 1
        logger.info(f"[BOT {_state['mode']}] {side} {qty} {symbol} @ ₹{price:.2f} (signals: {ind['buy_count']}B/{ind['sell_count']}S)")
    except Exception as e:
        logger.warning(f"Paper trade failed: {e}")
        _state["stats"]["errors"] += 1
        return

    # If live mode + fyers connected, also place real order
    if _state["mode"] == "live":
        try:
            import fyers_integration as fyers_int
            client = await fyers_int.get_client(db)
            if client:
                fyers_symbol = f"NSE:{name}-EQ"
                order_req = fyers_int.FyersOrderRequest(
                    symbol=fyers_symbol, qty=qty, side=side,
                    order_type="MARKET", product_type="INTRADAY",
                )
                await asyncio.to_thread(fyers_int.place_order_sync, client, order_req)
                logger.info(f"[BOT LIVE] Fyers order placed: {side} {qty} {fyers_symbol}")
            else:
                logger.warning("Live mode but Fyers not connected — only paper trade logged")
        except Exception as e:
            logger.exception(f"Fyers order failed for {symbol}")
            _state["stats"]["errors"] += 1
            _state["stats"]["last_error"] = f"Fyers: {str(e)[:200]}"


async def _check_exits(db, server_module):
    """Auto-exit positions hitting stop-loss or take-profit."""
    port = await db.portfolio.find_one({"user_id": "default_user"})
    if not port:
        return
    positions = port.get("positions", {})
    for symbol, pos in list(positions.items()):
        try:
            quote = await asyncio.to_thread(server_module.fetch_quote, symbol)
            cur_price = quote.get("price", 0)
            if not cur_price:
                continue
            entry = pos["avg_price"]
            pnl_pct = (cur_price - entry) / entry * 100
            if pnl_pct <= -_config["stop_loss_pct"]:
                logger.info(f"[BOT EXIT] Stop-loss hit on {symbol}: {pnl_pct:.2f}%")
                await _execute_trade(db, server_module, symbol, "SELL", pos["quantity"], cur_price,
                                     {"buy_count": 0, "sell_count": 99})
                await _log_decision(db, {
                    "symbol": symbol, "action": "SELL", "price": cur_price, "qty": pos["quantity"],
                    "buy_count": 0, "sell_count": 0, "rsi": 0,
                    "reason": f"STOP-LOSS hit ({pnl_pct:.2f}%)",
                })
            elif pnl_pct >= _config["take_profit_pct"]:
                logger.info(f"[BOT EXIT] Take-profit hit on {symbol}: {pnl_pct:.2f}%")
                await _execute_trade(db, server_module, symbol, "SELL", pos["quantity"], cur_price,
                                     {"buy_count": 0, "sell_count": 99})
                await _log_decision(db, {
                    "symbol": symbol, "action": "SELL", "price": cur_price, "qty": pos["quantity"],
                    "buy_count": 0, "sell_count": 0, "rsi": 0,
                    "reason": f"TAKE-PROFIT hit (+{pnl_pct:.2f}%)",
                })
        except Exception as e:
            logger.warning(f"Exit check failed for {symbol}: {e}")


async def start(db, server_module, mode: str = "paper") -> dict:
    if _state["running"]:
        return {"ok": False, "message": "Bot already running"}
    _state["mode"] = "live" if mode == "live" else "paper"
    _state["running"] = True
    _state["started_at"] = datetime.now(timezone.utc).isoformat()
    _state["stopped_at"] = None
    _state["stats"] = {"scans": 0, "buy_orders": 0, "sell_orders": 0, "errors": 0, "last_error": None}
    _state["task"] = asyncio.create_task(_bot_loop(db, server_module))
    return {"ok": True, "running": True, "mode": _state["mode"]}


async def stop() -> dict:
    if not _state["running"]:
        return {"ok": False, "message": "Bot not running"}
    _state["running"] = False
    _state["stopped_at"] = datetime.now(timezone.utc).isoformat()
    task = _state.get("task")
    if task and not task.done():
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    _state["task"] = None
    return {"ok": True, "running": False}
