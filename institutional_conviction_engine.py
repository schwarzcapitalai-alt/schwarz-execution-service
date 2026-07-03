import json
import urllib.request
from pathlib import Path

CONFIG_PATH = Path("/config/conviction_weights.json")

DEFAULT_WEIGHTS = {
    "institutional_forecast": 0.25,
    "gamma_regime": 0.15,
    "options_flow": 0.15,
    "breadth": 0.10,
    "sector_rotation": 0.10,
    "technical_confirmation": 0.10,
    "treasury_model": 0.05,
    "credit_spreads": 0.05,
    "vix_term_structure": 0.05,
    "news_impact": 0.05
}

def num(x, default=0.0):
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace("$", "").replace("B", "").strip()
        return float(x)
    except Exception:
        return default

def fetch(path, timeout=6):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8004{path}", timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def load_weights():
    try:
        if CONFIG_PATH.exists():
            data = json.loads(CONFIG_PATH.read_text())
            out = DEFAULT_WEIGHTS.copy()
            out.update({k: float(v) for k, v in data.items() if k in out})
            return out
    except Exception:
        pass
    return DEFAULT_WEIGHTS.copy()

def bias_score(value):
    v = str(value or "").upper()
    if any(x in v for x in ["SHORT_ONLY", "BEARISH", "NEGATIVE", "RISK_OFF", "DEFENSIVE"]):
        return -100
    if any(x in v for x in ["LONG_ONLY", "BULLISH", "POSITIVE", "RISK_ON"]):
        return 100
    if "LEAN_BEARISH" in v:
        return -65
    if "LEAN_BULLISH" in v:
        return 65
    return 0

def label(conviction):
    if conviction >= 85:
        return "VERY_HIGH"
    if conviction >= 70:
        return "HIGH"
    if conviction >= 55:
        return "MEDIUM"
    if conviction >= 40:
        return "LOW"
    return "NO_TRADE"

def size(conviction):
    if conviction >= 85:
        return "FULL"
    if conviction >= 70:
        return "THREE_QUARTER"
    if conviction >= 55:
        return "HALF"
    if conviction >= 40:
        return "QUARTER"
    return "NONE"

def quality(conviction):
    if conviction >= 85:
        return "A+"
    if conviction >= 70:
        return "A"
    if conviction >= 55:
        return "B"
    if conviction >= 40:
        return "C"
    return "WAIT"

def penalty_for_conflicts(factors):
    bullish = [f for f in factors if f["raw_score"] >= 40]
    bearish = [f for f in factors if f["raw_score"] <= -40]
    return 5 if bullish and bearish else 0

def institutional_conviction_v2():
    weights = load_weights()

    forecast = fetch("/forecast/trade-bias")
    breadth = fetch("/breadth/market")
    cross_asset = fetch("/cross-asset")
    sector = fetch("/sector/rotation")
    treasury = fetch("/treasury/yields")

    if forecast.get("error") and isinstance(cross_asset.get("forecast"), dict):
        forecast = cross_asset.get("forecast")

    tech = forecast.get("technical_confirmation", {}) or {}
    credit = forecast.get("credit_markets", {}) or forecast.get("credit_spreads", {}) or {}
    vix = forecast.get("vix_term_structure", {}) or {}
    news = forecast.get("news_impact", {}) or {}

    factors = []

    def add(key, name, raw, source):
        raw = max(-100, min(100, num(raw)))
        weight = weights[key]
        factors.append({
            "key": key,
            "factor": name,
            "weight": weight,
            "raw_score": round(raw, 2),
            "weighted_score": round(raw * weight, 2),
            "source": source
        })

    desk = forecast.get("desk_call") or forecast.get("institutional_bias") or forecast.get("bias")
    conf = num(forecast.get("adjusted_confidence", forecast.get("confidence", 50)), 50)
    add("institutional_forecast", "Institutional Forecast", bias_score(desk) * min(max(conf / 100, 0.25), 1.0), desk)

    gamma_source = forecast.get("gamma_regime") or forecast.get("gamma_bias")
    add("gamma_regime", "Gamma Regime", bias_score(gamma_source), gamma_source)

    flow_bias = forecast.get("flow_bias") or forecast.get("options_flow_bias")
    flow_score = num(forecast.get("flow_score", forecast.get("options_flow_score", 0)), 0)
    if flow_score == 0:
        flow_score = bias_score(flow_bias)
    add("options_flow", "Options Flow", flow_score, flow_bias)

    breadth_source = breadth.get("bias") or breadth.get("signal")
    breadth_score = num(breadth.get("total_score", breadth.get("breadth_score", breadth.get("score", 0))), 0)
    if abs(breadth_score) < 10:
        breadth_score = bias_score(breadth_source)
    add("breadth", "Breadth", breadth_score, breadth_source)

    sector_source = sector.get("signal")
    add("sector_rotation", "Sector Rotation", num(sector.get("rotation_score", 0), 0), sector_source)

    tech_source = tech.get("technical_bias") or tech.get("bot_permission")
    tech_score = num(tech.get("technical_score", 0), 0)
    if tech_score == 0:
        tech_score = bias_score(tech_source)
    add("technical_confirmation", "Technical Confirmation", tech_score, tech_source)

    treasury_source = treasury.get("signal") or treasury.get("bias")
    add("treasury_model", "Treasury Model", num(treasury.get("treasury_score", treasury.get("score", 0)), 0), treasury_source)

    credit_source = credit.get("signal") or credit.get("bias")
    add("credit_spreads", "Credit Spreads", num(credit.get("credit_score", credit.get("score", 0)), 0), credit_source)

    vix_source = vix.get("signal") or vix.get("regime")
    add("vix_term_structure", "VIX Term Structure", num(vix.get("vix_score", vix.get("score", 0)), 0), vix_source)

    news_source = news.get("news_bias") or news.get("bias")
    add("news_impact", "News Impact", num(news.get("news_score", news.get("score", 0)), 0), news_source)

    raw_total = round(sum(f["weighted_score"] for f in factors), 2)
    conflict_penalty = penalty_for_conflicts(factors)
    adjusted_total = raw_total - conflict_penalty if raw_total > 0 else raw_total + conflict_penalty
    conviction = round(abs(adjusted_total), 2)

    direction = "WAIT"
    if conviction >= 40:
        direction = "LONG" if adjusted_total > 0 else "SHORT"

    return {
        "service": "institutional_conviction_engine_v2",
        "institutional_conviction": conviction,
        "direction": direction,
        "confidence": label(conviction),
        "position_size": size(conviction),
        "expected_holding": "Intraday",
        "risk_multiplier": round(min(max(conviction / 85, 0.25), 1.25), 2) if direction != "WAIT" else 0,
        "entry_quality": quality(conviction),
        "trade_permission": "ALLOW_TRADE" if conviction >= 55 else "WAIT",
        "weighted_total_raw": raw_total,
        "weighted_total_adjusted": round(adjusted_total, 2),
        "conflict_penalty": conflict_penalty,
        "weights": weights,
        "factors": factors
    }
