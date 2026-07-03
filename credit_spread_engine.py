import json
import urllib.request
from datetime import datetime, timezone

def fetch_change(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=10d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    with urllib.request.urlopen(req, timeout=8) as r:
        data = json.loads(r.read().decode())

    result = data["chart"]["result"][0]
    closes = result["indicators"]["quote"][0]["close"]
    closes = [x for x in closes if x is not None]

    first = closes[0]
    last = closes[-1]

    return ((last - first) / first) * 100.0

def credit_market_signal():
    try:
        hyg = fetch_change("HYG")
        jnk = fetch_change("JNK")
        lqd = fetch_change("LQD")

        spread_hyg = hyg - lqd
        spread_jnk = jnk - lqd

        score = 0
        reasons = []

        if spread_hyg > 0.50:
            score += 10
            reasons.append("HYG outperforming LQD")
        elif spread_hyg > 0.15:
            score += 5
            reasons.append("HYG modestly outperforming LQD")
        elif spread_hyg < -0.50:
            score -= 10
            reasons.append("HYG underperforming LQD")
        elif spread_hyg < -0.15:
            score -= 5
            reasons.append("HYG modestly underperforming LQD")

        if spread_jnk > 0.50:
            score += 10
            reasons.append("JNK outperforming LQD")
        elif spread_jnk > 0.15:
            score += 5
            reasons.append("JNK modestly outperforming LQD")
        elif spread_jnk < -0.50:
            score -= 10
            reasons.append("JNK underperforming LQD")
        elif spread_jnk < -0.15:
            score -= 5
            reasons.append("JNK modestly underperforming LQD")

        if hyg > 1.0:
            score += 5
            reasons.append("HYG absolute strength")
        elif hyg < -1.0:
            score -= 5
            reasons.append("HYG absolute weakness")

        if jnk > 1.0:
            score += 5
            reasons.append("JNK absolute strength")
        elif jnk < -1.0:
            score -= 5
            reasons.append("JNK absolute weakness")

        score = max(-25, min(25, score))

        signal = "RISK_ON" if score >= 10 else "RISK_OFF" if score <= -10 else "NEUTRAL"

        return {
            "service": "execution_service",
            "module": "credit_market_engine_v2_relative_spreads",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "signal": signal,
            "credit_score": score,
            "HYG_pct": round(hyg, 2),
            "JNK_pct": round(jnk, 2),
            "LQD_pct": round(lqd, 2),
            "spread_hyg_lqd": round(spread_hyg, 2),
            "spread_jnk_lqd": round(spread_jnk, 2),
            "reasons": reasons,
        }

    except Exception as e:
        return {
            "service": "execution_service",
            "module": "credit_market_engine_v2_relative_spreads",
            "signal": "UNAVAILABLE",
            "credit_score": 0,
            "error": str(e),
        }
