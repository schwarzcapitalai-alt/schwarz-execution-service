import math

def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

def score_0dte_contract(contract, forecast):
    side = contract.get("right", "").upper()
    strike = safe_float(contract.get("strike"))
    delta = safe_float(contract.get("delta"))
    iv = safe_float(contract.get("iv"))
    oi = safe_float(contract.get("open_interest"))
    volume = safe_float(contract.get("volume"))
    bid = safe_float(contract.get("bid"))
    ask = safe_float(contract.get("ask"))

    put_wall = safe_float(forecast.get("put_wall"))
    call_wall = safe_float(forecast.get("call_wall"))

    if side == "P":
        target = put_wall
        ideal_delta = -0.38
    else:
        target = call_wall
        ideal_delta = 0.38

    delta_score = 1 - min(abs(delta - ideal_delta) / 0.25, 1)
    distance_score = 1 - min(abs(strike - target) / 10, 1)
    oi_score = clamp(math.log10(max(oi, 1)) / 6, 0, 1)
    volume_score = clamp(math.log10(max(volume, 1)) / 6, 0, 1)

    spread = max(ask - bid, 0)
    mid = max((ask + bid) / 2, 0.01)
    spread_score = 1 - clamp((spread / mid) / 0.25, 0, 1)

    iv_score = 1 - clamp((iv - 0.20) / 0.80, 0, 1)

    raw = (
        oi_score * 25 +
        volume_score * 20 +
        delta_score * 25 +
        iv_score * 10 +
        spread_score * 10 +
        distance_score * 10
    )

    return round(clamp(raw, 0, 100), 1)

def choose_best_0dte(option_chain, forecast, trade_bias):
    bias = trade_bias.get("bias", "")
    wanted_side = "P" if bias == "SHORT_ONLY" else "C"

    scored = []
    for c in option_chain:
        if c.get("right", "").upper() == wanted_side:
            c = dict(c)
            c["score"] = score_0dte_contract(c, forecast)
            scored.append(c)

    scored.sort(key=lambda x: x["score"], reverse=True)

    if not scored:
        return {"available": False, "reason": "No matching 0DTE contracts found"}

    best = scored[0]
    side_label = "PUT" if wanted_side == "P" else "CALL"

    return {
        "available": True,
        "ticker": forecast.get("ticker", "SPY"),
        "side": side_label,
        "best_strike": f'{int(float(best.get("strike")))}{wanted_side}',
        "strike": best.get("strike"),
        "expiry": best.get("expiry"),
        "delta": best.get("delta"),
        "iv": best.get("iv"),
        "open_interest": best.get("open_interest"),
        "volume": best.get("volume"),
        "bid": best.get("bid"),
        "ask": best.get("ask"),
        "score": best.get("score"),
        "reason": f"{side_label} selected from {bias}, OI, delta, IV, spread, and target distance"
    }
