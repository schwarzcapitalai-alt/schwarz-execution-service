from typing import Any, Dict, List
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from ib_insync import IB, Stock, MarketOrder, LimitOrder

IB_HOST = "127.0.0.1"
IB_PORT = 4002
IB_CLIENT_ID = 12001

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ibkr-broker")
_tls = threading.local()


def _ensure_loop():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _get_ib() -> IB:
    _ensure_loop()

    if not hasattr(_tls, "ib"):
        _tls.ib = IB()

    if not _tls.ib.isConnected():
        _tls.ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=10)

    return _tls.ib


def _run_on_broker(fn):
    fut = _executor.submit(lambda: fn(_get_ib()))
    return fut.result(timeout=30)


def ibkr_status() -> Dict[str, Any]:
    def work(ib: IB):
        return {
            "connected": ib.isConnected(),
            "host": IB_HOST,
            "port": IB_PORT,
            "client_id": IB_CLIENT_ID,
        }
    return _run_on_broker(work)


def submit_stock_order(symbol: str, action: str, quantity: int, order_type: str = "MKT", limit_price: float | None = None) -> Dict[str, Any]:
    def work(ib: IB):
        sym = symbol.upper()
        act = action.upper()
        typ = order_type.upper()
        qty = int(quantity)

        if act not in ["BUY", "SELL"]:
            raise ValueError("action must be BUY or SELL")
        if qty <= 0:
            raise ValueError("quantity must be positive")

        contract = Stock(sym, "SMART", "USD")

        if typ == "LMT":
            if limit_price is None:
                raise ValueError("limit_price required for LMT order")
            order = LimitOrder(act, qty, float(limit_price))
        else:
            order = MarketOrder(act, qty)

        trade = ib.placeOrder(contract, order)

        return {
            "submitted": True,
            "symbol": sym,
            "action": act,
            "quantity": qty,
            "order_type": typ,
            "order_id": getattr(trade.order, "orderId", None),
            "perm_id": getattr(trade.order, "permId", None),
            "status": getattr(trade.orderStatus, "status", None),
            "filled": getattr(trade.orderStatus, "filled", None),
            "remaining": getattr(trade.orderStatus, "remaining", None),
        }

    return _run_on_broker(work)


def open_orders() -> List[Dict[str, Any]]:
    def work(ib: IB):
        rows = []
        for trade in ib.trades():
            s = trade.orderStatus
            status = getattr(s, "status", None)

            remaining = getattr(s, "remaining", None)

            if status not in ["PendingSubmit", "PreSubmitted", "Submitted"]:
                continue

            try:
                if remaining is not None and float(remaining) <= 0:
                    continue
            except Exception:
                pass

            rows.append({
                "symbol": getattr(trade.contract, "symbol", None),
                "secType": getattr(trade.contract, "secType", None),
                "action": getattr(trade.order, "action", None),
                "quantity": getattr(trade.order, "totalQuantity", None),
                "order_id": getattr(trade.order, "orderId", None),
                "perm_id": getattr(trade.order, "permId", None),
                "status": status,
                "filled": getattr(s, "filled", None),
                "remaining": remaining,
            })
        return rows

    return _run_on_broker(work)


def cancel_order(order_id: int) -> Dict[str, Any]:
    def work(ib: IB):
        target = int(order_id)

        for trade in ib.trades():
            if int(getattr(trade.order, "orderId", -1)) == target:
                ib.cancelOrder(trade.order)
                return {
                    "cancel_requested": True,
                    "order_id": target,
                    "status": getattr(trade.orderStatus, "status", None),
                }

        return {
            "cancel_requested": False,
            "order_id": target,
            "error": "Order not found in shared broker trade cache",
        }

    return _run_on_broker(work)


def positions() -> List[Dict[str, Any]]:
    def work(ib: IB):
        return [
            {
                "account": p.account,
                "symbol": p.contract.symbol,
                "secType": p.contract.secType,
                "position": p.position,
                "avgCost": p.avgCost,
            }
            for p in ib.positions()
        ]

    return _run_on_broker(work)


def account_summary() -> List[Dict[str, Any]]:
    def work(ib: IB):
        wanted = {"NetLiquidation", "AvailableFunds", "BuyingPower", "ExcessLiquidity", "TotalCashValue"}
        return [
            {
                "account": item.account,
                "tag": item.tag,
                "value": item.value,
                "currency": item.currency,
            }
            for item in ib.accountValues()
            if item.tag in wanted
        ]

    return _run_on_broker(work)
