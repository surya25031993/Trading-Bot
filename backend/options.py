"""Options trading module — strategy suggester, Black-Scholes calculator, NSE chain (best-effort)."""
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import List, Optional, Literal

from pydantic import BaseModel
import numpy as np
from scipy.stats import norm

# Indian index lot sizes (current as of 2025; user can override in UI)
LOT_SIZE = {"NIFTY": 75, "BANKNIFTY": 35, "SENSEX": 20, "FINNIFTY": 65}

# Map index name → underlying yfinance symbol
INDEX_SYMBOL = {"NIFTY": "^NSEI", "SENSEX": "^BSESN", "BANKNIFTY": "^NSEBANK"}


# ============ Black-Scholes ============
def _d1(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return 0.0
    return (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))


def bs_price(S, K, T, r, sigma, opt: str) -> float:
    """Black-Scholes price. S spot, K strike, T years, r risk-free, sigma vol, opt 'CE' or 'PE'."""
    if T <= 0:
        return max(0.0, (S - K) if opt == "CE" else (K - S))
    d1 = _d1(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    if opt == "CE":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_greeks(S, K, T, r, sigma, opt: str) -> dict:
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    d1 = _d1(S, K, T, r, sigma)
    d2 = d1 - sigma * math.sqrt(T)
    pdf = norm.pdf(d1)
    if opt == "CE":
        delta = norm.cdf(d1)
        theta = -(S * pdf * sigma) / (2 * math.sqrt(T)) - r * K * math.exp(-r * T) * norm.cdf(d2)
    else:
        delta = norm.cdf(d1) - 1
        theta = -(S * pdf * sigma) / (2 * math.sqrt(T)) + r * K * math.exp(-r * T) * norm.cdf(-d2)
    gamma = pdf / (S * sigma * math.sqrt(T))
    vega = S * pdf * math.sqrt(T)
    return {
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta / 365, 4),  # per day
        "vega": round(vega / 100, 4),    # per 1% vol move
    }


# ============ Strategy templates ============
STRATEGIES = {
    "LONG_CALL": {
        "name": "Long Call",
        "view": "Strongly Bullish",
        "risk": "Limited (premium paid)",
        "reward": "Unlimited",
        "description": "Buy 1 ATM Call. Profits if index rallies above strike + premium.",
        "legs": [{"side": "BUY", "type": "CE", "strike_offset": 0, "qty": 1}],
    },
    "LONG_PUT": {
        "name": "Long Put",
        "view": "Strongly Bearish",
        "risk": "Limited (premium paid)",
        "reward": "Large (until index → 0)",
        "description": "Buy 1 ATM Put. Profits if index falls below strike − premium.",
        "legs": [{"side": "BUY", "type": "PE", "strike_offset": 0, "qty": 1}],
    },
    "BULL_CALL_SPREAD": {
        "name": "Bull Call Spread",
        "view": "Moderately Bullish",
        "risk": "Limited (net debit)",
        "reward": "Limited (spread width − debit)",
        "description": "Buy ATM Call, Sell OTM Call (+200 pts). Lower cost, capped upside.",
        "legs": [
            {"side": "BUY", "type": "CE", "strike_offset": 0, "qty": 1},
            {"side": "SELL", "type": "CE", "strike_offset": 200, "qty": 1},
        ],
    },
    "BEAR_PUT_SPREAD": {
        "name": "Bear Put Spread",
        "view": "Moderately Bearish",
        "risk": "Limited (net debit)",
        "reward": "Limited (spread width − debit)",
        "description": "Buy ATM Put, Sell OTM Put (−200 pts). Lower cost, capped downside.",
        "legs": [
            {"side": "BUY", "type": "PE", "strike_offset": 0, "qty": 1},
            {"side": "SELL", "type": "PE", "strike_offset": -200, "qty": 1},
        ],
    },
    "IRON_CONDOR": {
        "name": "Iron Condor",
        "view": "Sideways / Low Volatility",
        "risk": "Limited",
        "reward": "Limited (net credit received)",
        "description": "Sell OTM Call & OTM Put, buy further OTM Call & Put as hedge. Profits if index stays in a range.",
        "legs": [
            {"side": "SELL", "type": "CE", "strike_offset": 200, "qty": 1},
            {"side": "BUY", "type": "CE", "strike_offset": 400, "qty": 1},
            {"side": "SELL", "type": "PE", "strike_offset": -200, "qty": 1},
            {"side": "BUY", "type": "PE", "strike_offset": -400, "qty": 1},
        ],
    },
    "LONG_STRADDLE": {
        "name": "Long Straddle",
        "view": "Big Move Expected (direction unclear)",
        "risk": "Limited (both premiums)",
        "reward": "Unlimited (either direction)",
        "description": "Buy ATM Call AND ATM Put. Profits on a big move either side. Good before events.",
        "legs": [
            {"side": "BUY", "type": "CE", "strike_offset": 0, "qty": 1},
            {"side": "BUY", "type": "PE", "strike_offset": 0, "qty": 1},
        ],
    },
    "SHORT_STRANGLE": {
        "name": "Short Strangle",
        "view": "Range-bound, low volatility expected",
        "risk": "Unlimited (advanced)",
        "reward": "Limited (premiums received)",
        "description": "Sell OTM Call (+300) AND OTM Put (−300). Earns theta if index stays in range. RISKY.",
        "legs": [
            {"side": "SELL", "type": "CE", "strike_offset": 300, "qty": 1},
            {"side": "SELL", "type": "PE", "strike_offset": -300, "qty": 1},
        ],
    },
}


