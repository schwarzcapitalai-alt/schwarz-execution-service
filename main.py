from routers.dashboard_router import router as dashboard_router
from routers.health_router import router as health_router
from routers.forecast_router import router as forecast_router, forecast_input, forecast_trade_bias
from routers.system_router import router as system_router, system_mode
from routers.paper_router import router as paper_router
from routers.risk_router import router as risk_router, load_risk_limits, risk_kill_switch, risk_limits, risk_runtime, config_risk
from routers.technical_router import router as technical_router
from routers.options_router import router as options_router
from routers.account_router import router as account_router
from routers.safety_router import router as safety_router
from routers.autonomous_router import router as autonomous_router
from routers.analytics_router import router as analytics_router
from routers.broker_router import router as broker_router
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from routers.terminal_router import router as terminal_router
from routers.shared_ibkr_router import router as shared_ibkr_router
from decision_engine import build_decision
from technical_engine import technical_confirmation
from breadth_engine import market_breadth
from cross_asset_engine import cross_asset_confirmation
from news_impact_engine import news_impact
from treasury_yield_engine import treasury_yield_signal
from sector_rotation_engine import sector_rotation
from vix_term_structure_engine import vix_term_structure
from credit_spread_engine import credit_market_signal
from forecast_client import get_forecast, trade_bias
from pydantic import BaseModel
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.execution import ExecutionFilter
import threading
import itertools
import time
import os
import json
from routers.router_gate_router import router as router_gate_router
from datetime import datetime, timezone



class OrderProposalRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    estimated_price: float
    order_type: str = "MKT"
    limit_price: float | None = None
    time_in_force: str = "DAY"


class PreTradeRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    estimated_price: float


app = FastAPI()
app.mount("/bot-terminal", StaticFiles(directory="static/bot-terminal", html=True), name="bot_terminal")
app.include_router(terminal_router)
app.include_router(shared_ibkr_router)
app.include_router(broker_router)
from routers.intraday_projection_router import router as intraday_projection_router
app.include_router(intraday_projection_router)
app.include_router(router_gate_router)
app.include_router(health_router)
app.include_router(forecast_router)
app.include_router(system_router)
app.include_router(paper_router)
app.include_router(risk_router)
app.include_router(technical_router)
app.include_router(options_router)
app.include_router(account_router)
app.include_router(safety_router)
app.include_router(autonomous_router)
app.include_router(analytics_router)
app.include_router(dashboard_router)

IB_HOST = os.getenv("IB_HOST", "127.0.0.1")
IB_PORT = int(os.getenv("IB_PORT", "4002"))
IB_CLIENT_ID = int(os.getenv("IB_CLIENT_ID", "12001"))
CLIENT_ID_COUNTER = itertools.count(IB_CLIENT_ID)
EXECUTION_MODE = os.getenv("EXECUTION_MODE", "READ_ONLY")
AUDIT_LOG_PATH = os.getenv("AUDIT_LOG_PATH", "/tmp/pretrade_audit.jsonl")


ORDER_RATE_STATE = {
    "date": datetime.utcnow().date().isoformat(),
    "paper_orders_today": 0,
    "minute": int(time.time() // 60),
    "orders_this_minute": 0,
}
RISK_CONFIG_PATH = os.getenv("RISK_CONFIG_PATH", "/config/risk.json")
KILL_SWITCH_ENABLED = os.getenv("KILL_SWITCH_ENABLED", "true").lower() == "true"
KILL_SWITCH_REASON = os.getenv("KILL_SWITCH_REASON", "GLOBAL_TRADING_DISABLED_BY_DEFAULT")

RISK_LIMITS = {
    "max_notional_usd": 400.00,
    "max_quantity": 10,
    "allowed_symbols": ["SPY", "QQQ", "IWM", "SPX"],
    "blocked_sides": [],
    "execution": "READ_ONLY_PRETRADE_ONLY"
}



class IBApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.connected_flag = False
        self.account_summary_rows = []
        self.account_summary_done = False
        self.position_rows = []
        self.position_done = False
        self.open_order_rows = []
        self.open_order_done = False
        self.execution_rows = []
        self.execution_done = False

    def nextValidId(self, orderId):
        self.connected_flag = True

    def accountSummary(self, reqId, account, tag, value, currency):
        self.account_summary_rows.append({
            "account": account,
            "tag": tag,
            "value": value,
            "currency": currency,
        })

    def accountSummaryEnd(self, reqId):
        self.account_summary_done = True

    def position(self, account, contract, position, avgCost):
        self.position_rows.append({
            "account": account,
            "symbol": contract.symbol,
            "secType": contract.secType,
            "exchange": contract.exchange,
            "currency": contract.currency,
            "position": float(position),
            "avgCost": float(avgCost),
            "conId": contract.conId,
        })

    def positionEnd(self):
        self.position_done = True



    def openOrder(self, orderId, contract, order, orderState):
        self.open_order_rows.append({
            "orderId": orderId,
            "symbol": contract.symbol,
            "secType": contract.secType,
            "exchange": contract.exchange,
            "currency": contract.currency,
            "action": order.action,
            "orderType": order.orderType,
            "totalQuantity": float(order.totalQuantity),
            "lmtPrice": float(order.lmtPrice) if order.lmtPrice else None,
            "auxPrice": float(order.auxPrice) if order.auxPrice else None,
            "status": orderState.status,
        })

    def openOrderEnd(self):
        self.open_order_done = True

    def execDetails(self, reqId, contract, execution):
        self.execution_rows.append({
            "reqId": reqId,
            "symbol": contract.symbol,
            "secType": contract.secType,
            "exchange": contract.exchange,
            "currency": contract.currency,
            "execId": execution.execId,
            "time": execution.time,
            "acctNumber": execution.acctNumber,
            "side": execution.side,
            "shares": float(execution.shares),
            "price": float(execution.price),
            "orderId": execution.orderId,
            "clientId": execution.clientId,
        })

    def execDetailsEnd(self, reqId):
        self.execution_done = True


def connect_ib():
    app_ib = IBApp()
    client_id = next(CLIENT_ID_COUNTER)

    app_ib.connect(
        IB_HOST,
        IB_PORT,
        clientId=client_id
    )

    thread = threading.Thread(
        target=app_ib.run,
        daemon=True
    )

    thread.start()

    deadline = time.time() + 5

    while time.time() < deadline:
        if app_ib.connected_flag:
            break
        time.sleep(0.1)

    app_ib.client_id_used = client_id

    return app_ib


def load_risk_limits():
    try:
        with open(RISK_CONFIG_PATH, "r") as f:
            data = json.load(f)

        return {
            "max_notional_usd": float(data.get("max_notional_usd", 0)),
            "max_quantity": float(data.get("max_quantity", 0)),
            "allowed_symbols": [str(x).upper() for x in data.get("allowed_symbols", [])],
            "blocked_sides": [str(x).upper() for x in data.get("blocked_sides", [])],
            "allowed_accounts": [str(x) for x in data.get("allowed_accounts", [])],
            "execution": data.get("execution", "READ_ONLY_PRETRADE_ONLY"),
            "max_daily_loss_usd": float(data.get("max_daily_loss_usd", 0) or 0),
            "max_trades_per_day": int(data.get("max_trades_per_day", 0) or 0),
            "max_orders_per_minute": int(data.get("max_orders_per_minute", 0) or 0),
            "paper_trading_enabled": bool(data.get("paper_trading_enabled", True)),
            "live_trading_enabled": bool(data.get("live_trading_enabled", False)),
            "live_trading_requires_manual_approval": bool(data.get("live_trading_requires_manual_approval", True))
        }

    except Exception as e:
        return {
            "max_notional_usd": 0,
            "max_quantity": 0,
            "allowed_symbols": [],
            "blocked_sides": ["BUY", "SELL"],
            "allowed_accounts": [],
            "execution": f"RISK_CONFIG_LOAD_FAILED: {e}"
        }



def visible_accounts_from_cash_rows(cash_rows):
    return sorted({
        row.get("account")
        for row in cash_rows
        if row.get("account")
    })


def account_allowlist_check(cash_rows):
    limits = load_risk_limits()

    allowed = set(limits.get("allowed_accounts", []))
    visible = set(visible_accounts_from_cash_rows(cash_rows))

    if not allowed:
        return {
            "ok": False,
            "allowed_accounts": [],
            "visible_accounts": sorted(visible),
            "error": "allowed_accounts is empty."
        }

    if not visible:
        return {
            "ok": False,
            "allowed_accounts": sorted(allowed),
            "visible_accounts": [],
            "error": "no visible IB accounts found."
        }

    unapproved = sorted(visible - allowed)

    if unapproved:
        return {
            "ok": False,
            "allowed_accounts": sorted(allowed),
            "visible_accounts": sorted(visible),
            "unapproved_accounts": unapproved,
            "error": "visible IB account is not in allowed_accounts."
        }

    return {
        "ok": True,
        "allowed_accounts": sorted(allowed),
        "visible_accounts": sorted(visible),
        "error": None
    }


def write_audit_log(event):
    try:
        event["ts_utc"] = datetime.now(timezone.utc).isoformat()

        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps(event, sort_keys=True) + "\n")

    except Exception as e:
        print(f"AUDIT_LOG_WRITE_FAILED: {e}", flush=True)


