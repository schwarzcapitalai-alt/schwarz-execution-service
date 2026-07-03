from fastapi import APIRouter
import json
import os
from datetime import datetime

router = APIRouter()

EXECUTION_MODE = os.getenv("EXECUTION_MODE", "READ_ONLY")
RISK_CONFIG_PATH = os.getenv("RISK_CONFIG_PATH", "/config/risk.json")
KILL_SWITCH_ENABLED = os.getenv("KILL_SWITCH_ENABLED", "true").lower() in ("1", "true", "yes", "on")
KILL_SWITCH_REASON = os.getenv("KILL_SWITCH_REASON", "GLOBAL_TRADING_DISABLED_BY_DEFAULT")


ORDER_RATE_STATE = {
    "date": datetime.utcnow().date().isoformat(),
    "paper_orders_today": 0,
    "minute": 0,
    "orders_this_minute": 0,
}


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
            "live_trading_requires_manual_approval": bool(data.get("live_trading_requires_manual_approval", True)),
        }

    except Exception as e:
        return {
            "max_notional_usd": 0,
            "max_quantity": 0,
            "allowed_symbols": [],
            "blocked_sides": ["BUY", "SELL"],
            "allowed_accounts": [],
            "execution": f"RISK_CONFIG_LOAD_FAILED: {e}",
        }


RISK_LIMITS = load_risk_limits()


def order_rate_state():
    return ORDER_RATE_STATE


@router.get("/risk/limits")
def risk_limits():
    return {
        "mode": EXECUTION_MODE,
        "limits": RISK_LIMITS,
        "execution": "DISABLED_READ_ONLY_NO_ORDER_ROUTE",
    }


@router.get("/risk/kill-switch")
def risk_kill_switch():
    return {
        "mode": EXECUTION_MODE,
        "kill_switch_enabled": KILL_SWITCH_ENABLED,
        "reason": KILL_SWITCH_REASON,
        "execution": "GLOBAL_EXECUTION_BLOCK_ACTIVE" if KILL_SWITCH_ENABLED else "GLOBAL_EXECUTION_BLOCK_INACTIVE",
    }


@router.get("/config/risk")
def config_risk():
    return {
        "mode": EXECUTION_MODE,
        "risk_config_path": RISK_CONFIG_PATH,
        "limits": load_risk_limits(),
    }


@router.get("/risk/runtime")
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
                else max(0, int(limits.get("max_trades_per_day")) - int(st.get("paper_orders_today", 0)))
            ),
            "orders_this_minute": (
                None if not limits.get("max_orders_per_minute")
                else max(0, int(limits.get("max_orders_per_minute")) - int(st.get("orders_this_minute", 0)))
            ),
        },
        "live_ordering_possible": False,
        "execution": "RUNTIME_RISK_STATUS_ONLY",
    }
