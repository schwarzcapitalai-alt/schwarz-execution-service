from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()


def fnum(v, default=None):
    try:
        if v is None:
            return default
        return float(str(v).replace(",", "").replace("B", "").replace("$", ""))
    except Exception:
        return default


@router.get("/dashboard/chart-snapshot")
def dashboard_chart_snapshot():
    try:
        from main import forecast_input, technical_confirmation
    except Exception:
        forecast_input = None
        technical_confirmation = None

    try:
        forecast = forecast_input() if forecast_input else {}
    except Exception:
        forecast = {}

    try:
        tech = technical_confirmation() if technical_confirmation else {}
    except Exception:
        tech = {}

    price = fnum(tech.get("last_price"), fnum(forecast.get("spy_price"), 0))
    ema20 = fnum(tech.get("ema20"))
    ema50 = fnum(tech.get("ema50"))

    call_wall = fnum(forecast.get("call_wall"))
    put_wall = fnum(forecast.get("put_wall"))
    gamma_flip = fnum(forecast.get("gamma_flip"))

    bias = forecast.get("institutional_bias", "N/A")
    confidence = forecast.get("confidence", "N/A")
    gamma_regime = forecast.get("gamma_regime", "N/A")
    net_gex = forecast.get("net_gex", "N/A")

    return {
        "service": "execution_service",
        "endpoint": "dashboard_chart_snapshot",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": forecast.get("ticker", "SPY"),
        "price": price,
        "ema20": ema20,
        "ema50": ema50,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_flip": gamma_flip,
        "institutional_bias": bias,
        "confidence": confidence,
        "gamma_regime": gamma_regime,
        "net_gex": net_gex,
        "technical": tech,
        "forecast": forecast,
    }


@router.get("/paper/dashboard-summary")
def paper_dashboard_summary():
    try:
        from main import forecast_trade_bias, technical_confirmation, system_mode
    except Exception:
        forecast_trade_bias = None
        technical_confirmation = None
        system_mode = None

    try:
        trade_bias = forecast_trade_bias() if forecast_trade_bias else {}
    except Exception as e:
        trade_bias = {"error": str(e)}

    try:
        tech = technical_confirmation() if technical_confirmation else {}
    except Exception as e:
        tech = {"error": str(e)}

    try:
        mode = system_mode() if system_mode else {}
    except Exception as e:
        mode = {"error": str(e)}

    return {
        "service": "execution_service",
        "endpoint": "paper_dashboard_summary",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "trade_bias": trade_bias,
        "technical_confirmation": tech,
    }
