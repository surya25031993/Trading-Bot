"""Backend tests for Algo Trading Bot APIs."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("EXPO_PUBLIC_BACKEND_URL", "https://trading-bot-test-3.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
TIMEOUT = 60


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ------ Market & Stocks ------
def test_root(s):
    r = s.get(f"{API}/", timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


def test_market_indices(s):
    r = s.get(f"{API}/market/indices", timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) == 3
    syms = {d["symbol"] for d in data}
    assert {"^NSEI", "^BSESN", "^NSEBANK"} == syms
    for d in data:
        assert "price" in d and "change_pct" in d


def test_popular_stocks(s):
    r = s.get(f"{API}/stocks/popular", timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list) and len(data) >= 15
    assert all("symbol" in d and "name" in d and "price" in d for d in data)


def test_stock_detail(s):
    r = s.get(f"{API}/stocks/RELIANCE.NS", timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert "quote" in data and "chart" in data
    # chart may occasionally be empty if yfinance rate-limited; tolerate
    assert isinstance(data["chart"], list)


def test_stock_signals(s):
    r = s.get(f"{API}/stocks/RELIANCE.NS/signals", timeout=TIMEOUT)
    # tolerate yfinance failures
    if r.status_code == 404:
        pytest.skip("yfinance no data")
    assert r.status_code == 200
    data = r.json()
    assert "indicators" in data and "signals" in data and "consensus" in data
    names = {x["name"] for x in data["signals"]}
    assert "RSI (14)" in names and "MACD" in names
    assert len(data["signals"]) == 5
    assert data["consensus"] in {"BUY", "SELL", "HOLD"}


def test_signals_top(s):
    r = s.get(f"{API}/signals/top", timeout=TIMEOUT * 2)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    if data:
        assert "consensus" in data[0]


def test_search(s):
    r = s.get(f"{API}/stocks/search", params={"q": "tcs"}, timeout=TIMEOUT)
    assert r.status_code == 200
    data = r.json()
    assert any("TCS" in d["symbol"] for d in data)


# ------ Watchlist ------
def test_watchlist_flow(s):
    # cleanup
    s.delete(f"{API}/watchlist/TEST.NS", timeout=TIMEOUT)
    r = s.post(f"{API}/watchlist", json={"symbol": "TEST.NS", "name": "TEST_Stock"}, timeout=TIMEOUT)
    assert r.status_code == 200
    r = s.get(f"{API}/watchlist", timeout=TIMEOUT)
    assert r.status_code == 200
    syms = [i["symbol"] for i in r.json()]
    assert "TEST.NS" in syms
    r = s.delete(f"{API}/watchlist/TEST.NS", timeout=TIMEOUT)
    assert r.status_code == 200
    r = s.get(f"{API}/watchlist", timeout=TIMEOUT)
    assert "TEST.NS" not in [i["symbol"] for i in r.json()]


# ------ Paper trading & Portfolio ------
def test_reset_then_trade_flow(s):
    r = s.post(f"{API}/portfolio/reset", timeout=TIMEOUT)
    assert r.status_code == 200

    # initial portfolio
    r = s.get(f"{API}/portfolio", timeout=TIMEOUT)
    assert r.status_code == 200
    p = r.json()
    assert p["cash"] == 1_000_000.0
    assert p["positions"] == []

    # BUY
    buy = {"symbol": "RELIANCE.NS", "name": "Reliance", "side": "BUY", "quantity": 10, "price": 1000.0}
    r = s.post(f"{API}/trades/paper", json=buy, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    assert r.json()["cash_remaining"] == 990_000.0

    # verify portfolio
    r = s.get(f"{API}/portfolio", timeout=TIMEOUT)
    p = r.json()
    assert p["cash"] == 990_000.0
    assert len(p["positions"]) == 1
    assert p["positions"][0]["quantity"] == 10

    # Insufficient cash buy
    r = s.post(f"{API}/trades/paper", json={**buy, "quantity": 100000}, timeout=TIMEOUT)
    assert r.status_code == 400

    # Over-sell
    r = s.post(f"{API}/trades/paper", json={**buy, "side": "SELL", "quantity": 999}, timeout=TIMEOUT)
    assert r.status_code == 400

    # Valid SELL
    sell = {**buy, "side": "SELL", "quantity": 5, "price": 1100.0}
    r = s.post(f"{API}/trades/paper", json=sell, timeout=TIMEOUT)
    assert r.status_code == 200
    # 990000 + 5*1100 = 995500
    assert r.json()["cash_remaining"] == 995_500.0

    # trades history
    r = s.get(f"{API}/trades", timeout=TIMEOUT)
    assert r.status_code == 200
    trades = r.json()
    assert len(trades) >= 2

    # cleanup
    s.post(f"{API}/portfolio/reset", timeout=TIMEOUT)


# ------ AI Streaming ------
def test_ai_analyze_stream(s):
    with s.post(f"{API}/ai/analyze", json={"symbol": "RELIANCE.NS"}, stream=True, timeout=120) as r:
        assert r.status_code == 200
        chunks = []
        start = time.time()
        for chunk in r.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                chunks.append(chunk)
            if time.time() - start > 90:
                break
        body = "".join(chunks)
        assert len(body) > 20, f"AI body too short: {body!r}"
