def cross_asset_confirmation(forecast):
    score = 0
    reasons = []

    macro = forecast.get("macro", {}) or {}

    def num(*keys):
        for key in keys:
            try:
                if "." in key:
                    root, child = key.split(".", 1)
                    val = (forecast.get(root, {}) or {}).get(child)
                else:
                    val = forecast.get(key)
                if val is not None:
                    return float(val)
            except Exception:
                pass
        return 0.0

    vxx = num("vxx_change_pct", "macro.VXX_pct")
    tlt = num("tlt_change_pct", "macro.TLT_pct")
    uup = num("uup_change_pct", "macro.UUP_pct")
    btc = num("btc_change_pct", "macro.BTC_pct")

    institutional_bias = forecast.get("institutional_bias", "Neutral")
    gamma_bias = forecast.get("gamma_bias", "Neutral")
    gamma_regime = forecast.get("gamma_regime", "")

    if vxx > 1:
        score -= 20
        reasons.append("VXX rising = volatility pressure bearish")
    elif vxx < -1:
        score += 20
        reasons.append("VXX falling = volatility pressure bullish")

    if tlt > 0.5:
        score += 10
        reasons.append("TLT strong = rates relief bullish")
    elif tlt < -0.5:
        score -= 10
        reasons.append("TLT weak = rates pressure bearish")

    if uup > 0.5:
        score -= 10
        reasons.append("Dollar strong = risk pressure bearish")
    elif uup < -0.5:
        score += 10
        reasons.append("Dollar weak = risk-on support bullish")

    if btc > 1:
        score += 10
        reasons.append("BTC strong = risk appetite bullish")
    elif btc < -1:
        score -= 10
        reasons.append("BTC weak = risk appetite bearish")

    if institutional_bias == "Bullish":
        score += 20
        reasons.append("Institutional bias bullish")
    elif institutional_bias == "Bearish":
        score -= 20
        reasons.append("Institutional bias bearish")

    if gamma_bias == "Positive":
        score += 15
        reasons.append("Gamma bias positive")
    elif gamma_bias == "Negative":
        score -= 15
        reasons.append("Gamma bias negative")

    if "POSITIVE" in str(gamma_regime).upper():
        reasons.append("Positive gamma regime = more mean reversion/stability")
    elif "NEGATIVE" in str(gamma_regime).upper():
        reasons.append("Negative gamma regime = more expansion risk")

    if score >= 40:
        signal = "STRONG_BULLISH"
    elif score >= 15:
        signal = "BULLISH"
    elif score <= -40:
        signal = "STRONG_BEARISH"
    elif score <= -15:
        signal = "BEARISH"
    else:
        signal = "MIXED"

    confidence_adjustment = 0
    if abs(score) >= 50:
        confidence_adjustment = 10
    elif abs(score) >= 35:
        confidence_adjustment = 7
    elif abs(score) >= 20:
        confidence_adjustment = 4
    elif abs(score) <= 10:
        confidence_adjustment = -5

    return {
        "signal": signal,
        "score": score,
        "confidence_adjustment": confidence_adjustment,
        "inputs": {
            "VXX_pct": vxx,
            "TLT_pct": tlt,
            "UUP_pct": uup,
            "BTC_pct": btc,
            "institutional_bias": institutional_bias,
            "gamma_bias": gamma_bias,
            "gamma_regime": gamma_regime,
        },
        "reasons": reasons,
    }
