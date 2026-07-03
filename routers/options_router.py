from fastapi import APIRouter

router = APIRouter()


@router.get("/options/0dte-best-strike")
def options_best_strike_endpoint(ticker: str = "SPY"):
    from main import options_0dte_best_strike
    return options_0dte_best_strike(ticker=ticker.upper())
