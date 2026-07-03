from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.shared_ibkr_service import (
    ibkr_status,
    submit_stock_order,
    open_orders,
    cancel_order,
    positions,
    account_summary,
)

router = APIRouter()


class StockOrderRequest(BaseModel):
    symbol: str
    action: str
    quantity: int
    order_type: str = "MKT"
    limit_price: float | None = None


@router.get("/ibkr/shared/status")
def shared_status():
    return ibkr_status()


@router.get("/ibkr/shared/account")
def shared_account():
    return {"connected": True, "cash": account_summary()}


@router.get("/ibkr/shared/positions")
def shared_positions():
    return {"connected": True, "positions": positions()}


@router.get("/ibkr/shared/open-orders")
def shared_open_orders():
    return {"connected": True, "open_orders": open_orders()}


@router.post("/ibkr/shared/order")
def shared_submit_order(req: StockOrderRequest):
    try:
        return submit_stock_order(
            symbol=req.symbol,
            action=req.action,
            quantity=req.quantity,
            order_type=req.order_type,
            limit_price=req.limit_price,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ibkr/shared/cancel/{order_id}")
def shared_cancel_order(order_id: int):
    try:
        return cancel_order(order_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
