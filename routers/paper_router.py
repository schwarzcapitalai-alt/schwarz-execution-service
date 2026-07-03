from fastapi import APIRouter
import json
from pathlib import Path
from datetime import datetime, timezone

router = APIRouter()


@router.get("/paper/dashboard-summary")
def paper_dashboard_summary():
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

    gate_checks = len([e for e in events if e.get("event") == "GATE_CHECK"])
    setup_developing = len([e for e in events if e.get("event") == "SETUP_DEVELOPING"])
    ready_count = len([
        e for e in events
        if e.get("event") == "GATE_CHECK"
        and e.get("decision") == "READY_FOR_PAPER_EXECUTION"
    ])

    return {
        "date_utc": today,
        "gate_checks": gate_checks,
        "setup_developing": setup_developing,
        "paper_entries": len([e for e in events if e.get("event") == "PAPER_ENTRY"]),
        "paper_exits": len([e for e in events if e.get("event") == "PAPER_EXIT"]),
        "ready_count": ready_count,
        "errors": len([e for e in events if e.get("event") == "GATE_ERROR"]),
        "development_ratio": round((setup_developing / max(gate_checks, 1)) * 100, 2),
        "readiness_ratio": round((ready_count / max(gate_checks, 1)) * 100, 2),
        "recent_events": events[-25:],
        "open_position": open_position,
    }
