from fastapi import APIRouter
from technical_engine import technical_confirmation

router = APIRouter()


@router.get("/technical/confirmation")
def technical_confirmation_endpoint(ticker: str = "SPY", interval: str = "5m"):
    return technical_confirmation(
        ticker=ticker.upper(),
        interval=interval,
    )
