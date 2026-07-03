from fastapi import APIRouter

from forecast_client import get_forecast, trade_bias
from cross_asset_engine import cross_asset_confirmation
from news_impact_engine import news_impact
from sector_rotation_engine import sector_rotation
from treasury_yield_engine import treasury_yield_signal
from credit_spread_engine import credit_market_signal
from vix_term_structure_engine import vix_term_structure
from technical_engine import technical_confirmation

router = APIRouter()


@router.get("/forecast/input")
def forecast_input():
    return get_forecast()


@router.get("/forecast/trade-bias")
def forecast_trade_bias():
    result = trade_bias()
    forecast = forecast_input()
    cross = cross_asset_confirmation(forecast)

    base_confidence = int(float(result.get("confidence", forecast.get("confidence", 0)) or 0))
    adjustment = int(cross.get("confidence_adjustment", 0) or 0)
    adjusted_confidence = max(0, min(100, base_confidence + adjustment))

    result["cross_asset_signal"] = cross.get("signal")
    result["cross_asset_score"] = cross.get("score")
    result["cross_asset_confidence_adjustment"] = adjustment
    result["adjusted_confidence"] = adjusted_confidence
    result["cross_asset_reasons"] = cross.get("reasons", [])
    result["cross_asset_inputs"] = cross.get("inputs", {})

    news = news_impact()
    result["news_bias"] = news.get("news_bias")
    result["news_score"] = news.get("news_score")
    result["raw_news_score"] = news.get("raw_news_score")
    result["news_severity"] = news.get("severity")
    result["news_source"] = news.get("source")
    result["news_top_headlines"] = news.get("top_headlines", [])[:3]

    sector = sector_rotation()
    treasury = treasury_yield_signal()
    credit = credit_market_signal()
    vix_term = vix_term_structure()

    _n = lambda x: float(str(x if x is not None else 0).replace("+", "").replace("%", "").replace("B", "").replace(",", "").strip() or 0)

    f = result.get("forecast", {}) or forecast or {}

    institutional_component = _n(f.get("bias_score", 0)) * 30
    cross_asset_component = _n(result.get("cross_asset_score", 0))
    sector_component = _n(sector.get("rotation_score", sector.get("score", 0)))
    treasury_component = _n(treasury.get("treasury_score", treasury.get("score", 0)))
    credit_component = _n(credit.get("credit_score", credit.get("score", 0)))
    vix_component = _n(vix_term.get("score", 0))
    news_component = _n(news.get("news_score", 0))

    gamma_regime_txt = str(f.get("gamma_regime", result.get("gamma_regime", ""))).upper()
    gamma_bias_txt = str(f.get("gamma_bias", "")).upper()

    gamma_component = (
        (10 if "POSITIVE" in gamma_regime_txt else -10 if "NEGATIVE" in gamma_regime_txt else 0)
        + (10 if "POSITIVE" in gamma_bias_txt else -10 if "NEGATIVE" in gamma_bias_txt else 0)
    )

    composite_score = round(
        institutional_component
        + gamma_component
        + cross_asset_component
        + sector_component
        + treasury_component
        + credit_component
        + vix_component
        + news_component,
        2,
    )

    desk_call = (
        "LONGS_PREFERRED" if composite_score >= 35
        else "SHORT_ONLY" if composite_score <= -35
        else "LEAN_BULLISH" if composite_score >= 15
        else "LEAN_BEARISH" if composite_score <= -15
        else "BALANCED"
    )

    result["sector_rotation"] = sector
    result["treasury_model"] = treasury
    result["credit_markets"] = credit
    result["vix_term_structure"] = vix_term
    result["forecast_composite_score"] = composite_score
    result["forecast_components"] = {
        "institutional": round(institutional_component, 2),
        "gamma": round(gamma_component, 2),
        "cross_asset": round(cross_asset_component, 2),
        "sector_rotation": round(sector_component, 2),
        "treasury": round(treasury_component, 2),
        "credit": round(credit_component, 2),
        "vix_term": round(vix_component, 2),
        "news": round(news_component, 2),
    }
    result["desk_call"] = desk_call
    result["technical_confirmation"] = technical_confirmation(ticker="SPY", interval="5m")

    return result
