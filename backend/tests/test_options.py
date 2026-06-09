"""Backend tests for Options trading APIs (iteration 2)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://repo-ui-restore.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TIMEOUT = 60


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ------ Strategy templates ------
def test_options_strategies(s):
    r = s.get(f"{API}/options/strategies", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    keys = {d["key"] for d in data}
    expected = {"LONG_CALL", "LONG_PUT", "BULL_CALL_SPREAD", "BEAR_PUT_SPREAD",
                "IRON_CONDOR", "LONG_STRADDLE", "SHORT_STRANGLE"}
    assert expected.issubset(keys), f"missing strategy keys: {expected - keys}"
    for d in data:
        assert "name" in d and "view" in d and "legs" in d
        assert isinstance(d["legs"], list) and len(d["legs"]) >= 1


# ------ Suggest endpoint per-index ------
@pytest.mark.parametrize("index,expected_lot", [
    ("NIFTY", 75),
    ("SENSEX", 20),
    ("BANKNIFTY", 35),
])
def test_options_suggest(s, index, expected_lot):
    r = s.get(f"{API}/options/suggest", params={"index": index}, timeout=TIMEOUT)
    if r.status_code == 503:
        pytest.skip(f"yfinance data unavailable for {index}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["index"] == index
    assert d["lot_size"] == expected_lot
    assert isinstance(d["spot"], (int, float)) and d["spot"] > 0
    assert isinstance(d["atm"], (int, float)) and d["atm"] > 0
    assert d["consensus"] in {"BUY", "SELL", "HOLD"}
    assert isinstance(d["rsi"], (int, float))
    assert "strategy" in d and d["strategy"]["name"]
    legs = d["concrete_legs"]
    assert isinstance(legs, list) and 1 <= len(legs) <= 5
    for leg in legs:
        assert leg["side"] in {"BUY", "SELL"}
        assert leg["type"] in {"CE", "PE"}
        assert isinstance(leg["strike"], (int, float)) and leg["strike"] > 0
        assert isinstance(leg["premium_est"], (int, float)) and leg["premium_est"] >= 0
        assert isinstance(leg["qty"], int) and leg["qty"] >= 1


def test_options_suggest_bad_index(s):
    r = s.get(f"{API}/options/suggest", params={"index": "FOOBAR"}, timeout=TIMEOUT)
    assert r.status_code == 400


# ------ Calculate ------
def test_options_calculate_iron_condor(s):
    # Build a simple Iron Condor on NIFTY around 22000 spot
    payload = {
        "index": "NIFTY",
        "spot": 22000,
        "days_to_expiry": 7,
        "iv": 15,
        "legs": [
            {"side": "SELL", "type": "CE", "strike": 22200, "premium": 80, "qty": 1},
            {"side": "BUY",  "type": "CE", "strike": 22400, "premium": 30, "qty": 1},
            {"side": "SELL", "type": "PE", "strike": 21800, "premium": 80, "qty": 1},
            {"side": "BUY",  "type": "PE", "strike": 21600, "premium": 30, "qty": 1},
        ],
    }
    r = s.post(f"{API}/options/calculate", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["lot_size"] == 75
    assert isinstance(d["payoff"], list) and 60 <= len(d["payoff"]) <= 100
    for p in d["payoff"][:3]:
        assert "spot" in p and "pnl" in p
    assert "max_profit" in d and "max_loss" in d
    assert isinstance(d["breakevens"], list)
    g = d["greeks"]
    for k in ("delta", "gamma", "theta", "vega"):
        assert k in g
    assert "probability_of_profit_pct" in d
    assert "net_premium" in d


def test_options_calculate_long_call(s):
    payload = {
        "index": "NIFTY", "spot": 22000, "days_to_expiry": 7, "iv": 15,
        "legs": [{"side": "BUY", "type": "CE", "strike": 22000, "premium": 150, "qty": 1}],
    }
    r = s.post(f"{API}/options/calculate", json=payload, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    # Long call: max loss = -premium*lot
    assert d["max_loss"] is not None and d["max_loss"] < 0
    # Net premium should be negative (debit)
    assert d["net_premium"] < 0


# ------ Chain (best-effort) ------
def test_options_chain_either_outcome(s):
    r = s.get(f"{API}/options/chain", params={"index": "NIFTY"}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "available" in d
    if d["available"]:
        assert "chain" in d and isinstance(d["chain"], list)
    else:
        assert "reason" in d  # expected when NSE blocks server IPs
