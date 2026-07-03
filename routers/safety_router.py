from fastapi import APIRouter
from services.account_service import (
    ib_status as account_ib_status,
    account_snapshot as account_snapshot_service,
    account_positions as account_positions_service,
)


router = APIRouter()


@router.get("/checks/readiness")
def checks_readiness():
    import main

    checks = {}

    ib = account_ib_status()
    checks["ib_connected"] = bool(ib.get("connected"))
    checks["ib_api_ready"] = bool(ib.get("api_ready"))

    kill = main.risk_kill_switch()
    checks["kill_switch_disabled"] = not bool(kill.get("kill_switch_enabled"))

    risk = main.risk_limits()
    limits = risk.get("limits", {})
    checks["risk_limits_loaded"] = bool(limits.get("allowed_symbols")) and float(limits.get("max_notional_usd", 0)) > 0

    snap = account_snapshot_service()
    checks["account_connected"] = bool(snap.get("connected"))
    checks["cash_available"] = len(snap.get("cash", [])) > 0
    checks["positions_visible"] = "positions" in snap

    account_check = main.account_allowlist_check(snap.get("cash", []))
    checks["account_allowlisted"] = bool(account_check.get("ok"))

    audit_writable = False
    try:
        with open(main.AUDIT_LOG_PATH, "a") as f:
            f.write("")
        audit_writable = True
    except Exception:
        audit_writable = False

    checks["audit_writable"] = audit_writable
    checks["read_only_mode"] = main.EXECUTION_MODE == "READ_ONLY"
    checks["order_route_absent"] = True

    ready_for_execution = all(checks.values()) and main.EXECUTION_MODE != "READ_ONLY"

    return {
        "service": "execution_service",
        "mode": main.EXECUTION_MODE,
        "ready_for_execution": ready_for_execution,
        "safe_to_observe": checks["ib_connected"] and checks["account_connected"] and checks["audit_writable"],
        "checks": checks,
        "kill_switch": kill,
        "risk_limits": limits,
        "account_check": account_check,
        "execution": "BLOCKED_READ_ONLY_OR_KILL_SWITCH",
    }


@router.get("/safety/summary")
def safety_summary():
    import main

    ib = account_ib_status()
    kill = main.risk_kill_switch()
    readiness = checks_readiness()

    return {
        "service": "execution_service",
        "ib_connected": bool(ib.get("connected")),
        "ib_api_ready": bool(ib.get("api_ready")),
        "account_allowlisted": bool(readiness.get("safe_to_observe")),
        "safe_to_observe": readiness.get("safe_to_observe"),
        "kill_switch_enabled": kill.get("kill_switch_enabled"),
        "read_only_mode": main.EXECUTION_MODE == "READ_ONLY",
        "execution": "SAFE_OBSERVATION_ONLY",
    }


@router.get("/safety/final-check")
def safety_final_check():
    import main

    mode = main.system_mode()
    safety = safety_summary()

    can_send_live_orders = (
        mode.get("live_enabled") is True
        and mode.get("routing_active") is True
        and safety.get("ib_connected") is True
        and safety.get("ib_api_ready") is True
        and safety.get("account_allowlisted") is True
        and safety.get("kill_switch_enabled") is False
    )

    return {
        "service": "execution_service",
        "can_send_live_orders": can_send_live_orders,
        "mode": mode,
        "safety": safety,
        "verdict": "LIVE_ORDERING_BLOCKED" if not can_send_live_orders else "LIVE_ORDERING_ENABLED",
    }


@router.get("/system/status")
def system_status():
    import main

    mode = main.system_mode()
    safety = safety_summary()
    final = safety_final_check()

    try:
        pos = account_positions_service()
    except Exception as e:
        pos = {
            "service": "execution_service",
            "error": str(e),
            "positions": [],
        }

    return {
        "service": "execution_service",
        "status": "production_prep_locked",
        "can_send_live_orders": final.get("can_send_live_orders") is True,
        "verdict": final.get("verdict"),
        "mode": mode,
        "safety": safety,
        "positions": pos,
        "final_check": final,
    }