def suggest_strategy(consensus: str, rsi: float, change_pct: float) -> dict:
    """Map index technical view → recommended option strategy."""
    if consensus == "BUY" and rsi < 70:
        key = "BULL_CALL_SPREAD" if rsi > 55 else "LONG_CALL"
    elif consensus == "SELL" and rsi > 30:
        key = "BEAR_PUT_SPREAD" if rsi < 45 else "LONG_PUT"
    elif consensus == "HOLD" and 40 < rsi < 60:
        key = "IRON_CONDOR"
    elif abs(change_pct) > 1.5:
        key = "LONG_STRADDLE"
    else:
        key = "IRON_CONDOR"
    s = STRATEGIES[key].copy()
    s["key"] = key
    return s


# ============ Payoff Calculator ============
class OptionLeg(BaseModel):
    side: Literal["BUY", "SELL"]
    type: Literal["CE", "PE"]
    strike: float
    premium: float
    qty: int = 1  # in lots


class CalcRequest(BaseModel):
    index: Literal["NIFTY", "SENSEX", "BANKNIFTY", "FINNIFTY"]
    spot: float
    days_to_expiry: int
    iv: float = 15.0  # implied vol in %
    legs: List[OptionLeg]


def _leg_payoff_at(leg: OptionLeg, S_at_expiry: float, lot: int) -> float:
    intrinsic = max(0.0, (S_at_expiry - leg.strike) if leg.type == "CE" else (leg.strike - S_at_expiry))
    pnl_per_unit = (intrinsic - leg.premium) if leg.side == "BUY" else (leg.premium - intrinsic)
    return pnl_per_unit * leg.qty * lot