def dedupe_rows(rows):
    seen = set()
    out = []

    for row in rows:
        key = tuple(sorted(row.items()))
        if key in seen:
            continue

        seen.add(key)
        out.append(row)

    return out


@app.get("/")
def root():
    market = forecast_trade_bias()
    tech = market.get("technical_confirmation", {}) or {}

    desk_call = market.get("desk_call", "BALANCED")
    technical_permission = tech.get("bot_permission", "WAIT")

    execution_signal = "WAIT"

    if desk_call in ["LONGS_PREFERRED", "LEAN_BULLISH"] and technical_permission == "LONGS_ALLOWED":
        execution_signal = "EXECUTE_LONG"

    elif desk_call in ["SHORT_ONLY", "LEAN_BEARISH"] and technical_permission == "SHORTS_ALLOWED":
        execution_signal = "EXECUTE_SHORT"

    return {
        "service": "execution_service",
        "market_permission": {
            "desk_call": desk_call,
            "technical_permission": technical_permission,
            "execution_signal": execution_signal
        },
        "mode": EXECUTION_MODE
    }


@app.get("/health")
def health():
    return {
        "service": "execution_service",
        "status": "healthy"
    }










@app.post("/pretrade/check")
def pretrade_check(req: PreTradeRequest):
    side = req.side.upper().strip()
    symbol = req.symbol.upper().strip()
    notional = float(req.quantity) * float(req.estimated_price)

    snapshot = account_snapshot()
    cash_rows = snapshot.get("cash", [])
    account_check = account_allowlist_check(cash_rows)
    available_funds = None

    for row in cash_rows:
        if row.get("tag") == "AvailableFunds":
            try:
                available_funds = float(row.get("value"))
            except Exception:
                available_funds = None

    errors = []
    warnings = []

    if KILL_SWITCH_ENABLED:
        errors.append("global kill switch is enabled.")

    if not account_check.get("ok"):
        errors.append(account_check.get("error", "account allowlist check failed."))

    if EXECUTION_MODE != "READ_ONLY":
        errors.append("Service is not in READ_ONLY mode.")

    if side not in {"BUY", "SELL"}:
        errors.append("side must be BUY or SELL.")

    if req.quantity <= 0:
        errors.append("quantity must be greater than zero.")

    if req.estimated_price <= 0:
        errors.append("estimated_price must be greater than zero.")

    allowed_symbols = set(load_risk_limits().get("allowed_symbols", []))
    blocked_sides = set(load_risk_limits().get("blocked_sides", []))
    max_notional = float(load_risk_limits().get("max_notional_usd", 0))
    max_quantity = float(load_risk_limits().get("max_quantity", 0))

    if symbol not in allowed_symbols:
        errors.append("symbol is not in allowed_symbols.")

    if side in blocked_sides:
        errors.append("side is currently blocked by risk limits.")

    if max_notional > 0 and notional > max_notional:
        errors.append("estimated notional exceeds max_notional_usd.")

    if max_quantity > 0 and req.quantity > max_quantity:
        errors.append("quantity exceeds max_quantity.")

    if side == "BUY" and available_funds is not None and notional > available_funds:
        errors.append("estimated notional exceeds AvailableFunds.")

    if available_funds is None:
        warnings.append("AvailableFunds unavailable; cash check incomplete.")

    result = {
        "allowed": len(errors) == 0,
        "mode": EXECUTION_MODE,
        "symbol": symbol,
        "side": side,
        "quantity": req.quantity,
        "estimated_price": req.estimated_price,
        "estimated_notional": notional,
        "available_funds": available_funds,
        "account_check": account_check,
        "errors": errors,
        "warnings": warnings,
        "kill_switch_enabled": KILL_SWITCH_ENABLED,
        "kill_switch_reason": KILL_SWITCH_REASON,
        "risk_limits": load_risk_limits(),
        "execution": "DISABLED_READ_ONLY_NO_ORDER_ROUTE"
    }

    write_audit_log({
        "event": "pretrade_check",
        "request": {
            "symbol": req.symbol,
            "side": req.side,
            "quantity": req.quantity,
            "estimated_price": req.estimated_price
        },
        "result": result
    })

    return result


@app.get("/audit/pretrade")
def audit_pretrade_tail(limit: int = 20):
    limit = max(1, min(int(limit), 100))

    try:
        with open(AUDIT_LOG_PATH, "r") as f:
            lines = f.readlines()[-limit:]

        rows = []
        for line in lines:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass

        return {
            "mode": EXECUTION_MODE,
            "audit_log_path": AUDIT_LOG_PATH,
            "count": len(rows),
            "events": rows
        }

    except FileNotFoundError:
        return {
            "mode": EXECUTION_MODE,
            "audit_log_path": AUDIT_LOG_PATH,
            "count": 0,
            "events": []
        }


