"""VULCAN â€” Alpaca data client. Single source of truth for market data (data hygiene)."""
import os
import time
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

API_KEY = os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("ALPACA_SECRET")
PAPER = os.getenv("ALPACA_PAPER", "true").lower() == "true"
BASE = "https://paper-api.alpaca.markets" if PAPER else "https://api.alpaca.markets"
DATA = "https://data.alpaca.markets"


def _get(url: str, params: dict | None = None, retries: int = 4) -> dict:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last_err = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url)
            req.add_header("APCA-API-KEY-ID", API_KEY)
            req.add_header("APCA-API-SECRET-KEY", API_SECRET)
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET failed {url}: {last_err}")


def _post(url: str, body: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST")
    req.add_header("APCA-API-KEY-ID", API_KEY)
    req.add_header("APCA-API-SECRET-KEY", API_SECRET)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:500]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


# ---------- account ----------
def get_account() -> dict:
    return _get(f"{BASE}/v2/account")


def get_positions() -> list:
    return _get(f"{BASE}/v2/positions")


# ---------- stock bars ----------
def get_bars(symbol: str = "SPY", days: int = 400, timeframe: str = "1Day") -> list:
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    page = None
    while True:
        params = {
            "symbols": symbol,
            "timeframe": timeframe,
            "start": start,
            "limit": 10000,
            "feed": "iex",
        }
        if page:
            params["page_token"] = page
        resp = _get(f"{DATA}/v2/stocks/bars", params)
        bars = resp.get("bars", {})
        if isinstance(bars, dict):
            out.extend(bars.get(symbol, []))
        else:
            out.extend(bars)
        page = resp.get("next_page_token")
        if not page:
            break
    return out


def get_latest_quote(symbol: str = "SPY") -> dict:
    return _get(f"{DATA}/v2/stocks/{symbol}/trades/latest", {"feed": "iex"})


# ---------- options ----------
def get_option_chain(underlying: str = "SPY", expiration: str | None = None) -> list:
    """Fetch option snapshots (IV + greeks) for one underlying, optionally one expiration.

    Returns list of {symbol, expiration_date, strike_price, ...snapshot fields}.
    """
    params = {"limit": 1000}
    if expiration:
        params["expiration_date"] = expiration
    out = []
    page = None
    while True:
        if page:
            params["page_token"] = page
        resp = _get(f"{DATA}/v1beta1/options/snapshots/{underlying}", params)
        snaps = resp.get("snapshots", [])
        for contract_symbol, snap in snaps.items():
            snap["symbol"] = contract_symbol
            out.append(snap)
        page = resp.get("next_page_token")
        if not page:
            break
    return out


# ---------- orders ----------
def submit_order(order: dict) -> dict:
    return _post(f"{BASE}/v2/orders", order)


def cancel_all_orders():
    req = urllib.request.Request(f"{BASE}/v2/orders", method="DELETE")
    req.add_header("APCA-API-KEY-ID", API_KEY)
    req.add_header("APCA-API-SECRET-KEY", API_SECRET)
    urllib.request.urlopen(req, timeout=30).read()


def get_open_orders() -> list:
    return _get(f"{BASE}/v2/orders", {"status": "open", "limit": 100})


if __name__ == "__main__":
    acc = get_account()
    print(f"ACCOUNT {acc['account_number']} | status={acc['status']} | equity=${acc['equity']}")
    exps = get_expirations("SPY")
    print(f"SPY expirations: {len(exps)} â€” first 8: {exps[:8]}")
    exp = exps[2] if len(exps) > 2 else exps[0]
    chain = get_option_chain("SPY", exp)
    print(f"chain for {exp}: {len(chain)} contracts")
    with_iv = [s for s in chain if s.get("impliedVolatility")]
    print(f"with IV: {len(with_iv)}")
    for s in with_iv[:5]:
        g = s.get("greeks") or {}
        print(f"  {s['symbol']} IV={s['impliedVolatility']:.3f} delta={g.get('delta')}")
