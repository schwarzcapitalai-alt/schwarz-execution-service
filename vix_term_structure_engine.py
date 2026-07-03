import json
import urllib.request
from datetime import datetime, timezone

def fetch_close(symbol):
    encoded = symbol.replace("^", "%5E")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode())

    result = data.get("chart", {}).get("result", [{}])[0]
    quote_list = result.get("indicators", {}).get("quote", [{}])
    quote = quote_list[0] if quote_list else {}

    closes = quote.get("close", []) or []
    closes = [x for x in closes if x is not None]

    if not closes:
        raise Exception(f"no_close_data:{symbol}")

    return float(closes[-1])

def vix_term_structure():
    try:
        vix = fetch_close("^VIX")
        vix9d = fetch_close("^VIX9D")
        vxv = fetch_close("^VIX3M")

        score = 0
        reasons = []

        if vix9d > vix:
            score -= 15
            reasons.append("VIX9D above VIX = near-term stress")
        else:
            score += 5
            reasons.append("VIX9D below VIX = near-term stress cooling")

        if vix > vxv:
            score -= 20
            reasons.append("VIX above VIX3M/VXV = backwardation")
            term_structure = "Backwardation"
        else:
            score += 10
            reasons.append("VIX below VIX3M/VXV = contango")
            term_structure = "Contango"

        signal = "RISK_OFF" if score <= -20 else "RISK_ON" if score >= 10 else "NEUTRAL"

        return {
            "service": "execution_service",
            "module": "vix_term_structure_engine_v2_safe_yahoo",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "available": True,
            "signal": signal,
            "score": score,
            "vix": round(vix, 2),
            "vix9d": round(vix9d, 2),
            "vxv": round(vxv, 2),
            "term_structure": term_structure,
            "reasons": reasons,
        }

    except Exception as e:
        return {
            "service": "execution_service",
            "module": "vix_term_structure_engine_v2_safe_yahoo",
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "available": False,
            "signal": "UNAVAILABLE",
            "score": 0,
            "error": str(e),
        }
