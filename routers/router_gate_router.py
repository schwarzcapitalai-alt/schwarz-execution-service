from fastapi import APIRouter

router = APIRouter()


@router.get("/execution/router-gate")
def execution_router_gate():
    try:
        from main import execution_intelligence_v2
        intel = execution_intelligence_v2()
    except Exception as e:
        return {
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
