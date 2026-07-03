import json
import os
import requests
from datetime import datetime, timezone

FORECAST_URL = "http://172.31.19.197:8787/data/forecast_input.json"
FORECAST_CACHE = os.getenv("FORECAST_CACHE", "/config/last_good_forecast_input.json")

def _fallback(error):
    try:
        if os.path.exists(FORECAST_CACHE) and os.path.getsize(FORECAST_CACHE) > 0:
            with open(FORECAST_CACHE, "r") as f:
                data = json.load(f)
            data["stale_forecast_cache"] = True
            data["forecast_error"] = str(error)
            return data
    except Exception:
        pass

    return {
        "error": str(error),
        "ticker": "SPY",
        "spy_price": None,
        "institutional_bias": "UNKNOWN",
        "confidence": 0,
        "gamma_regime": None,
        "net_gex": None,
        "call_wall": None,
        "put_wall": None,
        "forecast": {"direction": "UNKNOWN", "risk": "UNKNOWN"},
        "updated_at_utc": datetime.now(timezone.utc).isoformat()
    }

def get_forecast():
    try:
        r = requests.get(FORECAST_URL, timeout=5)
        r.raise_for_status()

        if not r.text or not r.text.strip():
            raise ValueError("forecast_input.json returned empty body")

        data = r.json()

        if not isinstance(data, dict):
            raise ValueError("forecast_input.json did not return a JSON object")

        os.makedirs(os.path.dirname(FORECAST_CACHE), exist_ok=True)
        with open(FORECAST_CACHE, "w") as f:
            json.dump(data, f, indent=2)

        return data

    except Exception as e:
        return _fallback(e)

def trade_bias():
    f = get_forecast()
    direction = str(f.get("institutional_bias", "")).upper()
    gamma = str(f.get("gamma_regime", "")).upper()
    risk = str(f.get("forecast", {}).get("risk", "")).upper()

    if direction == "BEARISH" and "NEGATIVE" in gamma:
        bias = "SHORT_ONLY"
        reason = "Bearish institutional bias with negative gamma"
    elif direction == "BULLISH" and "POSITIVE" in gamma:
        bias = "LONG_ONLY"
        reason = "Bullish institutional bias with positive gamma"
    elif risk == "HIGH":
        bias = "REDUCED_SIZE"
        reason = "High-risk forecast environment"
    else:
        bias = "BOTH_ALLOWED"
        reason = "No strong directional restriction"

    return {
        "bias": bias,
        "reason": reason,
        "ticker": f.get("ticker"),
        "spy_price": f.get("spy_price"),
        "institutional_bias": f.get("institutional_bias"),
        "confidence": f.get("confidence"),
        "gamma_regime": f.get("gamma_regime"),
        "net_gex": f.get("net_gex"),
        "call_wall": f.get("call_wall"),
        "put_wall": f.get("put_wall"),
        "risk": risk,
        "forecast": f
    }
