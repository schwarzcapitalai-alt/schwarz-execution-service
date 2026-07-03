from fastapi import APIRouter
import json
import os

router = APIRouter()

EXECUTION_MODE = os.getenv("EXECUTION_MODE", "READ_ONLY")


@router.get("/system/mode")
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
        execution_mode == "LIVE"
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
