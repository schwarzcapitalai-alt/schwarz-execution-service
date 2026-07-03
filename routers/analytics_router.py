from fastapi import APIRouter
from pathlib import Path
import json

router = APIRouter()

EVENT_LOG = Path("/logs/autonomous_paper_trades.jsonl")
LIFECYCLE_LOG = Path("/logs/autonomous_paper_trade_lifecycle.jsonl")


def read_jsonl(path, limit=500):
    rows = []
    try:
        for line in path.read_text().splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    except Exception:
        pass
    return rows


@router.get("/analytics/paper/summary")
def paper_analytics_summary(limit: int = 500):
    events = read_jsonl(EVENT_LOG, limit)
    lifecycle = read_jsonl(LIFECYCLE_LOG, limit)

    decisions = {}
    reasons = {}

    for e in events:
        d = e.get("decision", "UNKNOWN")
        r = e.get("reason") or e.get("decision_reason") or "UNKNOWN"
        decisions[d] = decisions.get(d, 0) + 1
        reasons[r] = reasons.get(r, 0) + 1

    closed = [
        x for x in lifecycle
        if x.get("event") in ["POSITION_CLOSED", "TRADE_CLOSED", "EXIT"]
    ]

    realized = []
    for x in closed:
        for key in ["realized_pnl", "pnl", "profit_loss"]:
            if key in x:
                try:
                    realized.append(float(x[key]))
                except Exception:
                    pass
                break

    wins = len([x for x in realized if x > 0])
    losses = len([x for x in realized if x < 0])

    return {
        "service": "execution_service",
        "component": "paper_trade_analytics",
        "events_count": len(events),
        "lifecycle_count": len(lifecycle),
        "decisions": decisions,
        "reasons": reasons,
        "closed_trades": len(closed),
        "realized_pnl_total": round(sum(realized), 2),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(realized), 4) if realized else None,
        "recent_events": events[-10:],
        "recent_lifecycle": lifecycle[-10:],
    }
