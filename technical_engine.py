import math, time, urllib.request, json
from datetime import datetime, timezone

CACHE = {}
TTL = 60

def _ema(values, length):
    if not values:
        return []
    k = 2 / (length + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append((v * k) + (out[-1] * (1 - k)))
    return out

def _fetch_closes(ticker="SPY", interval="5m", rng="2d"):
    key = (ticker, interval, rng)
    now = time.time()
    if key in CACHE and now - CACHE[key]["ts"] < TTL:
        return CACHE[key]["closes"]

    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={rng}&interval={interval}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())

    result = data["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    closes = [float(x) for x in closes if x is not None]

    CACHE[key] = {"ts": now, "closes": closes}
    return closes

def technical_confirmation(ticker="SPY", interval="5m"):
    closes = _fetch_closes(ticker, interval)

    if len(closes) < 40:
        return {
            "ticker": ticker,
            "interval": interval,
            "status": "insufficient_data",
            "technical_bias": "NEUTRAL",
            "score": 0
        }

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
    signal = _ema(macd, 9)
    hist = macd[-1] - signal[-1]
    prev_hist = macd[-2] - signal[-2]

    momentum_roc_10 = ((closes[-1] - closes[-11]) / closes[-11]) * 100

    macd_bullish = macd[-1] > signal[-1]
    macd_bearish = macd[-1] < signal[-1]
    hist_rising = hist > prev_hist
    hist_falling = hist < prev_hist
    momentum_positive = momentum_roc_10 > 0
    momentum_negative = momentum_roc_10 < 0

    ema20 = _ema(closes, 20)[-1]
    ema50 = _ema(closes, 50)[-1]

    above_ema20 = closes[-1] > ema20
    below_ema20 = closes[-1] < ema20

    above_ema50 = closes[-1] > ema50
    below_ema50 = closes[-1] < ema50

    score = 0

    if macd_bullish: score += 1
    if macd_bearish: score -= 1

    if hist_rising: score += 1
    if hist_falling: score -= 1

    if momentum_positive: score += 1
    if momentum_negative: score -= 1

    if above_ema20: score += 1
    if below_ema20: score -= 1

    if above_ema50: score += 1
    if below_ema50: score -= 1

    if score >= 4:
        bias = "LONG_CONFIRMATION"
        permission = "LONGS_ALLOWED"
    elif score <= -4:
        bias = "SHORT_CONFIRMATION"
        permission = "SHORTS_ALLOWED"
    else:
        bias = "NEUTRAL"
        permission = "WAIT"

    return {
        "ticker": ticker,
        "interval": interval,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "last_price": round(closes[-1], 2),
        "macd": round(macd[-1], 4),
        "macd_signal": round(signal[-1], 4),
        "macd_histogram": round(hist, 4),
        "macd_state": "BULLISH" if macd_bullish else "BEARISH",
        "histogram_state": "RISING" if hist_rising else "FALLING",
        "momentum_roc_10": round(momentum_roc_10, 4),
        "momentum_state": "POSITIVE" if momentum_positive else "NEGATIVE",
        
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "above_ema20": above_ema20,
        "above_ema50": above_ema50,
        "technical_score": score,

        "technical_bias": bias,
        "bot_permission": permission
    }