@app.get("/orders/open")
def orders_open():
    app_ib = connect_ib()

    if not app_ib.connected_flag:
        return {
            "connected": False,
            "mode": EXECUTION_MODE,
            "open_orders": []
        }

    app_ib.reqOpenOrders()

    deadline = time.time() + 8
    while time.time() < deadline:
        if app_ib.open_order_done:
            break
        time.sleep(0.1)

    result = {
        "connected": app_ib.connected_flag,
        "mode": EXECUTION_MODE,
        "open_orders": app_ib.open_order_rows,
        "execution": "DISABLED_READ_ONLY_NO_ORDER_ROUTE"
    }

    app_ib.disconnect()
    return result


@app.get("/executions/recent")
def executions_recent():
    app_ib = connect_ib()

    if not app_ib.connected_flag:
        return {
            "connected": False,
            "mode": EXECUTION_MODE,
            "executions": []
        }

    app_ib.reqExecutions(9301, ExecutionFilter())

    deadline = time.time() + 8
    while time.time() < deadline:
        if app_ib.execution_done:
            break
        time.sleep(0.1)

    result = {
        "connected": app_ib.connected_flag,
        "mode": EXECUTION_MODE,
        "executions": app_ib.execution_rows,
        "execution": "DISABLED_READ_ONLY_NO_ORDER_ROUTE"
    }

    app_ib.disconnect()
    return result


@app.post("/order/proposal")
def order_proposal(req: OrderProposalRequest):
    pretrade = pretrade_check(
        PreTradeRequest(
            symbol=req.symbol,
            side=req.side,
            quantity=req.quantity,
            estimated_price=req.estimated_price
        )
    )

    order_type = req.order_type.upper().strip()
    tif = req.time_in_force.upper().strip()
    side = req.side.upper().strip()
    symbol = req.symbol.upper().strip()

    errors = list(pretrade.get("errors", []))
    warnings = list(pretrade.get("warnings", []))

    if order_type not in {"MKT", "LMT"}:
        errors.append("order_type must be MKT or LMT.")

    if tif not in {"DAY"}:
        errors.append("time_in_force must be DAY.")

    if order_type == "LMT" and (req.limit_price is None or req.limit_price <= 0):
        errors.append("limit_price is required and must be greater than zero for LMT orders.")

    proposal = {
        "symbol": symbol,
        "side": side,
        "quantity": req.quantity,
        "order_type": order_type,
        "limit_price": req.limit_price if order_type == "LMT" else None,
        "time_in_force": tif,
        "estimated_price": req.estimated_price,
        "estimated_notional": pretrade.get("estimated_notional"),
        "status": "PROPOSED_DRY_RUN_ONLY"
    }

    return {
        "accepted": len(errors) == 0,
        "mode": EXECUTION_MODE,
        "proposal": proposal,
        "pretrade": pretrade,
        "errors": errors,
        "warnings": warnings,
        "kill_switch_enabled": KILL_SWITCH_ENABLED,
        "kill_switch_reason": KILL_SWITCH_REASON,
        "execution": "DISABLED_DRY_RUN_ONLY_NO_ORDER_ROUTE"
    }






