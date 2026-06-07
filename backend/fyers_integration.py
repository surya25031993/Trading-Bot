"""Fyers Securities API v3 integration — OAuth, live data, option chain, orders."""
from __future__ import annotations
import os
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List

import httpx
from fyers_apiv3 import fyersModel
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def _app_id() -> str:
    return os.environ.get("FYERS_APP_ID", "")


def _secret() -> str:
    return os.environ.get("FYERS_SECRET_KEY", "")


def _redirect() -> str:
    return os.environ.get("FYERS_REDIRECT_URL", "")


DEFAULT_USER = "default_user"

# Fyers index/spot symbol mapping
INDEX_SYMBOL = {
    "NIFTY": "NSE:NIFTY50-INDEX",
    "SENSEX": "BSE:SENSEX-INDEX",
    "BANKNIFTY": "NSE:NIFTYBANK-INDEX",
    "FINNIFTY": "NSE:FINNIFTY-INDEX",
}

REFRESH_URL = "https://api-t1.fyers.in/api/v3/validate-refresh-token"


def is_configured() -> bool:
    return bool(_app_id() and _secret() and _redirect())


def get_login_url() -> str:
    """Generate Fyers OAuth login URL."""
    session = fyersModel.SessionModel(
        client_id=_app_id(),
        secret_key=_secret(),
        redirect_uri=_redirect(),
        response_type="code",
        grant_type="authorization_code",
        state=DEFAULT_USER,
    )
    return session.generate_authcode()


async def exchange_auth_code(db, auth_code: str) -> dict:
    """Exchange auth_code for access_token + refresh_token and store in DB."""
    session = fyersModel.SessionModel(
        client_id=_app_id(),
        secret_key=_secret(),
        redirect_uri=_redirect(),
        response_type="code",
        grant_type="authorization_code",
    )
    session.set_token(auth_code)
    resp = session.generate_token()
    if not resp or resp.get("s") != "ok":
        raise ValueError(f"Fyers token exchange failed: {resp}")

    access_token = resp["access_token"]
    refresh_token = resp.get("refresh_token", "")
    now = datetime.now(timezone.utc)

    doc = {
        "user_id": DEFAULT_USER,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "access_expires_at": (now + timedelta(hours=24)).isoformat(),
        "refresh_expires_at": (now + timedelta(days=15)).isoformat(),
        "updated_at": now.isoformat(),
    }
    await db.fyers_tokens.update_one(
        {"user_id": DEFAULT_USER},
        {"$set": doc},
        upsert=True,
    )
    return {"connected": True, "expires_in_hours": 24}


async def get_token_record(db) -> Optional[dict]:
    rec = await db.fyers_tokens.find_one({"user_id": DEFAULT_USER}, {"_id": 0})
    return rec


async def get_status(db) -> dict:
    rec = await get_token_record(db)
    if not rec:
        return {"connected": False}
    now = datetime.now(timezone.utc)
    try:
        exp = datetime.fromisoformat(rec["access_expires_at"])
    except Exception:
        exp = now - timedelta(seconds=1)
    valid = exp > now
    return {
        "connected": valid,
        "access_expires_at": rec.get("access_expires_at"),
        "refresh_expires_at": rec.get("refresh_expires_at"),
        "needs_relogin": not valid,
    }


async def disconnect(db) -> dict:
    await db.fyers_tokens.delete_one({"user_id": DEFAULT_USER})
    return {"ok": True}


