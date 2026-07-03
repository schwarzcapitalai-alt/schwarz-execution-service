from datetime import datetime
from zoneinfo import ZoneInfo


def fnum(v, default=0.0):
    try:
        if v is None:
            return default
        s = str(v).replace(",", "").replace("$", "").replace("+", "").strip()
        if s.endswith("B"):
            return float(s[:-1]) * 1_000_000_000
        if s.endswith("M"):
            return float(s[:-1]) * 1_000_000
        return float(s)
    except Exception:
        return default


def grade(score):
    if score >= 80:
        return "A"
    if score >= 70:
        return "B+"
    if score >= 60:
        return "B"
    if score >= 50:
        return "C"
    return "WAIT"


def decision(score, directional_score):
    if score < 50:
        return "WAIT"
    if directional_score >= 3:
        return "LONG_WATCH"
    if directional_score <= -3:
        return "SHORT_WATCH"
    return "PIN_WATCH"


def build_projection(forecast, trade_bias, technical, option):
    now_et = datetime.now(ZoneInfo("America/New_York"))

    spy = fnum(forecast.get("spy_price"))
    call_wall = fnum(forecast.get("call_wall"))
    put_wall = fnum(forecast.get("put_wall"))
    net_gex_raw = str(forecast.get("net_gex", "0"))
    net_gex = fnum(net_gex_raw)

    gamma_regime = forecast.get("gamma_regime", "UNKNOWN")
    institutional_bias = forecast.get("institutional_bias", "UNKNOWN")
    dealer_flow = forecast.get("dealer_flow", "UNKNOWN")

    tech_bias = technical.get("technical_bias", "NEUTRAL")
    bot_permission = technical.get("bot_permission", "WAIT")
    macd_state = technical.get("macd_state", "NEUTRAL")
    momentum_state = technical.get("momentum_state", "NEUTRAL")

    best_side = option.get("side", "NONE")
    best_contract = option.get("best_strike", "N/A")
    best_strike = fnum(option.get("strike"), spy)

    composite = fnum(trade_bias.get("forecast_composite_score"))
    desk_call = trade_bias.get("desk_call", "WAIT")

    quality = 50
    direction = 0
    reasons = []

    if gamma_regime == "POSITIVE GAMMA":
        quality += 10
        reasons.append("Positive gamma supports pinning")
    elif gamma_regime == "NEGATIVE GAMMA":
        quality -= 5
        reasons.append("Negative gamma increases volatility")

    if net_gex > 0:
        quality += 8
        reasons.append(f"Net GEX positive: {net_gex_raw}")

    if best_side == "CALL":
        quality += 8
        direction += 2
        reasons.append(f"Options chain favors calls: {best_contract}")
    elif best_side == "PUT":
        quality += 8
        direction -= 2
        reasons.append(f"Options chain favors puts: {best_contract}")

    if tech_bias == "LONG_CONFIRMATION" or bot_permission == "LONGS_ALLOWED":
        quality += 10
        direction += 2
        reasons.append("Technicals confirm long side")
    elif tech_bias == "SHORT_CONFIRMATION" or bot_permission == "SHORTS_ALLOWED":
        quality += 10
        direction -= 2
        reasons.append("Technicals confirm short side")

    if macd_state == "BULLISH":
        direction += 1
    elif macd_state == "BEARISH":
        direction -= 1

    if momentum_state == "POSITIVE":
        direction += 1
    elif momentum_state == "NEGATIVE":
        direction -= 1

    if institutional_bias == "Bearish":
        direction -= 2
        reasons.append("Institutional bias bearish")
    elif institutional_bias == "Bullish":
        direction += 2
        reasons.append("Institutional bias bullish")

    if composite <= -35:
        direction -= 1
        reasons.append(f"Composite bearish: {composite}")
    elif composite >= 35:
        direction += 1
        reasons.append(f"Composite bullish: {composite}")

    if dealer_flow == "Stabilizing":
        quality += 5
        reasons.append("Dealer flow stabilizing")

    quality = max(0, min(100, quality))
    final_decision = decision(quality, direction)

    magnet = best_strike if best_strike > 0 else spy
    forecast_close = round((spy * 0.55) + (magnet * 0.30) + ((call_wall or spy) * 0.15), 2)
    close_low = round(forecast_close - 0.45, 2)
    close_high = round(forecast_close + 0.45, 2)

    return {
        "service": "execution_service",
        "module": "schwarz_institutional_forecast_engine_v1",
        "updated_at_et": now_et.isoformat(),
        "ticker": "SPY",
        "spy_price": round(spy, 2),
        "decision": final_decision,
        "probability": quality,
        "grade": grade(quality),
        "directional_score": direction,
        "desk_call": desk_call,
        "forecast_close": forecast_close,
        "close_zone": {"low": close_low, "high": close_high},
        "pin_level": round(magnet, 2),
        "call_wall": round(call_wall, 2),
        "put_wall": round(put_wall, 2),
        "best_0dte": best_contract,
        "gamma_regime": gamma_regime,
        "net_gex": net_gex_raw,
        "institutional_bias": institutional_bias,
        "technical_bias": tech_bias,
        "bot_permission": bot_permission,
        "reasons": reasons[:10]
    }
