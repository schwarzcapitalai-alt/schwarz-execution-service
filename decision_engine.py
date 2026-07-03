from datetime import datetime, timezone


def _f(v, default=0.0):
    try:
        return float(str(v).replace("$", "").replace("B", "").replace(",", ""))
    except Exception:
        return default


def build_decision(forecast: dict, trade_bias: dict = None, technical: dict = None):
    trade_bias = trade_bias or {}
    technical = technical or trade_bias.get("technical_confirmation", {}) or {}

    composite = _f(trade_bias.get("forecast_composite_score"), 0)
    institutional = str(forecast.get("institutional_bias", "Neutral"))
    gamma_regime = str(forecast.get("gamma_regime", "UNKNOWN"))
    dealer_flow = str(forecast.get("dealer_flow", "UNKNOWN"))
    vol_regime = str(forecast.get("vol_regime", "UNKNOWN"))
    tech_bias = str(technical.get("technical_bias", "NEUTRAL"))
    bot_permission = str(technical.get("bot_permission", "WAIT"))

    reasons = []

    # Direction only
    if institutional.lower() == "bearish" or composite <= -35:
        direction = "SHORT_ONLY"
        reasons.append("Institutional/composite bias bearish")
    elif institutional.lower() == "bullish" or composite >= 35:
        direction = "LONG_ONLY"
        reasons.append("Institutional/composite bias bullish")
    else:
        direction = "BALANCED"
        reasons.append("No strong institutional direction")

    # Regime only
    if "POSITIVE" in gamma_regime and dealer_flow.lower() in ["stabilizing", "stable"]:
        market_regime = "PIN_DAY"
        reasons.append("Positive gamma with stabilizing dealer flow favors pinning")
    elif "NEGATIVE" in gamma_regime and vol_regime.lower() in ["hot", "expanding"]:
        market_regime = "TREND_DAY"
        reasons.append("Negative gamma with hot volatility favors trend expansion")
    elif vol_regime.lower() in ["hot", "expanding"]:
        market_regime = "HIGH_VOLATILITY"
        reasons.append("Hot volatility regime")
    else:
        market_regime = "CHOP_DAY"
        reasons.append("No clean trend regime")

    # Execution permission
    execution = "WAIT"

    if market_regime == "PIN_DAY":
        execution = "WAIT"
        reasons.append("Execution blocked: pin day / insufficient trend edge")
    elif direction == "SHORT_ONLY" and bot_permission == "SHORTS_ALLOWED":
        execution = "EXECUTE_SHORT"
        reasons.append("Short execution allowed by technical confirmation")
    elif direction == "LONG_ONLY" and bot_permission == "LONGS_ALLOWED":
        execution = "EXECUTE_LONG"
        reasons.append("Long execution allowed by technical confirmation")
    else:
        reasons.append("Execution blocked: direction and technical permission not aligned")

    confidence = int(trade_bias.get("adjusted_confidence") or forecast.get("confidence") or 0)

    return {
        "service": "execution_service",
        "module": "schwarz_decision_engine_v1",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": forecast.get("ticker", "SPY"),
        "price": forecast.get("spy_price"),
        "direction": direction,
        "market_regime": market_regime,
        "execution": execution,
        "confidence": confidence,
        "composite_score": composite,
        "institutional_bias": institutional,
        "gamma_regime": gamma_regime,
        "dealer_flow": dealer_flow,
        "vol_regime": vol_regime,
        "technical_bias": tech_bias,
        "bot_permission": bot_permission,
        "reason": reasons,
        "contract_side": (
            "PUT" if execution == "EXECUTE_SHORT"
            else "CALL" if execution == "EXECUTE_LONG"
            else "NONE"
        ),
        "trade_allowed": execution in ["EXECUTE_SHORT", "EXECUTE_LONG"],
    }
