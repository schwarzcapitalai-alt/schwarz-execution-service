import csv, io, json, os, urllib.request
from datetime import datetime, timezone, timedelta

MASSIVE_API_KEY = os.getenv("MASSIVE_API_KEY", "")

def fetch_massive_yields():
    if not MASSIVE_API_KEY:
        return []
    start = (datetime.now(timezone.utc) - timedelta(days=45)).date().isoformat()
    url = "https://api.massive.com/fed/v1/treasury-yields" + f"?date.gte={start}&limit=100&apiKey={MASSIVE_API_KEY}"
    with urllib.request.urlopen(url, timeout=15) as r:
        data = json.loads(r.read().decode())
    rows = data.get("results", [])
    rows = [x for x in rows if isinstance(x, dict) and x.get("date")]
    return sorted(rows, key=lambda x: x.get("date"), reverse=True)

def fetch_fred_yields():
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS10,DGS30"
    with urllib.request.urlopen(url, timeout=15) as r:
        text = r.read().decode()
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            y2 = float(row.get("DGS2") or "")
            y10 = float(row.get("DGS10") or "")
            y30 = float(row.get("DGS30") or "")
        except Exception:
            continue
        rows.append({"date": row.get("observation_date"), "yield_2_year": y2, "yield_10_year": y10, "yield_30_year": y30})
    return sorted(rows, key=lambda x: x.get("date"), reverse=True)

def rows_to_data(rows):
    latest, previous = rows[0], rows[1]
    y2 = float(latest.get("yield_2_year", 0) or 0)
    y10 = float(latest.get("yield_10_year", 0) or 0)
    y30 = float(latest.get("yield_30_year", 0) or 0)
    p2 = float(previous.get("yield_2_year", 0) or 0)
    p10 = float(previous.get("yield_10_year", 0) or 0)
    p30 = float(previous.get("yield_30_year", 0) or 0)
    return {
        "date": latest.get("date"),
        "previous_date": previous.get("date"),
        "US02Y": y2,
        "US10Y": y10,
        "US30Y": y30,
        "US02Y_chg_bps": round((y2 - p2) * 100, 2),
        "US10Y_chg_bps": round((y10 - p10) * 100, 2),
        "US30Y_chg_bps": round((y30 - p30) * 100, 2),
    }

def treasury_yield_signal(data=None):
    source = "manual"
    if data is None:
        data = {}
        try:
            rows = fetch_massive_yields()
            if len(rows) >= 2:
                data = rows_to_data(rows)
                source = "massive"
        except Exception:
            pass
        if not data:
            try:
                rows = fetch_fred_yields()
                if len(rows) >= 2:
                    data = rows_to_data(rows)
                    source = "fred_fallback"
                else:
                    source = "fred_empty"
            except Exception as e:
                try:
                    data = {
                        "date": datetime.now(timezone.utc).date().isoformat(),
                        "previous_date": None,
                        "US02Y": 0,
                        "US10Y": 0,
                        "US30Y": 0,
                        "US02Y_chg_bps": 0,
                        "US10Y_chg_bps": 0,
                        "US30Y_chg_bps": 0,
                        "proxy_note": "FRED timed out; using neutral Treasury fallback until external yield source responds"
                    }
                    source = "neutral_safe_fallback"
                except Exception:
                    data = {"error": str(e)}
                    source = "fred_error"

    data = data or {}

    def num(key):
        try:
            return float(data.get(key, 0) or 0)
        except Exception:
            return 0.0

    us2y, us10y, us30y = num("US02Y"), num("US10Y"), num("US30Y")
    us2y_chg, us10y_chg, us30y_chg = num("US02Y_chg_bps"), num("US10Y_chg_bps"), num("US30Y_chg_bps")
    score, reasons = 0, []

    if us10y_chg >= 7:
        score -= 20; reasons.append("10Y yield rising sharply = equity pressure")
    elif us10y_chg >= 3:
        score -= 10; reasons.append("10Y yield rising = mild equity pressure")
    elif us10y_chg <= -7:
        score += 20; reasons.append("10Y yield falling sharply = equity support")
    elif us10y_chg <= -3:
        score += 10; reasons.append("10Y yield falling = mild equity support")

    if us2y_chg >= 7:
        score -= 15; reasons.append("2Y yield rising sharply = Fed pressure")
    elif us2y_chg <= -7:
        score += 15; reasons.append("2Y yield falling sharply = Fed relief")

    if us30y_chg >= 7:
        score -= 10; reasons.append("30Y yield rising = long-duration pressure")
    elif us30y_chg <= -7:
        score += 10; reasons.append("30Y yield falling = duration support")

    curve_2s10s = us10y - us2y if us10y and us2y else 0
    curve_10s30s = us30y - us10y if us30y and us10y else 0

    if curve_2s10s < -0.50:
        reasons.append("2s10s curve deeply inverted")
    elif curve_2s10s > 0.25:
        reasons.append("2s10s curve positive / steepening")

    score = max(-50, min(50, score))

    if score >= 25:
        signal = "RISK_ON_YIELD_RELIEF"
    elif score >= 10:
        signal = "MILD_YIELD_SUPPORT"
    elif score <= -25:
        signal = "RISK_OFF_YIELD_PRESSURE"
    elif score <= -10:
        signal = "MILD_YIELD_PRESSURE"
    else:
        signal = "NEUTRAL_YIELDS"

    return {
        "service": "execution_service",
        "module": "treasury_yield_engine_v3_fred_fallback",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "available": bool(us10y) or source == "neutral_safe_fallback",
        "source": source,
        "signal": signal,
        "score": score,
        "treasury_score": score,
        "inputs": {
            "date": data.get("date"),
            "previous_date": data.get("previous_date"),
            "US02Y": us2y,
            "US10Y": us10y,
            "US30Y": us30y,
            "US02Y_chg_bps": us2y_chg,
            "US10Y_chg_bps": us10y_chg,
            "US30Y_chg_bps": us30y_chg,
            "curve_2s10s": round(curve_2s10s, 3),
            "curve_10s30s": round(curve_10s30s, 3),
        },
        "reasons": reasons,
        "note": data.get("error") if "error" in data else "Treasury yields scored with Massive primary and FRED fallback",
    }