def calculate_payoff(req: CalcRequest) -> dict:
    lot = LOT_SIZE.get(req.index, 75)
    spot = req.spot
    # Build expiry payoff curve from -10% to +10% of spot
    low = spot * 0.90
    high = spot * 1.10
    xs = np.linspace(low, high, 80)
    ys = []
    for S in xs:
        total = sum(_leg_payoff_at(leg, float(S), lot) for leg in req.legs)
        ys.append(round(total, 2))

    max_profit = float(max(ys))
    max_loss = float(min(ys))

    # Find breakevens (sign changes)
    breakevens = []
    for i in range(1, len(ys)):
        if (ys[i - 1] <= 0 <= ys[i]) or (ys[i - 1] >= 0 >= ys[i]):
            if ys[i] == ys[i - 1]:
                continue
            x = xs[i - 1] + (xs[i] - xs[i - 1]) * (-ys[i - 1] / (ys[i] - ys[i - 1]))
            breakevens.append(round(float(x), 2))

    # Net debit / credit
    net = 0.0
    for leg in req.legs:
        c = leg.premium * leg.qty * lot
        net += -c if leg.side == "BUY" else c  # debit negative

    # Greeks summed across legs (today)
    T = max(req.days_to_expiry / 365.0, 0.001)
    sigma = req.iv / 100.0
    r = 0.07  # ~RBI repo
    total_greeks = {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    for leg in req.legs:
        g = bs_greeks(spot, leg.strike, T, r, sigma, leg.type)
        mult = leg.qty * lot * (1 if leg.side == "BUY" else -1)
        for k in total_greeks:
            total_greeks[k] += g[k] * mult

    pop = _probability_of_profit(spot, sigma, T, breakevens, ys)

    return {
        "lot_size": lot,
        "net_premium": round(net, 2),
        "max_profit": round(max_profit, 2) if max_profit < 1e9 else None,
        "max_loss": round(max_loss, 2) if max_loss > -1e9 else None,
        "breakevens": breakevens,
        "payoff": [{"spot": round(float(x), 2), "pnl": round(float(y), 2)} for x, y in zip(xs, ys)],
        "greeks": {k: round(v, 4) for k, v in total_greeks.items()},
        "probability_of_profit_pct": pop,
    }


def _probability_of_profit(spot, sigma, T, breakevens, ys):
    """Rough P(profit) using lognormal distribution under BS assumptions."""
    if T <= 0 or sigma <= 0:
        return None
    # Use empirical curve: estimate that ~ +/- 1 sigma move is sigma * sqrt(T)
    # Better: monte carlo
    try:
        rng = np.random.default_rng(42)
        samples = spot * np.exp((-0.5 * sigma ** 2) * T + sigma * math.sqrt(T) * rng.standard_normal(2000))
        # interpolate payoff at samples (the ys array is over linear xs)
        # Recompute payoff vectorized by interpolation
        xs_arr = np.linspace(spot * 0.90, spot * 1.10, len(ys))
        clipped = np.clip(samples, xs_arr.min(), xs_arr.max())
        sim_pnl = np.interp(clipped, xs_arr, ys)
        prob = float((sim_pnl > 0).mean() * 100)
        return round(prob, 1)
    except Exception:
        return None


# ============ Option Chain (best-effort) ============
def fetch_option_chain(index: str) -> dict:
    """Best-effort NSE option chain. NSE often blocks server IPs."""
    try:
        from nsepython import nse_optionchain_scrapper
        data = nse_optionchain_scrapper(index)
        if not data or "records" not in data:
            return {"available": False, "reason": "NSE blocked or no data"}
        rec = data["records"]
        expiries = rec.get("expiryDates", [])
        if not expiries:
            return {"available": False, "reason": "No expiry data"}
        first_expiry = expiries[0]
        rows = [r for r in rec.get("data", []) if r.get("expiryDate") == first_expiry]
        spot = rec.get("underlyingValue", 0)
        # ATM and ±10 strikes
        strikes = sorted(set(r["strikePrice"] for r in rows))
        atm = min(strikes, key=lambda s: abs(s - spot)) if strikes else 0
        atm_idx = strikes.index(atm) if atm in strikes else 0
        chosen = strikes[max(0, atm_idx - 10): atm_idx + 11]
        out = []
        for k in chosen:
            row = next((r for r in rows if r["strikePrice"] == k), None)
            if not row:
                continue
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            out.append({
                "strike": k,
                "ce_ltp": ce.get("lastPrice", 0),
                "ce_oi": ce.get("openInterest", 0),
                "ce_iv": ce.get("impliedVolatility", 0),
                "pe_ltp": pe.get("lastPrice", 0),
                "pe_oi": pe.get("openInterest", 0),
                "pe_iv": pe.get("impliedVolatility", 0),
            })
        return {"available": True, "expiry": first_expiry, "spot": spot, "atm": atm, "chain": out}
    except Exception as e:
        return {"available": False, "reason": str(e)[:200]}
