import json
import urllib.request
from institutional_conviction_engine import institutional_conviction_v2

def fetch(path, timeout=6):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:8004{path}", timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

def upper(x):
    return str(x or "").upper()

def aligned_for_direction(direction, value):
    v = upper(value)
    d = upper(direction)

    if d == "LONG":
        return any(x in v for x in ["LONG", "BULL", "BUY", "POSITIVE", "RISK_ON", "CALL"])
    if d == "SHORT":
        return any(x in v for x in ["SHORT", "BEAR", "SELL", "NEGATIVE", "RISK_OFF", "PUT", "DEFENSIVE"])
    return False

def execution_intelligence():
    conviction = institutional_conviction_v2()
    forecast = fetch("/forecast/trade-bias")
    import os
    risk = {
        "kill_switch_enabled": os.getenv("KILL_SWITCH_ENABLED", "true").lower() == "true",
        "execution_mode": os.getenv("EXECUTION_MODE", "UNKNOWN"),
        "execution": "SAFE_OBSERVATION_ONLY" if os.getenv("KILL_SWITCH_ENABLED", "true").lower() == "true" else "PAPER_ALLOWED"
    }

    direction = conviction.get("direction", "WAIT")
    score = float(conviction.get("institutional_conviction", 0) or 0)

    tech = forecast.get("technical_confirmation", {}) or {}
    dealer_flow = forecast.get("dealer_flow")
    flow_bias = forecast.get("flow_bias")
    gamma_regime = forecast.get("gamma_regime")
    vol_regime = forecast.get("vol_regime")

    checks = []
    missing = []

    def add_check(name, passed, detail):
        checks.append({
            "check": name,
            "passed": bool(passed),
            "detail": detail
        })
        if not passed:
            missing.append(name)

    add_check(
        "conviction_threshold",
        score >= 55 and direction != "WAIT",
        f"score={score}, direction={direction}, required>=55"
    )

    add_check(
        "technical_confirmation",
        aligned_for_direction(direction, tech.get("technical_bias") or tech.get("bot_permission")),
        tech
    )

    add_check(
        "dealer_flow_confirmation",
        aligned_for_direction(direction, dealer_flow) or aligned_for_direction(direction, flow_bias),
        {"dealer_flow": dealer_flow, "flow_bias": flow_bias}
    )

    add_check(
        "gamma_context",
        aligned_for_direction(direction, gamma_regime),
        gamma_regime
    )

    add_check(
        "risk_layer_available",
        not bool(risk.get("error")),
        risk
    )

    hard_block = False
    if upper(risk.get("kill_switch_enabled")) == "TRUE":
        hard_block = True
    if upper(risk.get("execution")) in ["BLOCKED", "LIVE_ORDERING_BLOCKED", "SAFE_OBSERVATION_ONLY"]:
        hard_block = True

    paper_sim_allowed = os.getenv("PAPER_SIMULATION_ALLOWED", "false").lower() == "true"

    if hard_block and paper_sim_allowed and os.getenv("EXECUTION_MODE", "").upper() == "PAPER_ONLY":
        decision = "WAIT_FOR_CONFIRMATION"
        entry_status = "NOT_READY"
    elif hard_block:
        decision = "BLOCKED_BY_RISK"
        entry_status = "BLOCKED"
    elif score < 55 or direction == "WAIT":
        decision = "WAIT_FOR_CONVICTION"
        entry_status = "NOT_READY"
    elif missing:
        decision = "WAIT_FOR_CONFIRMATION"
        entry_status = "NOT_READY"
    else:
        decision = "READY_FOR_PAPER_TRADE"
        entry_status = "READY"

    return {
        "service": "execution_intelligence_v1",
        "execution_decision": decision,
        "entry_status": entry_status,
        "direction": direction,
        "conviction": score,
        "position_size": conviction.get("position_size"),
        "risk_multiplier": conviction.get("risk_multiplier"),
        "entry_quality": conviction.get("entry_quality"),
        "missing_confirmations": missing,
        "checks": checks,
        "context": {
            "gamma_regime": gamma_regime,
            "vol_regime": vol_regime,
            "dealer_flow": dealer_flow,
            "flow_bias": flow_bias,
            "technical_confirmation": tech
        }
    }


