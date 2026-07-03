from fastapi import APIRouter
import json
import os
from pathlib import Path

router = APIRouter()

STATE_PATH = Path("/logs/autonomous_paper_trader.json")
EVENT_LOG_PATH = Path("/logs/autonomous_paper_trades.jsonl")
TRADE_LOG_PATH = Path("/logs/autonomous_paper_trade_lifecycle.jsonl")


def read_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def tail_jsonl(path, limit=1):
    try:
        lines = path.read_text().splitlines()[-limit:]
        rows = []
        for line in lines:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
        return rows
    except Exception:
        return []


@router.get("/autonomous/paper/status")
def autonomous_paper_status():
    state = read_json(STATE_PATH, {})
    recent_events = tail_jsonl(EVENT_LOG_PATH, 5)
    recent_lifecycle = tail_jsonl(TRADE_LOG_PATH, 5)

    last_event = recent_events[-1] if recent_events else {}
    open_position = state.get("open_position")

    return {
        "service": "execution_service",
        "component": "autonomous_paper_trader",
        "enabled": True,
        "mode": "PAPER_ONLY",
        "state_path": str(STATE_PATH),
        "event_log_path": str(EVENT_LOG_PATH),
        "trade_log_path": str(TRADE_LOG_PATH),
        "last_run_utc": last_event.get("timestamp_utc"),
        "last_decision": last_event.get("decision"),
        "last_reason": last_event.get("reason") or last_event.get("decision_reason"),
        "open_position": open_position,
        "last_closed_trade": state.get("last_closed_trade"),
        "recent_events": recent_events,
        "recent_lifecycle": recent_lifecycle,
    }
