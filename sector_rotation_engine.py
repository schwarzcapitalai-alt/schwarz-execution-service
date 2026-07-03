import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta

MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "")

SECTORS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Health Care",
    "XLI": "Industrials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

RISK_ON = ["XLK", "XLY", "XLF", "XLC", "XLI"]
DEFENSIVE = ["XLU", "XLP", "XLV"]
INFLATION = ["XLE", "XLB"]


def pct_change(a, b):
    try:
        a = float(a)
        b = float(b)
        if a == 0:
            return 0.0
        return ((b - a) / a) * 100.0
    except Exception:
        return 0.0


def fetch_massive_daily(symbol):
    if not MASSIVE_API_KEY:
        return []
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=30)
    url = (
        f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/"
        f"{start.isoformat()}/{end.isoformat()}"
        f"?adjusted=true&sort=asc&limit=40&apiKey={MASSIVE_API_KEY}"
    )
    with urllib.request.urlopen(url, timeout=8) as r:
        data = json.loads(r.read().decode())
    return data.get("results", []) or []


def fetch_yahoo_daily(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1mo&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode())

    result = data.get("chart", {}).get("result", [{}])[0]
    timestamps = result.get("timestamp", []) or []
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", []) or []

    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        rows.append({
            "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
            "c": float(close),
        })

    return rows[-30:]


def fetch_daily(symbol):
    try:
        rows = fetch_massive_daily(symbol)
        if len(rows) >= 6:
            return rows, "massive_aggs_daily"
    except Exception:
        pass

    try:
        rows = fetch_yahoo_daily(symbol)
        if len(rows) >= 6:
            return rows, "yahoo_chart_fallback"
    except Exception as e:
        return [], f"data_error:{e}"

    return [], "not_enough_data"


def sector_signal(symbol):
    rows, source = fetch_daily(symbol)

    if len(rows) < 2:
        return {
            "symbol": symbol,
            "name": SECTORS.get(symbol, symbol),
            "bias": "Unavailable",
            "score": 0,
            "error": source,
        }

    latest = rows[-1]
    previous = rows[-2]
    first_5d = rows[-6] if len(rows) >= 6 else rows[0]
    first_20d = rows[-21] if len(rows) >= 21 else rows[0]

    price = float(latest.get("c") or 0)
    change_1d = pct_change(previous.get("c"), latest.get("c"))
    change_5d = pct_change(first_5d.get("c"), latest.get("c"))
    change_20d = pct_change(first_20d.get("c"), latest.get("c"))

    score = 0

    if change_1d > 0.35:
        score += 2
    elif change_1d < -0.35:
        score -= 2

    if change_5d > 1.0:
        score += 3
    elif change_5d < -1.0:
        score -= 3

    if change_20d > 2.5:
        score += 4
    elif change_20d < -2.5:
        score -= 4

    if score >= 5:
        bias = "Bullish"
    elif score <= -5:
        bias = "Bearish"
    else:
        bias = "Neutral"

    return {
        "symbol": symbol,
        "name": SECTORS.get(symbol, symbol),
        "price": round(price, 2),
        "change_1d": round(change_1d, 3),
        "change_5d": round(change_5d, 3),
        "change_20d": round(change_20d, 3),
        "score": score,
        "bias": bias,
        "source": source,
    }


def sector_rotation():
    rows = []
    for symbol in SECTORS:
        try:
            rows.append(sector_signal(symbol))
        except Exception as e:
            rows.append({
                "symbol": symbol,
                "name": SECTORS.get(symbol, symbol),
                "bias": "Unavailable",
                "score": 0,
                "error": str(e),
            })

    valid = [r for r in rows if r.get("bias") != "Unavailable"]

    risk_on_score = sum(r.get("score", 0) for r in valid if r["symbol"] in RISK_ON)
    defensive_score = sum(r.get("score", 0) for r in valid if r["symbol"] in DEFENSIVE)
    inflation_score = sum(r.get("score", 0) for r in valid if r["symbol"] in INFLATION)

    leaders = sorted(valid, key=lambda x: x.get("score", 0), reverse=True)[:3]
    laggards = sorted(valid, key=lambda x: x.get("score", 0))[:3]

    rotation_score = max(-50, min(50, risk_on_score - defensive_score))

    if rotation_score >= 8:
        signal = "RISK_ON_ROTATION"
    elif rotation_score <= -8:
        signal = "DEFENSIVE_ROTATION"
    elif inflation_score >= 6:
        signal = "INFLATION_ROTATION"
    else:
        signal = "MIXED_ROTATION"

    return {
        "service": "execution_service",
        "module": "sector_rotation_engine_v4_yahoo_fallback",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "available": bool(valid),
        "source": "mixed_massive_yahoo",
        "signal": signal,
        "rotation_score": rotation_score,
        "risk_on_score": risk_on_score,
        "defensive_score": defensive_score,
        "inflation_score": inflation_score,
        "leaders": leaders,
        "laggards": laggards,
        "sectors": rows,
    }