async def _refresh_token(db, pin: str) -> str:
    rec = await get_token_record(db)
    if not rec or not rec.get("refresh_token"):
        raise ValueError("No refresh token available")
    input_str = f"{_app_id()}:{_secret()}"
    sha256_hash = hashlib.sha256(input_str.encode()).hexdigest()
    payload = {
        "grant_type": "refresh_token",
        "appIdHash": sha256_hash,
        "refresh_token": rec["refresh_token"],
        "pin": pin,
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(REFRESH_URL, json=payload)
    data = resp.json()
    if data.get("s") != "ok":
        raise ValueError(f"Refresh failed: {data.get('message') or data}")
    access_token = data["access_token"]
    now = datetime.now(timezone.utc)
    await db.fyers_tokens.update_one(
        {"user_id": DEFAULT_USER},
        {"$set": {
            "access_token": access_token,
            "access_expires_at": (now + timedelta(hours=24)).isoformat(),
            "updated_at": now.isoformat(),
        }},
    )
    return access_token


async def get_client(db) -> Optional[fyersModel.FyersModel]:
    """Return a FyersModel client if access token is valid, else None."""
    rec = await get_token_record(db)
    if not rec:
        return None
    try:
        exp = datetime.fromisoformat(rec["access_expires_at"])
    except Exception:
        return None
    if exp <= datetime.now(timezone.utc):
        return None
    return fyersModel.FyersModel(
        client_id=_app_id(),
        token=rec["access_token"],
        is_async=False,
        log_path="/tmp",
    )


# ============ Data Operations ============
def fetch_quotes_sync(client: fyersModel.FyersModel, symbols: List[str]) -> List[dict]:
    """Fetch live quotes for one or more Fyers symbols. Returns normalized list."""
    if not symbols:
        return []
    payload = {"symbols": ",".join(symbols)}
    resp = client.quotes(data=payload)
    if resp.get("s") != "ok":
        logger.warning(f"fyers quotes error: {resp}")
        return []
    out = []
    for item in resp.get("d", []):
        v = item.get("v") or {}
        out.append({
            "symbol": item.get("n", v.get("symbol", "")),
            "price": v.get("lp", 0),
            "change": v.get("ch", 0),
            "change_pct": v.get("chp", 0),
            "volume": v.get("volume", 0),
            "day_high": v.get("high_price", 0),
            "day_low": v.get("low_price", 0),
        })
    return out


def fetch_option_chain_sync(client: fyersModel.FyersModel, index: str, strike_count: int = 10) -> dict:
    """Fetch live option chain for an index (NIFTY/SENSEX/BANKNIFTY)."""
    sym = INDEX_SYMBOL.get(index.upper())
    if not sym:
        return {"available": False, "reason": "Unknown index"}
    payload = {"symbol": sym, "strikecount": strike_count, "timestamp": ""}
    resp = client.optionchain(data=payload)
    if resp.get("s") != "ok":
        return {"available": False, "reason": resp.get("message", "Fyers option chain error")}
    data = resp.get("data") or {}
    options = data.get("optionsChain", [])
    expiry_list = data.get("expiryData", [])
    expiry = expiry_list[0]["date"] if expiry_list else ""
    # Group by strike
    by_strike: dict = {}
    spot = 0.0
    for o in options:
        if o.get("option_type") == "":
            spot = o.get("ltp", spot)
            continue
        strike = o.get("strike_price", 0)
        side = "CE" if o.get("option_type") == "CE" else "PE"
        if strike not in by_strike:
            by_strike[strike] = {"strike": strike}
        by_strike[strike][f"{side.lower()}_ltp"] = o.get("ltp", 0)
        by_strike[strike][f"{side.lower()}_oi"] = o.get("oi", 0)
        by_strike[strike][f"{side.lower()}_volume"] = o.get("volume", 0)
        by_strike[strike][f"{side.lower()}_symbol"] = o.get("symbol", "")
    chain = sorted(by_strike.values(), key=lambda x: x["strike"])
    atm = min((c["strike"] for c in chain), key=lambda s: abs(s - spot)) if chain and spot else 0
    return {
        "available": True,
        "index": index.upper(),
        "spot": spot,
        "atm": atm,
        "expiry": expiry,
        "chain": chain,
    }


def get_funds_sync(client: fyersModel.FyersModel) -> dict:
    resp = client.funds()
    if resp.get("s") != "ok":
        return {"error": resp.get("message", "Unknown error")}
    return resp.get("fund_limit", [])


def get_holdings_sync(client: fyersModel.FyersModel) -> dict:
    resp = client.holdings()
    if resp.get("s") != "ok":
        return {"error": resp.get("message", "Unknown error")}
    return {
        "holdings": resp.get("holdings", []),
        "overall": resp.get("overall", {}),
    }


def get_positions_sync(client: fyersModel.FyersModel) -> dict:
    resp = client.positions()
    if resp.get("s") != "ok":
        return {"error": resp.get("message", "Unknown error")}
    return {
        "net_positions": resp.get("netPositions", []),
        "overall": resp.get("overall", {}),
    }


def get_profile_sync(client: fyersModel.FyersModel) -> dict:
    resp = client.get_profile()
    if resp.get("s") != "ok":
        return {"error": resp.get("message", "Unknown error")}
    return resp.get("data", {})


# ============ Order Placement ============
class FyersOrderRequest(BaseModel):
    symbol: str  # Fyers format e.g. "NSE:RELIANCE-EQ" or "NSE:NIFTY25FEB23400CE"
    qty: int
    side: str  # "BUY" or "SELL"
    order_type: str = "MARKET"  # "MARKET" or "LIMIT"
    product_type: str = "INTRADAY"  # CNC, INTRADAY, MARGIN
    limit_price: float = 0.0
    stop_price: float = 0.0


def place_order_sync(client: fyersModel.FyersModel, order: FyersOrderRequest) -> dict:
    side_value = 1 if order.side.upper() == "BUY" else -1
    type_map = {"MARKET": 2, "LIMIT": 1, "STOP": 3, "STOPLIMIT": 4}
    type_value = type_map.get(order.order_type.upper(), 2)
    product_map = {"CNC": "CNC", "INTRADAY": "INTRADAY", "MIS": "INTRADAY", "MARGIN": "MARGIN"}
    product = product_map.get(order.product_type.upper(), "INTRADAY")
    payload = {
        "symbol": order.symbol,
        "qty": order.qty,
        "type": type_value,
        "side": side_value,
        "productType": product,
        "limitPrice": order.limit_price,
        "stopPrice": order.stop_price,
        "disclosedQty": 0,
        "validity": "DAY",
        "offlineOrder": False,
        "orderTag": "AlgoBot",
    }
    resp = client.place_order(data=payload)
    return resp
