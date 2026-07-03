import os
import time
from datetime import datetime, timezone, timedelta
import requests

MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "").strip()

SYMBOLS = {
    "SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Russell 2000", "DIA": "Dow Jones",
    "XLK": "Technology", "XLF": "Financials", "XLE": "Energy", "XLV": "Health Care",
    "XLI": "Industrials", "XLY": "Consumer Discretionary", "XLP": "Consumer Staples", "XLU": "Utilities",
}

RISK_ON = ["SPY", "QQQ", "IWM", "XLK", "XLF", "XLY"]
RISK_OFF = ["XLU", "XLP", "XLV"]

def _now_iso():
    return datetime.now(timezone.utc).isoformat()

def _date_window():
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=10)
    return start.isoformat(), end.isoformat()

def pct_change(a, b):
    try:
        a, b = float(a), float(b)
        return ((b - a) / a) * 100.0 if a else 0.0
    except Exception:
        return 0.0

def massive_daily_closes(symbol):
    if not MASSIVE_API_KEY:
        raise RuntimeError("MASSIVE_API_KEY missing")
    start, end = _date_window()
    url = f"https://api.massive.com/v2/aggs/ticker/{symbol}/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=20&apiKey={MASSIVE_API_KEY}"
    r = requests.get(url, timeout=8)
    r.raise_for_status()
    rows = (r.json().get("results") or [])
    return [x.get("c") for x in rows if x.get("c") is not None]

def symbol_signal(symbol):
    closes = massive_daily_closes(symbol)

    if len(closes) < 2:
        return {
            "symbol": symbol, "name": SYMBOLS.get(symbol, symbol),
            "price": closes[-1] if closes else None,
            "change_1d": 0, "change_5d": 0, "score": 0,
            "bias": "Neutral", "source": "massive_aggs_daily",
        }

    price = closes[-1]
    change_1d = pct_change(closes[-2], closes[-1])
    change_5d = pct_change(closes[-6], closes[-1]) if len(closes) >= 6 else change_1d

    score = 0
    if change_1d > 0.20:
        score += 2
    elif change_1d < -0.20:
        score -= 2

    if change_5d > 0.50:
        score += 3
    elif change_5d < -0.50:
        score -= 3

    if symbol in RISK_ON and score > 0:
        score += 1
    if symbol in RISK_OFF and score > 0:
        score += 1
    if symbol in RISK_ON and score < 0:
        score -= 1

    bias = "Bullish" if score >= 3 else "Bearish" if score <= -3 else "Neutral"

    return {
        "symbol": symbol, "name": SYMBOLS.get(symbol, symbol),
        "price": round(float(price), 2),
        "change_1d": round(change_1d, 3),
        "change_5d": round(change_5d, 3),
        "score": score,
        "bias": bias,
        "source": "massive_aggs_daily",
    }

def market_breadth():
    rows, errors = [], []

    for symbol in SYMBOLS:
        try:
            rows.append(symbol_signal(symbol))
            time.sleep(0.05)
        except Exception as e:
            errors.append({"symbol": symbol, "error": str(e)})
            rows.append({
                "symbol": symbol, "name": SYMBOLS.get(symbol, symbol),
                "error": str(e), "score": 0, "bias": "Unavailable",
                "source": "massive_aggs_daily",
            })

    valid = [r for r in rows if r.get("bias") != "Unavailable"]
    bullish = sum(1 for r in valid if r.get("bias") == "Bullish")
    bearish = sum(1 for r in valid if r.get("bias") == "Bearish")
    neutral = sum(1 for r in valid if r.get("bias") == "Neutral")

    total_score = sum(r.get("score", 0) for r in valid)
    risk_on_score = sum(r.get("score", 0) for r in valid if r["symbol"] in RISK_ON)
    risk_off_score = sum(r.get("score", 0) for r in valid if r["symbol"] in RISK_OFF)
    participation = round((bullish - bearish) / len(valid) * 100, 1) if valid else 0

    if not valid:
        bias = "BREADTH_UNAVAILABLE"
        forecast_effect = "Breadth unavailable. Massive data did not return usable ETF data."
    elif total_score >= 12 and risk_on_score > risk_off_score:
        bias = "BULLISH_PARTICIPATION"
        forecast_effect = "Bullish breadth confirmation. Long setups have higher quality."
    elif total_score <= -12:
        bias = "BEARISH_PARTICIPATION"
        forecast_effect = "Bearish breadth confirmation. Short setups have higher quality."
    elif risk_off_score > risk_on_score and total_score <= 3:
        bias = "RISK_OFF_ROTATION"
        forecast_effect = "Risk-off breadth rotation detected. Longs should be reduced or blocked."
    else:
        bias = "MIXED_BREADTH"
        forecast_effect = "Market participation is mixed. Forecast confidence should be reduced."

    leaders = sorted(valid, key=lambda x: x.get("score", 0), reverse=True)[:3]
    laggards = sorted(valid, key=lambda x: x.get("score", 0))[:3]

    return {
        "service": "execution_service",
        "module": "market_breadth_engine_v3_massive",
        "available": bool(valid),
        "source": "massive_aggs_daily",
        "updated_at_utc": _now_iso(),
        "bias": bias,
        "forecast_effect": forecast_effect,
        "total_score": total_score,
        "participation_score": participation,
        "bullish_count": bullish,
        "bearish_count": bearish,
        "neutral_count": neutral,
        "risk_on_score": risk_on_score,
        "risk_off_score": risk_off_score,
        "leaders": leaders,
        "laggards": laggards,
        "errors": errors[:5],
        "symbols": rows,
    }
