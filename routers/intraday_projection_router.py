from fastapi import APIRouter
from forecast_engine.intraday_projection_engine import build_projection

router = APIRouter()


@router.get("/forecast/intraday-projection")
def intraday_projection():
    from main import (
        forecast_input,
        forecast_trade_bias,
        technical_confirmation,
        options_0dte_best_strike,
    )

    forecast = forecast_input()
    trade_bias = forecast_trade_bias()
    technical = technical_confirmation()
    option = options_0dte_best_strike("SPY")

    return build_projection(
        forecast,
        trade_bias,
        technical,
        option,
    )