def execution_intelligence_v2():
    import os, json, time
    from pathlib import Path

    state_path = Path("/config/execution_intelligence_state.json")

    now = int(time.time())
    current = execution_intelligence()

    conviction = float(current.get("conviction", 0) or 0)
    direction = current.get("direction", "WAIT")
    entry_status = current.get("entry_status")
    decision = current.get("execution_decision")
    ctx = current.get("context", {}) or {}
    tech = ctx.get("technical_confirmation", {}) or {}

    price = float(tech.get("last_price", 0) or 0)
    ema20 = float(tech.get("ema20", 0) or 0)
    ema50 = float(tech.get("ema50", 0) or 0)
    macd_state = str(tech.get("macd_state", "")).upper()
    histogram_state = str(tech.get("histogram_state", "")).upper()
    momentum_state = str(tech.get("momentum_state", "")).upper()

    previous = {}
    try:
        if state_path.exists():
            previous = json.loads(state_path.read_text())
    except Exception:
        previous = {}

    prev_conviction = float(previous.get("conviction", conviction) or conviction)
    prev_price = float(previous.get("price", price) or price)

    conviction_delta = round(conviction - prev_conviction, 2)
    price_delta = round(price - prev_price, 2)

    liquidity_sweep = False
    break_reject = False
    break_reclaim = False
    momentum_confirmed = False

    if direction == "SHORT":
        liquidity_sweep = price > ema20 and price_delta > 0 and macd_state == "BEARISH"
        break_reject = price < ema20 and macd_state == "BEARISH"
        momentum_confirmed = macd_state == "BEARISH" and histogram_state in ["FALLING", "BEARISH"]
    elif direction == "LONG":
        liquidity_sweep = price < ema20 and price_delta < 0 and macd_state == "BULLISH"
        break_reclaim = price > ema20 and macd_state == "BULLISH"
        momentum_confirmed = macd_state == "BULLISH" and histogram_state in ["RISING", "BULLISH"]

    improving = conviction_delta > 0
    fading = conviction_delta < -3

    v2_checks = [
        {"check": "conviction_improving", "passed": improving, "detail": {"delta": conviction_delta}},
        {"check": "liquidity_sweep_detected", "passed": liquidity_sweep, "detail": {"price": price, "ema20": ema20, "price_delta": price_delta}},
        {"check": "break_reject_or_reclaim", "passed": break_reject or break_reclaim, "detail": {"break_reject": break_reject, "break_reclaim": break_reclaim}},
        {"check": "momentum_confirmed", "passed": momentum_confirmed, "detail": {"macd_state": macd_state, "histogram_state": histogram_state, "momentum_state": momentum_state}},
        {"check": "not_fading", "passed": not fading, "detail": {"conviction_delta": conviction_delta}}
    ]

    v2_missing = [c["check"] for c in v2_checks if not c["passed"]]

    if decision == "BLOCKED_BY_RISK":
        v2_decision = "BLOCKED_BY_RISK"
        v2_status = "BLOCKED"
    elif decision in ["WAIT_FOR_CONVICTION", "WAIT_FOR_CONFIRMATION"]:
        if v2_missing:
            v2_decision = "WAIT_FOR_EXECUTION_SETUP"
            v2_status = "NOT_READY"
        else:
            v2_decision = "READY_FOR_PAPER_EXECUTION"
            v2_status = "READY"
    elif decision in ["WAIT_FOR_CONVICTION", "WAIT_FOR_CONFIRMATION"]:
        if v2_missing:
            v2_decision = "WAIT_FOR_EXECUTION_SETUP"
            v2_status = "NOT_READY"
        else:
            v2_decision = "READY_FOR_PAPER_EXECUTION"
            v2_status = "READY"
    elif entry_status != "READY":
        v2_decision = "WAIT_FOR_BASE_GATE"
        v2_status = "NOT_READY"
    elif v2_missing:
        v2_decision = "WAIT_FOR_EXECUTION_SETUP"
        v2_status = "NOT_READY"
    else:
        v2_decision = "READY_FOR_PAPER_EXECUTION"
        v2_status = "READY"

    new_state = {
        "updated_at_epoch": now,
        "direction": direction,
        "conviction": conviction,
        "price": price,
        "decision": decision,
        "entry_status": entry_status
    }

    try:
        state_path.write_text(json.dumps(new_state, indent=2) + "\n")
    except Exception:
        pass

    return {
        "service": "execution_intelligence_v2",
        "execution_decision": v2_decision,
        "entry_status": v2_status,
        "direction": direction,
        "conviction": conviction,
        "conviction_delta": conviction_delta,
        "price": price,
        "price_delta": price_delta,
        "base_gate": current,
        "v2_missing_confirmations": v2_missing,
        "v2_checks": v2_checks,
        "setup_detection": {
            "liquidity_sweep": liquidity_sweep,
            "break_reject": break_reject,
            "break_reclaim": break_reclaim,
            "momentum_confirmed": momentum_confirmed,
            "improving": improving,
            "fading": fading
        }
    }