def load_order_rate_state_from_disk():
    try:
        if os.path.exists(RISK_RUNTIME_STATE_PATH):
            with open(RISK_RUNTIME_STATE_PATH, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                ORDER_RATE_STATE.update(data)
                ORDER_RATE_STATE["paper_orders_today"] = int(ORDER_RATE_STATE.get("paper_orders_today", 0))
                ORDER_RATE_STATE["orders_this_minute"] = int(ORDER_RATE_STATE.get("orders_this_minute", 0))
                ORDER_RATE_STATE["minute"] = int(ORDER_RATE_STATE.get("minute", int(time.time() // 60)))
    except Exception:
        pass

def save_order_rate_state_to_disk():
    try:
        with open(RISK_RUNTIME_STATE_PATH, "w") as f:
            json.dump(ORDER_RATE_STATE, f)
    except Exception:
        pass

load_order_rate_state_from_disk()

def order_rate_state():
    today = datetime.utcnow().date().isoformat()
    minute = int(time.time() // 60)

    if ORDER_RATE_STATE["date"] != today:
        ORDER_RATE_STATE["date"] = today
        ORDER_RATE_STATE["paper_orders_today"] = 0

    if ORDER_RATE_STATE["minute"] != minute:
        ORDER_RATE_STATE["minute"] = minute
        ORDER_RATE_STATE["orders_this_minute"] = 0

    return ORDER_RATE_STATE

def record_paper_order_accept():
    st = order_rate_state()
    st["paper_orders_today"] += 1
    st["orders_this_minute"] += 1
    save_order_rate_state_to_disk()



class PaperOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: float
    estimated_price: float = 0
    price: float = 0
    order_type: str = "MARKET"


@app.post("/orders/paper")
def paper_order(req: PaperOrderRequest):

    limits = load_risk_limits()

    symbol = req.symbol.upper()
    side = req.side.upper()

    allowed_symbols = limits.get("allowed_symbols", [])
    blocked_sides = limits.get("blocked_sides", [])
    max_qty = float(limits.get("max_quantity", 0))
    px = float(req.price or req.estimated_price or 0)
    notional = abs(float(req.quantity) * px)
    max_notional = float(limits.get("max_notional_usd", 0) or 0)
    max_trades_per_day = int(limits.get("max_trades_per_day", 0) or 0)
    max_orders_per_minute = int(limits.get("max_orders_per_minute", 0) or 0)
    rate_state = order_rate_state()

    checks = {
        "symbol_allowed": symbol in allowed_symbols,
        "side_allowed": side not in blocked_sides,
        "qty_allowed": req.quantity <= max_qty,
        "notional_allowed": (
            max_notional <= 0 or
            px <= 0 or
            notional <= max_notional
        ),
        "daily_trade_count_allowed": (
            max_trades_per_day <= 0 or
            rate_state["paper_orders_today"] < max_trades_per_day
        ),
        "order_rate_allowed": (
            max_orders_per_minute <= 0 or
            rate_state["orders_this_minute"] < max_orders_per_minute
        ),
        "read_only_mode": EXECUTION_MODE == "READ_ONLY",
        "paper_mode": EXECUTION_MODE == "PAPER_ONLY",
        "live_mode": EXECUTION_MODE == "LIVE_ENABLED"
    }

    reject_reasons = []

    if not checks["symbol_allowed"]:
        reject_reasons.append("SYMBOL_NOT_ALLOWED")

    if not checks["side_allowed"]:
        reject_reasons.append("SIDE_BLOCKED")

    if not checks["qty_allowed"]:
        reject_reasons.append("QUANTITY_EXCEEDS_LIMIT")

    if not checks["notional_allowed"]:
        reject_reasons.append("NOTIONAL_EXCEEDS_LIMIT")

    if not checks["daily_trade_count_allowed"]:
        reject_reasons.append("MAX_TRADES_PER_DAY_EXCEEDED")

    if not checks["order_rate_allowed"]:
        reject_reasons.append("MAX_ORDERS_PER_MINUTE_EXCEEDED")

    approved = (
        checks["symbol_allowed"] and
        checks["side_allowed"] and
        checks["qty_allowed"] and
        checks["notional_allowed"] and
        checks["daily_trade_count_allowed"] and
        checks["order_rate_allowed"] and
        checks["paper_mode"]
    )

    if not checks["paper_mode"]:
        reject_reasons.append("PAPER_MODE_NOT_ENABLED")

    record = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "mode": EXECUTION_MODE,
        "approved": approved,
        "reject_reasons": reject_reasons,
        "checks": checks,
        "rate_state": dict(rate_state),
        "order": {
            "symbol": symbol,
            "side": side,
            "quantity": req.quantity,
            "price": px,
            "notional": notional,
            "order_type": req.order_type
        },
        "execution": "PAPER_SIMULATED_ONLY_NO_LIVE_ORDER"
    }

    if approved:
        record_paper_order_accept()

    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")

    return record


@app.post("/orders/ibkr-paper")
def ibkr_paper_order(req: PaperOrderRequest):
    import subprocess
    import sys
    import os

    gate = paper_order(req)

    if not gate.get("approved"):
        gate["execution"] = "IBKR_PAPER_REJECTED_BY_PRETRADE"
        return gate

    mode = system_mode()
    if mode.get("execution_mode") != "PAPER_ONLY":
        gate["approved"] = False
        gate["execution"] = "IBKR_PAPER_BLOCKED_NOT_PAPER_ONLY"
        return gate

    if mode.get("live_enabled"):
        gate["approved"] = False
        gate["execution"] = "IBKR_PAPER_BLOCKED_LIVE_ENABLED"
        return gate

    payload = {
        "host": IB_HOST,
        "port": IB_PORT,
        "client_id": 12031,
        "symbol": req.symbol.upper(),
        "side": req.side.upper(),
        "quantity": int(req.quantity),
        "order_type": req.order_type.upper(),
        "price": float(req.price or req.estimated_price or 0),
    }

    code = r"""
import json, os
from ib_insync import IB, Stock, MarketOrder, LimitOrder

p = json.loads(os.environ["ORDER_PAYLOAD"])
ib = IB()
ib.connect(p["host"], int(p["port"]), clientId=int(p["client_id"]), timeout=15)

contract = Stock(p["symbol"], "SMART", "USD")
ib.qualifyContracts(contract)

if p["order_type"] == "LIMIT":
    if not p["price"]:
        raise ValueError("LIMIT_ORDER_REQUIRES_PRICE")
    order = LimitOrder(p["side"], int(p["quantity"]), float(p["price"]))
else:
    order = MarketOrder(p["side"], int(p["quantity"]))

trade = ib.placeOrder(contract, order)
ib.sleep(2)

print(json.dumps({
    "connected": ib.isConnected(),
    "accounts": ib.managedAccounts(),
    "order_id": getattr(trade.order, "orderId", None),
    "perm_id": getattr(trade.order, "permId", None),
    "status": getattr(trade.orderStatus, "status", None),
    "filled": getattr(trade.orderStatus, "filled", None),
    "remaining": getattr(trade.orderStatus, "remaining", None),
    "avg_fill_price": getattr(trade.orderStatus, "avgFillPrice", None),
}))

ib.disconnect()
"""

    env = dict(os.environ)
    env["ORDER_PAYLOAD"] = json.dumps(payload)

    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        if result.returncode != 0:
            gate["approved"] = False
            gate["execution"] = "IBKR_PAPER_ORDER_FAILED"
            gate["error"] = result.stderr.strip() or result.stdout.strip()
            return gate

        ibkr = json.loads(result.stdout.strip().splitlines()[-1])

        record = {
            **gate,
            "execution": "IBKR_PAPER_ORDER_SUBMITTED",
            "ibkr": ibkr,
        }

        with open(AUDIT_LOG_PATH, "a") as f:
            f.write(json.dumps(record) + "\n")

        return record

    except Exception as e:
        gate["approved"] = False
        gate["execution"] = "IBKR_PAPER_ORDER_FAILED"
        gate["error"] = str(e)
        return gate


@app.get("/orders/audit")
def audit_orders():

    if not os.path.exists(AUDIT_LOG_PATH):
        return {
            "count": 0,
            "orders": []
        }

    rows = []

    with open(AUDIT_LOG_PATH, "r") as f:
        for line in f.readlines()[-100:]:
            try:
                rows.append(json.loads(line))
            except:
                pass

    return {
        "count": len(rows),
        "orders": rows
    }



@app.post("/orders/pretrade")
def pretrade_order(req: PaperOrderRequest):

    limits = load_risk_limits()

    symbol = req.symbol.upper()
    side = req.side.upper()

    allowed_symbols = limits.get("allowed_symbols", [])
    blocked_sides = limits.get("blocked_sides", [])
    max_qty = float(limits.get("max_quantity", 0))
    px = float(req.price or req.estimated_price or 0)
    notional = abs(float(req.quantity) * px)
    max_notional = float(limits.get("max_notional_usd", 0) or 0)
    max_trades_per_day = int(limits.get("max_trades_per_day", 0) or 0)
    max_orders_per_minute = int(limits.get("max_orders_per_minute", 0) or 0)
    rate_state = order_rate_state()

    checks = {
        "symbol_allowed": symbol in allowed_symbols,
        "side_allowed": side not in blocked_sides,
        "qty_allowed": req.quantity <= max_qty,
        "notional_allowed": (
            max_notional <= 0 or
            px <= 0 or
            notional <= max_notional
        ),
        "daily_trade_count_allowed": (
            max_trades_per_day <= 0 or
            rate_state["paper_orders_today"] < max_trades_per_day
        ),
        "order_rate_allowed": (
            max_orders_per_minute <= 0 or
            rate_state["orders_this_minute"] < max_orders_per_minute
        ),
        "read_only_mode": EXECUTION_MODE == "READ_ONLY",
        "paper_mode": EXECUTION_MODE == "PAPER_ONLY",
        "live_mode": EXECUTION_MODE == "LIVE_ENABLED",
        "kill_switch_blocks_live": True
    }

    reject_reasons = []

    if not checks["symbol_allowed"]:
        reject_reasons.append("SYMBOL_NOT_ALLOWED")

    if not checks["side_allowed"]:
        reject_reasons.append("SIDE_BLOCKED")

    if not checks["qty_allowed"]:
        reject_reasons.append("QUANTITY_EXCEEDS_LIMIT")

    if not checks["notional_allowed"]:
        reject_reasons.append("NOTIONAL_EXCEEDS_LIMIT")

    if not checks["daily_trade_count_allowed"]:
        reject_reasons.append("MAX_TRADES_PER_DAY_EXCEEDED")

    if not checks["order_rate_allowed"]:
        reject_reasons.append("MAX_ORDERS_PER_MINUTE_EXCEEDED")

    if checks["read_only_mode"]:
        reject_reasons.append("READ_ONLY_MODE_BLOCKS_LIVE_EXECUTION")

    if not bool(limits.get("live_trading_enabled", False)):
        reject_reasons.append("LIVE_TRADING_DISABLED")

    if bool(limits.get("live_trading_requires_manual_approval", True)):
        reject_reasons.append("MANUAL_APPROVAL_REQUIRED_FOR_LIVE")

    paper_approved = (
        checks["symbol_allowed"] and
        checks["side_allowed"] and
        checks["qty_allowed"] and
        checks["notional_allowed"] and
        checks["daily_trade_count_allowed"] and
        checks["order_rate_allowed"] and
        checks["paper_mode"]
    )

    live_approved = (
        checks["symbol_allowed"] and
        checks["side_allowed"] and
        checks["qty_allowed"] and
        checks["notional_allowed"] and
        checks["daily_trade_count_allowed"] and
        checks["order_rate_allowed"] and
        checks["live_mode"]
    )

    record = {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "mode": EXECUTION_MODE,
        "paper_approved": paper_approved,
        "paper_approved": paper_approved,
        "live_approved": live_approved,
        "reject_reasons": reject_reasons,
        "checks": checks,
        "rate_state": dict(rate_state),
        "order": {
            "symbol": symbol,
            "side": side,
            "quantity": req.quantity,
            "price": px,
            "notional": notional,
            "order_type": req.order_type
        },
        "execution": "BLOCKED_PRETRADE_ONLY_NO_LIVE_ORDER"
    }

    with open(AUDIT_LOG_PATH, "a") as f:
        f.write(json.dumps(record) + "\n")

    return record




def permission_gate_for_order(order):
    perm = execution_permission()

    if perm.get("can_route_orders") is not True:
        return False, {
            "accepted": False,
            "blocked": True,
            "reason": "EXECUTION_PERMISSION_DENIED",
            "permission": perm,
        }

    risk_limits = perm.get("risk_limits", {})
    symbol = str(order.get("symbol", "")).upper()
    qty = float(order.get("quantity", order.get("qty", 0)) or 0)
    price = float(order.get("limit_price", order.get("price", 0)) or 0)
    notional = abs(qty * price) if price else 0

    allowed = risk_limits.get("allowed_symbols", [])
    if allowed and symbol not in allowed:
        return False, {
            "accepted": False,
            "blocked": True,
            "reason": "SYMBOL_NOT_ALLOWED",
            "symbol": symbol,
            "allowed_symbols": allowed,
        }

    max_qty = float(risk_limits.get("max_quantity", 0) or 0)
    if max_qty and abs(qty) > max_qty:
        return False, {
            "accepted": False,
            "blocked": True,
            "reason": "QUANTITY_LIMIT_EXCEEDED",
            "quantity": qty,
            "max_quantity": max_qty,
        }

    max_notional = float(risk_limits.get("max_notional_usd", 0) or 0)
    if max_notional and notional and notional > max_notional:
        return False, {
            "accepted": False,
            "blocked": True,
            "reason": "NOTIONAL_LIMIT_EXCEEDED",
            "notional_usd": notional,
            "max_notional_usd": max_notional,
        }

    return True, {
        "accepted": True,
        "blocked": False,
        "permission": perm,
    }

@app.post("/orders/route")
def route_order(req: PaperOrderRequest):
    order = {
        "symbol": req.symbol,
        "side": req.side,
        "quantity": req.quantity,
        "price": getattr(req, "price", 0),
        "limit_price": getattr(req, "limit_price", 0),
        "order_type": getattr(req, "order_type", "MARKET"),
    }

    ok, gate = permission_gate_for_order(order)
    if not ok:
        return gate

    pretrade = pretrade_check(req)

    route_allowed = (
        pretrade.get("live_approved") is True
        and pretrade.get("paper_approved") is True
    )

    return {
        "timestamp_utc": datetime.utcnow().isoformat(),
        "mode": EXECUTION_MODE,
        "route_allowed": route_allowed,
        "permission": gate,
        "pretrade": pretrade,
        "execution": "ROUTE_ALLOWED_PENDING_BROKER_SEND" if route_allowed else "ROUTE_BLOCKED_NO_LIVE_ORDER",
    }

@app.get("/system/mode")
def system_mode():
    try:
        with open("/config/risk.json", "r") as f:
            risk = json.load(f)
    except Exception:
        risk = {}

    execution_mode = EXECUTION_MODE
    read_only = execution_mode == "READ_ONLY"

    paper_enabled = (
        execution_mode in ["PAPER", "PAPER_ONLY"]
        and bool(risk.get("paper_trading_enabled", False))
    )

    live_enabled = (
        execution_mode in ["LIVE", "LIVE_ONLY"]
        and bool(risk.get("live_trading_enabled", False))
    )

    kill_switch_enabled = bool(risk.get("kill_switch_enabled", True))

    routing_active = bool(paper_enabled or live_enabled) and not read_only

    return {
        "service": "execution_service",
        "execution_mode": execution_mode,
        "read_only": read_only,
        "paper_enabled": paper_enabled,
        "live_enabled": live_enabled,
        "kill_switch_enabled": kill_switch_enabled,
        "routing_active": routing_active,
    }






@app.get("/risk/runtime")
def risk_runtime():

    limits = load_risk_limits()
    st = order_rate_state()

    return {
        "service": "execution_service",
        "mode": EXECUTION_MODE,
        "risk_config_path": RISK_CONFIG_PATH,

        "limits": {
            "max_notional_usd": limits.get("max_notional_usd"),
            "max_quantity": limits.get("max_quantity"),
            "max_daily_loss_usd": limits.get("max_daily_loss_usd"),
            "max_trades_per_day": limits.get("max_trades_per_day"),
            "max_orders_per_minute": limits.get("max_orders_per_minute"),
            "allowed_symbols": limits.get("allowed_symbols"),
            "blocked_sides": limits.get("blocked_sides"),
            "paper_trading_enabled": limits.get("paper_trading_enabled"),
            "live_trading_enabled": limits.get("live_trading_enabled"),
            "live_trading_requires_manual_approval": limits.get("live_trading_requires_manual_approval"),
        },

        "runtime_state": dict(st),

        "remaining": {
            "trades_today": (
                None if not limits.get("max_trades_per_day")
                else max(
                    0,
                    int(limits.get("max_trades_per_day"))
                    - int(st.get("paper_orders_today", 0))
                )
            ),

            "orders_this_minute": (
                None if not limits.get("max_orders_per_minute")
                else max(
                    0,
                    int(limits.get("max_orders_per_minute"))
                    - int(st.get("orders_this_minute", 0))
                )
            ),
        },

        "live_ordering_possible": False,
        "execution": "RUNTIME_RISK_STATUS_ONLY"
    }



def _as_dict(x):
    return x if isinstance(x, dict) else {}


def permission_risk_limits():
    try:
        with open("/config/risk.json", "r") as f:
            data = json.load(f)
    except Exception:
        data = {}

    limits = data.get("limits") if isinstance(data.get("limits"), dict) else data
    if not isinstance(limits, dict):
        limits = {}

    keys = [
        "max_notional_usd",
        "max_quantity",
        "max_daily_loss_usd",
        "max_trades_per_day",
        "max_orders_per_minute",
        "allowed_symbols",
        "blocked_sides",
        "paper_trading_enabled",
        "live_trading_enabled",
        "require_kill_switch_off_for_live",
        "emergency_flatten_enabled",
        "live_trading_requires_manual_approval",
        "execution",
    ]
    return {k: limits.get(k) for k in keys if k in limits}


def permission_runtime_counters():
    out = {}

    try:
        with open("/config/execution_risk_runtime_state.json", "r") as f:
            out["persisted"] = json.load(f)
    except Exception:
        out["persisted"] = {}

    try:
        out["order_rate_state"] = ORDER_RATE_STATE
    except Exception:
        out["order_rate_state"] = {}

    return out


@app.get("/execution/permission")
def execution_permission():
    mode = system_mode()
    from routers.safety_router import safety_summary
    safety = safety_summary()
    risk = load_risk_limits()
    runtime = runtime_risk_state()

    block_reasons = []

    can_trade_paper = (
        mode.get("paper_enabled") is True
    )

    can_trade_live = (
        mode.get("live_enabled") is True
        and not mode.get("kill_switch_enabled")
    )

    if mode.get("kill_switch_enabled"):
        block_reasons.append("KILL_SWITCH_ENABLED")

    if not mode.get("live_enabled"):
        block_reasons.append("LIVE_TRADING_DISABLED")

    if not mode.get("paper_enabled"):
        block_reasons.append("PAPER_TRADING_DISABLED")

    verdict = (
        "PAPER_TRADING_ALLOWED"
        if can_trade_paper else
        "TRADING_BLOCKED"
    )

    market = forecast_trade_bias()
    tech = market.get("technical_confirmation", {}) or {}

    desk_call = market.get("desk_call", "BALANCED")
    technical_permission = tech.get("bot_permission", "WAIT")

    execution_signal = "WAIT"

    if desk_call in ["LONGS_PREFERRED", "LEAN_BULLISH"] and technical_permission == "LONGS_ALLOWED":
        execution_signal = "EXECUTE_LONG"
    elif desk_call in ["SHORT_ONLY", "LEAN_BEARISH"] and technical_permission == "SHORTS_ALLOWED":
        execution_signal = "EXECUTE_SHORT"

    return {
        "service": "execution_service",
        "market_permission": {
            "desk_call": desk_call,
            "technical_permission": technical_permission,
            "execution_signal": execution_signal
        },
        "can_trade_paper": can_trade_paper,
        "can_trade_live": can_trade_live,
        "block_reasons": block_reasons,
        "kill_switch": {
            "enabled": mode.get("kill_switch_enabled")
        },
        "mode": mode,
        "safety": safety,
        "risk_limits": risk,
        "runtime_counters": runtime,
        "ib_status": {
            "connected": safety.get("ib_connected"),
            "api_ready": safety.get("ib_api_ready"),
            "account_allowlisted": safety.get("account_allowlisted"),
        },
        "verdict": verdict,
        "can_route_orders": can_trade_paper or can_trade_live,
    }


def runtime_risk_state():
    return risk_runtime()


@app.get("/forecast/input")
def forecast_input():
    return get_forecast()

@app.get("/forecast/trade-bias")
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
    gamma_component = (10 if "POSITIVE" in gamma_regime_txt else -10 if "NEGATIVE" in gamma_regime_txt else 0) + (10 if "POSITIVE" in gamma_bias_txt else -10 if "NEGATIVE" in gamma_bias_txt else 0)
    composite_score = round(institutional_component + gamma_component + cross_asset_component + sector_component + treasury_component + credit_component + vix_component + news_component, 2)
    desk_call = "LONGS_PREFERRED" if composite_score >= 35 else "SHORT_ONLY" if composite_score <= -35 else "LEAN_BULLISH" if composite_score >= 15 else "LEAN_BEARISH" if composite_score <= -15 else "BALANCED"
    result["sector_rotation"] = sector
    result["treasury_model"] = treasury
    result["credit_markets"] = credit
    result["vix_term_structure"] = vix_term
    result["forecast_composite_score"] = composite_score
    result["forecast_components"] = {"institutional": round(institutional_component, 2), "gamma": round(gamma_component, 2), "cross_asset": round(cross_asset_component, 2), "sector_rotation": round(sector_component, 2), "treasury": round(treasury_component, 2), "credit": round(credit_component, 2), "vix_term": round(vix_component, 2), "news": round(news_component, 2)}
    result["desk_call"] = desk_call
    result["technical_confirmation"] = technical_confirmation(ticker="SPY", interval="5m")
    return result


@app.get("/options/0dte-best-strike")
def options_0dte_best_strike(ticker: str = "SPY"):
    from datetime import datetime, timezone
    from options.best_0dte import choose_best_0dte
    from options.uw_live import uw_option_contract_id, fetch_contract

    forecast = forecast_input()
    trade_bias = forecast_trade_bias()

    try:
        tech = technical_confirmation(ticker=ticker.upper(), interval="5m")
    except Exception:
        tech = trade_bias.get("technical_confirmation", {}) or {}

    decision = build_decision(forecast, trade_bias, tech)

    if not decision.get("trade_allowed"):
        return {
            "available": False,
            "ticker": ticker.upper(),
            "trade": "NO_TRADE",
            "side": "NONE",
            "best_strike": None,
            "score": 0,
            "reason": "Decision engine denied entry",
            "decision": decision,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    side = "P" if decision.get("execution") == "EXECUTE_SHORT" else "C"
    expiry = datetime.now(timezone.utc).strftime("%Y%m%d")

    spy = float(str(forecast.get("spy_price", 0)).replace(",", ""))
    wall_key = "put_wall" if side == "P" else "call_wall"
    target = float(str(forecast.get(wall_key, spy)).replace(",", ""))

    center = round(target)
    strikes = sorted(set([
        center - 5, center - 4, center - 3, center - 2, center - 1,
        center, center + 1, center + 2, center + 3, center + 4, center + 5,
        round(spy) - 3, round(spy) - 2, round(spy) - 1,
        round(spy), round(spy) + 1, round(spy) + 2, round(spy) + 3
    ]))

    option_chain = []
    checked_contracts = []

    for strike in strikes:
        cid = uw_option_contract_id(ticker, expiry, side, strike)
        checked_contracts.append(cid)

        row = fetch_contract(cid)
        if not row:
            continue

        option_chain.append({
            "right": side,
            "strike": row.get("strike", strike),
            "expiry": row.get("expiry", expiry),
            "delta": row.get("delta", 0),
            "iv": row.get("implied_volatility", 0),
            "open_interest": row.get("open_interest", 0),
            "volume": row.get("volume", 0),
            "bid": row.get("nbbo_bid") or row.get("ewma_nbbo_bid") or 0,
            "ask": row.get("nbbo_ask") or row.get("ewma_nbbo_ask") or 0,
            "contract_id": row.get("option_chain_id", cid),
        })

    source = "unusual_whales_live_flow"

    if not option_chain:
        return {
            "available": False,
            "ticker": ticker.upper(),
            "side": "PUT" if side == "P" else "CALL",
            "reason": "Live options chain unavailable; stale sample fallback disabled",
            "service": "execution_service",
            "source": "uw_empty_no_fallback",
            "contracts_scanned": 0,
            "contracts_checked": checked_contracts[:40],
            "updated_at_utc": datetime.now(timezone.utc).isoformat()
        }

    result = choose_best_0dte(option_chain, forecast, trade_bias)
    result["service"] = "execution_service"
    result["source"] = source
    result["contracts_scanned"] = len(option_chain)
    result["contracts_checked"] = checked_contracts[:40]
    result["updated_at_utc"] = forecast.get("updated_at_utc")
    return result


@app.get("/breadth/market")
def breadth_market():
    return market_breadth()


@app.get("/cross-asset")
def cross_asset():
    forecast = forecast_input()
    result = cross_asset_confirmation(forecast)
    return {
        "service": "execution_service",
        "module": "cross_asset_confirmation_v1",
        "cross_asset": result,
        "forecast": forecast
    }


@app.get("/news/impact")
def news_impact_endpoint():
    return news_impact()


@app.get("/treasury/yields")
def treasury_yields_endpoint():
    return treasury_yield_signal()


@app.get("/sector/rotation")
def sector_rotation_endpoint():
    return sector_rotation()


@app.get("/vix/term-structure")
def vix_term_structure_endpoint():
    return vix_term_structure()


@app.get("/credit/markets")
def credit_markets_endpoint():
    return credit_market_signal()





# ==============================
# Institutional Conviction Engine
# ==============================

def _ice_num(x, default=0.0):
    try:
        if x is None:
            return default
        if isinstance(x, str):
            x = x.replace("%", "").replace("B", "").replace("$", "").strip()
        return float(x)
    except Exception:
        return default

def _ice_fetch(path):
    import urllib.request, json
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8004{path}", timeout=6) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def _ice_bias_score(value):
    v = str(value or "").upper()
    if any(x in v for x in ["SHORT", "BEAR", "NEGATIVE", "RISK_OFF"]):
        return -100
    if any(x in v for x in ["LONG", "BULL", "POSITIVE", "RISK_ON"]):
        return 100
    return 0

def _ice_confidence_label(score):
    a = abs(score)
    if a >= 85:
        return "VERY_HIGH"
    if a >= 70:
        return "HIGH"
    if a >= 55:
        return "MEDIUM"
    if a >= 40:
        return "LOW"
    return "NO_TRADE"

def _ice_position_size(score):
    a = abs(score)
    if a >= 85:
        return "FULL"
    if a >= 70:
        return "THREE_QUARTER"
    if a >= 55:
        return "HALF"
    if a >= 40:
        return "QUARTER"
    return "NONE"

def _ice_entry_quality(score):
    a = abs(score)
    if a >= 85:
        return "A+"
    if a >= 70:
        return "A"
    if a >= 55:
        return "B"
    if a >= 40:
        return "C"
    return "WAIT"

def institutional_conviction_engine():
    forecast = _ice_fetch("/forecast/trade-bias")
    breadth = _ice_fetch("/breadth/market")
    cross_asset = _ice_fetch("/cross-asset")
    sector = _ice_fetch("/sector/rotation")
    treasury = _ice_fetch("/treasury/yields")

    # Fallback: /cross-asset already carries a usable forecast snapshot
    if forecast.get("error") and isinstance(cross_asset.get("forecast"), dict):
        forecast = cross_asset.get("forecast")

    tech = forecast.get("technical_confirmation", {}) or {}
    credit = forecast.get("credit_markets", {}) or forecast.get("credit_spreads", {}) or {}
    vix = forecast.get("vix_term_structure", {}) or {}
    news = forecast.get("news_impact", {}) or {}

    factors = []

    def add(name, weight, raw_score, source):
        raw_score = max(-100, min(100, _ice_num(raw_score)))
        factors.append({
            "factor": name,
            "weight": weight,
            "raw_score": round(raw_score, 2),
            "weighted_score": round(raw_score * weight, 2),
            "source": source
        })

    # 25% Institutional Forecast
    desk = forecast.get("desk_call") or forecast.get("bias") or forecast.get("institutional_bias")
    forecast_score = _ice_bias_score(desk)
    conf = _ice_num(forecast.get("adjusted_confidence", forecast.get("confidence", 50)), 50)
    forecast_score *= min(max(conf / 100, 0.25), 1.0)
    add("Institutional Forecast", 0.25, forecast_score, desk)

    # 15% Gamma
    gamma_source = forecast.get("gamma_regime") or forecast.get("gamma_bias")
    add("Gamma Regime", 0.15, _ice_bias_score(gamma_source), gamma_source)

    # 15% Options Flow
    flow_score = _ice_num(forecast.get("options_flow_score", forecast.get("flow_score", 0)), 0)
    flow_bias = forecast.get("options_flow_bias") or forecast.get("flow_bias")
    if flow_score == 0:
        flow_score = _ice_bias_score(flow_bias)
    add("Options Flow", 0.15, flow_score, flow_bias or "neutral/missing")

    # 10% Breadth
    breadth_score = _ice_num(
        breadth.get("breadth_score", breadth.get("score", breadth.get("market_breadth_score", 0))), 0
    )
    if breadth_score == 0:
        breadth_score = _ice_bias_score(breadth.get("signal") or breadth.get("bias"))
    add("Breadth", 0.10, breadth_score, breadth.get("signal") or breadth.get("bias"))

    # 10% Sector Rotation
    sector_score = _ice_num(sector.get("rotation_score", sector.get("score", 0)), 0)
    if sector_score == 0:
        sector_score = _ice_bias_score(sector.get("signal"))
    add("Sector Rotation", 0.10, sector_score, sector.get("signal"))

    # 10% Technical Confirmation
    tech_score = _ice_num(tech.get("technical_score", tech.get("score", 0)), 0)
    if tech_score == 0:
        tech_score = _ice_bias_score(tech.get("technical_bias") or tech.get("bot_permission"))
    add("Technical Confirmation", 0.10, tech_score, tech.get("technical_bias") or tech.get("bot_permission"))

    # 5% Treasury
    treasury_score = _ice_num(treasury.get("treasury_score", treasury.get("score", 0)), 0)
    if treasury_score == 0:
        treasury_score = _ice_bias_score(treasury.get("signal") or treasury.get("bias"))
    add("Treasury Model", 0.05, treasury_score, treasury.get("signal") or treasury.get("bias"))

    # 5% Credit
    credit_score = _ice_num(credit.get("score", credit.get("credit_score", 0)), 0)
    if credit_score == 0:
        credit_score = _ice_bias_score(credit.get("signal") or credit.get("bias"))
    add("Credit Spreads", 0.05, credit_score, credit.get("signal") or credit.get("bias"))

    # 5% VIX Term
    vix_score = _ice_num(vix.get("score", vix.get("vix_score", 0)), 0)
    if vix_score == 0:
        vix_score = _ice_bias_score(vix.get("signal") or vix.get("regime"))
    add("VIX Term Structure", 0.05, vix_score, vix.get("signal") or vix.get("regime"))

    # 5% News
    news_score = _ice_num(news.get("news_score", news.get("score", 0)), 0)
    if news_score == 0:
        news_score = _ice_bias_score(news.get("news_bias") or news.get("bias"))
    add("News Impact", 0.05, news_score, news.get("news_bias") or news.get("bias"))

    total = round(sum(f["weighted_score"] for f in factors), 2)
    conviction = round(abs(total), 2)

    if conviction < 40:
        direction = "WAIT"
    else:
        direction = "LONG" if total > 0 else "SHORT"

    return {
        "service": "institutional_conviction_engine",
        "institutional_conviction": conviction,
        "direction": direction,
        "confidence": _ice_confidence_label(total),
        "position_size": _ice_position_size(total),
        "expected_holding": "Intraday",
        "risk_multiplier": round(min(max(conviction / 85, 0.25), 1.25), 2) if direction != "WAIT" else 0,
        "entry_quality": _ice_entry_quality(total),
        "weighted_total": total,
        "trade_permission": "ALLOW_TRADE" if conviction >= 55 else "WAIT",
        "factors": factors,
        "raw_inputs": {
            "forecast": forecast,
            "breadth": breadth,
            "cross_asset": cross_asset,
            "sector": sector,
            "treasury": treasury
        }
    }

@app.get("/conviction/institutional")
def conviction_institutional():
    return institutional_conviction_engine()



from institutional_conviction_engine import institutional_conviction_v2

@app.get("/conviction/institutional-v2")
def conviction_institutional_v2():
    return institutional_conviction_v2()


from execution_intelligence_engine import execution_intelligence

@app.get("/execution/intelligence")
def execution_intelligence_endpoint():
    return execution_intelligence()


from execution_intelligence_engine import execution_intelligence_v2

@app.get("/execution/intelligence-v2")
def execution_intelligence_v2_endpoint():
    return execution_intelligence_v2()



try:
    app.mount("/dashboard", StaticFiles(directory="/app/static", html=True), name="dashboard")
except Exception:
    pass


@app.get("/paper/dashboard-summary")
def paper_dashboard_summary():
    import json
    from pathlib import Path
    from datetime import datetime, timezone

    journal = Path("/logs/paper_trade_journal.jsonl")
    state_path = Path("/state/paper_execution_state.json")
    today = datetime.now(timezone.utc).date().isoformat()

    events = []
    if journal.exists():
        for line in journal.read_text().splitlines():
            try:
                e = json.loads(line)
                if str(e.get("ts_utc", "")).startswith(today):
                    events.append(e)
            except Exception:
                pass

    open_position = None
    if state_path.exists():
        try:
            open_position = json.loads(state_path.read_text()).get("open_position")
        except Exception:
            pass

    return {
        "date_utc": today,
        "gate_checks": len([e for e in events if e.get("event") == "GATE_CHECK"]),
        "setup_developing": len([e for e in events if e.get("event") == "SETUP_DEVELOPING"]),
        "paper_entries": len([e for e in events if e.get("event") == "PAPER_ENTRY"]),
        "paper_exits": len([e for e in events if e.get("event") == "PAPER_EXIT"]),
        "ready_count": len([e for e in events if e.get("event") == "GATE_CHECK" and e.get("decision") == "READY_FOR_PAPER_EXECUTION"]),
        "errors": len([e for e in events if e.get("event") == "GATE_ERROR"]),
        "development_ratio": round((len([e for e in events if e.get("event") == "SETUP_DEVELOPING"]) / max(len([e for e in events if e.get("event") == "GATE_CHECK"]), 1)) * 100, 2),
        "readiness_ratio": round((len([e for e in events if e.get("event") == "GATE_CHECK" and e.get("decision") == "READY_FOR_PAPER_EXECUTION"]) / max(len([e for e in events if e.get("event") == "GATE_CHECK"]), 1)) * 100, 2),
        "recent_events": events[-25:],
        "open_position": open_position
    }


@app.get("/dashboard/chart-snapshot")
def dashboard_chart_snapshot():
    from datetime import datetime, timezone

    try:
        forecast = forecast_input()
    except Exception:
        forecast = {}

    try:
        tech = technical_confirmation()
    except Exception:
        tech = {}

    def fnum(v, default=None):
        try:
            if v is None:
                return default
            return float(str(v).replace(",", "").replace("B", "").replace("$", ""))
        except Exception:
            return default

    price = fnum(tech.get("last_price"), fnum(forecast.get("spy_price"), 0))
    ema20 = fnum(tech.get("ema20"))
    ema50 = fnum(tech.get("ema50"))
    call_wall = fnum(forecast.get("call_wall"))
    put_wall = fnum(forecast.get("put_wall"))
    gamma_flip = fnum(forecast.get("gamma_flip"))

    # lightweight synthetic line until true intraday candles are wired
    points = []
    base = price or 0
    for i in range(30):
        drift = (i - 15) * 0.015
        wave = ((i % 6) - 3) * 0.035
        points.append({
            "t": i,
            "price": round(base + drift + wave, 2),
            "ema20": ema20,
            "ema50": ema50,
            "vwap": round(base - 0.08, 2) if base else None
        })

    return {
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "ticker": "SPY",
        "price": price,
        "ema20": ema20,
        "ema50": ema50,
        "vwap": round(price - 0.08, 2) if price else None,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "gamma_flip": gamma_flip,
        "points": points
    }


@app.get("/execution/router-gate")
def execution_router_gate():
    try:
        intel = execution_intelligence_v2()
    except Exception as e:
        return {
            "service": "execution_service",
            "status": "ERROR",
            "decision": "BLOCKED_BY_ROUTER_ERROR",
            "error": str(e),
        }

    setup = intel.get("setup", {}) or intel.get("execution_setup", {}) or {}
    risk = intel.get("risk", {}) or {}

    direction = setup.get("direction", intel.get("direction", "WAIT"))
    conviction = setup.get("conviction", intel.get("conviction", 0))
    missing = setup.get("missing", intel.get("missing", []))

    blocked = (
        risk.get("status") == "BLOCKED"
        or intel.get("decision") in ["BLOCKED_BY_RISK", "WAIT_FOR_EXECUTION_SETUP"]
        or bool(missing)
    )

    return {
        "service": "execution_service",
        "endpoint": "/execution/router-gate",
        "status": "BLOCKED" if blocked else "READY",
        "decision": "BLOCKED_BY_RISK" if blocked else "ALLOW_PAPER_EXECUTION",
        "direction": direction,
        "conviction": conviction,
        "missing": missing,
        "source": "execution_intelligence_v2",
    }


@app.get("/decision/current")
def decision_current(ticker: str = "SPY"):
    try:
        forecast = forecast_input()
    except Exception:
        forecast = {}

    try:
        trade = forecast_trade_bias()
    except Exception:
        trade = {}

    try:
        tech = technical_confirmation(ticker=ticker.upper(), interval="5m")
    except Exception:
        tech = trade.get("technical_confirmation", {}) or {}

    return build_decision(forecast, trade, tech)
