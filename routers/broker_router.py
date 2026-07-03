from fastapi import APIRouter
from pydantic import BaseModel

from services.ibkr_service import (
    account_summary,
    cancel_order,
    executions,
    open_orders,
    order_status,
    positions,
)


router = APIRouter(prefix="/broker", tags=["broker"])


class CancelOrderRequest(BaseModel):
    order_id: int


@router.get("/open-orders")
def broker_open_orders():
    try:
        return open_orders()
    except Exception as e:
        return {"ok": False, "endpoint": "open_orders", "error": str(e), "type": type(e).__name__}


@router.get("/order/{order_id}")
def broker_order_status(order_id: int):
    return order_status(order_id)


@router.post("/cancel")
def broker_cancel_order(req: CancelOrderRequest):
    return cancel_order(req.order_id)


@router.get("/positions")
def broker_positions():
    try:
        return positions()
    except Exception as e:
        return {"ok": False, "endpoint": "positions", "error": str(e), "type": type(e).__name__}


@router.get("/account")
def broker_account():
    try:
        return account_summary()
    except Exception as e:
        return {"ok": False, "endpoint": "account", "error": str(e), "type": type(e).__name__}


@router.get("/executions")
def broker_executions():
    return executions()
