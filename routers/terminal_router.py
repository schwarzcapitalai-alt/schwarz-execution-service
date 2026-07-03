from fastapi import APIRouter
from datetime import datetime, timezone
import requests

router = APIRouter()
BASE = "http://127.0.0.1:8004"


def safe_get(path, fallback):
    try:
        r = requests.get(BASE + path, timeout=3)
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}", "fallback": fallback}
    except Exception as e:
        return {"error": str(e), "fallback": fallback}


@router.get("/terminal/state")
def terminal_state():
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "ibkr": safe_get("/ibkr/shared/status", {}),
        "mode": safe_get("/system/mode", {}),
        "account": safe_get("/account/snapshot", {}),
        "decision": safe_get("/decision/current", {}),
        "risk": safe_get("/risk/status", {}),
        "orders": safe_get("/ibkr/shared/open-orders", {}),
        "positions": safe_get("/ibkr/shared/positions", {}),
        "health": safe_get("/health", {}),
    }
