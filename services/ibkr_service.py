import os
import asyncio
from typing import Any, Dict, List

from ib_insync import IB


IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "4002"))
IB_CLIENT_ID_BASE = int(os.getenv("IB_CLIENT_ID_BASE", "12100"))


def _safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def connect_ib(client_offset: int = 0, timeout: int = 5) -> IB:
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    ib = IB()
    ib.connect(
        IB_HOST,
        IB_PORT,
        clientId=IB_CLIENT_ID_BASE + int(client_offset),
        timeout=timeout,
    )
    return ib


def open_orders() -> Dict[str, Any]:
    ib = connect_ib(1)
    try:
        ib.reqAllOpenOrders()
        ib.sleep(0.5)

        rows: List[Dict[str, Any]] = []
        for trade in ib.openTrades():
            c = trade.contract
            o = trade.order
            st = trade.orderStatus

            rows.append({
                "order_id": getattr(o, "orderId", None),
                "perm_id": getattr(o, "permId", None),
                "symbol": getattr(c, "symbol", None),
                "sec_type": getattr(c, "secType", None),
                "exchange": getattr(c, "exchange", None),
                "currency": getattr(c, "currency", None),
                "side": getattr(o, "action", None),
                "qty": _safe_float(getattr(o, "totalQuantity", None)),
                "order_type": getattr(o, "orderType", None),
                "limit_price": _safe_float(getattr(o, "lmtPrice", None)),
                "status": getattr(st, "status", None),
                "filled": _safe_float(getattr(st, "filled", None), 0),
                "remaining": _safe_float(getattr(st, "remaining", None), 0),
                "avg_fill_price": _safe_float(getattr(st, "avgFillPrice", None), 0),
            })

        return {"connected": ib.isConnected(), "count": len(rows), "open_orders": rows}
    finally:
        ib.disconnect()


def order_status(order_id: int) -> Dict[str, Any]:
    ib = connect_ib(2)
    try:
        ib.reqAllOpenOrders()
        ib.sleep(0.5)

        target = int(order_id)

        for trade in ib.trades() + ib.openTrades():
            o = trade.order
            st = trade.orderStatus
            c = trade.contract

            if int(getattr(o, "orderId", -1)) == target:
                return {
                    "found": True,
                    "order_id": getattr(o, "orderId", None),
                    "perm_id": getattr(o, "permId", None),
                    "symbol": getattr(c, "symbol", None),
                    "side": getattr(o, "action", None),
                    "qty": _safe_float(getattr(o, "totalQuantity", None)),
                    "order_type": getattr(o, "orderType", None),
                    "limit_price": _safe_float(getattr(o, "lmtPrice", None)),
                    "status": getattr(st, "status", None),
                    "filled": _safe_float(getattr(st, "filled", None), 0),
                    "remaining": _safe_float(getattr(st, "remaining", None), 0),
                    "avg_fill_price": _safe_float(getattr(st, "avgFillPrice", None), 0),
                }

        return {"found": False, "order_id": target, "status": "UNKNOWN_OR_NOT_IN_OPEN_SESSION_CACHE"}
    finally:
        ib.disconnect()


def cancel_order(order_id: int) -> Dict[str, Any]:
    ib = connect_ib(3)
    try:
        ib.reqAllOpenOrders()
        ib.sleep(0.5)

        target = int(order_id)

        for trade in ib.openTrades():
            o = trade.order
            if int(getattr(o, "orderId", -1)) == target:
                ib.cancelOrder(o)
                ib.sleep(0.5)
                st = trade.orderStatus
                return {
                    "cancel_requested": True,
                    "cancelled": getattr(st, "status", None) in ["Cancelled", "ApiCancelled"],
                    "order_id": target,
                    "status": getattr(st, "status", None),
                    "filled": _safe_float(getattr(st, "filled", None), 0),
                    "remaining": _safe_float(getattr(st, "remaining", None), 0),
                }

        try:
            ib.client.cancelOrder(target, "")
            ib.sleep(0.5)
            return {
                "cancel_requested": True,
                "cancelled": None,
                "order_id": target,
                "status": "CANCEL_SENT_DIRECT_BY_ORDER_ID",
            }
        except Exception as e:
            return {
                "cancel_requested": False,
                "cancelled": False,
                "order_id": target,
                "status": "ORDER_NOT_FOUND_OR_NOT_OPEN",
                "error": str(e),
                "type": type(e).__name__,
            }
    finally:
        ib.disconnect()

def positions() -> Dict[str, Any]:
    ib = connect_ib(4)
    try:
        rows: List[Dict[str, Any]] = []

        for pos in ib.positions():
            c = pos.contract
            rows.append({
                "account": getattr(pos, "account", None),
                "symbol": getattr(c, "symbol", None),
                "sec_type": getattr(c, "secType", None),
                "exchange": getattr(c, "exchange", None),
                "currency": getattr(c, "currency", None),
                "qty": _safe_float(getattr(pos, "position", None), 0),
                "avg_cost": _safe_float(getattr(pos, "avgCost", None), 0),
                "market_value_estimate": None,
                "unrealized_pnl": None,
                "realized_pnl": None,
            })

        return {"connected": ib.isConnected(), "count": len(rows), "positions": rows}
    finally:
        ib.disconnect()


def account_summary() -> Dict[str, Any]:
    ib = connect_ib(5)
    try:
        wanted = {
            "NetLiquidation",
            "TotalCashValue",
            "AvailableFunds",
            "BuyingPower",
            "ExcessLiquidity",
            "RealizedPnL",
            "UnrealizedPnL",
            "MaintMarginReq",
            "InitMarginReq",
        }

        rows = []
        for item in ib.accountSummary():
            if item.tag in wanted:
                rows.append({
                    "account": item.account,
                    "tag": item.tag,
                    "value": item.value,
                    "currency": item.currency,
                })

        return {"connected": ib.isConnected(), "summary": rows}
    finally:
        ib.disconnect()


def executions() -> Dict[str, Any]:
    ib = connect_ib(6)
    try:
        rows = []

        for fill in ib.fills():
            c = fill.contract
            e = fill.execution
            cr = fill.commissionReport

            rows.append({
                "symbol": getattr(c, "symbol", None),
                "sec_type": getattr(c, "secType", None),
                "side": getattr(e, "side", None),
                "shares": _safe_float(getattr(e, "shares", None), 0),
                "price": _safe_float(getattr(e, "price", None), 0),
                "time": str(getattr(e, "time", "")),
                "order_id": getattr(e, "orderId", None),
                "exec_id": getattr(e, "execId", None),
                "commission": _safe_float(getattr(cr, "commission", None), 0),
                "realized_pnl": _safe_float(getattr(cr, "realizedPNL", None), None),
            })

        return {"connected": ib.isConnected(), "count": len(rows), "executions": rows}
    finally:
        ib.disconnect()
