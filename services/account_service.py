import time


def ib_status():
    import main
    app_ib = main.connect_ib()
    result = {
        "connected": app_ib.connected_flag,
        "api_ready": app_ib.connected_flag,
        "host": main.IB_HOST,
        "port": main.IB_PORT,
        "mode": main.EXECUTION_MODE,
    }
    app_ib.disconnect()
    return result


def account_cash():
    import main
    app_ib = main.connect_ib()

    if not app_ib.connected_flag:
        return {"connected": False, "mode": main.EXECUTION_MODE, "cash": []}

    tags = "NetLiquidation,TotalCashValue,AvailableFunds,BuyingPower,ExcessLiquidity"
    app_ib.reqAccountSummary(9001, "All", tags)

    deadline = time.time() + 8
    while time.time() < deadline:
        if app_ib.account_summary_done:
            break
        time.sleep(0.1)

    app_ib.cancelAccountSummary(9001)

    result = {
        "connected": app_ib.connected_flag,
        "mode": main.EXECUTION_MODE,
        "cash": main.dedupe_rows(app_ib.account_summary_rows),
    }

    app_ib.disconnect()
    return result


def account_positions():
    import main
    app_ib = main.connect_ib()

    if not app_ib.connected_flag:
        return {"connected": False, "mode": main.EXECUTION_MODE, "positions": []}

    app_ib.reqPositions()

    deadline = time.time() + 8
    while time.time() < deadline:
        if app_ib.position_done:
            break
        time.sleep(0.1)

    app_ib.cancelPositions()

    result = {
        "connected": app_ib.connected_flag,
        "mode": main.EXECUTION_MODE,
        "positions": app_ib.position_rows,
    }

    app_ib.disconnect()
    return result


def account_snapshot():
    import main
    cash_data = account_cash()
    positions_data = account_positions()

    return {
        "connected": bool(cash_data.get("connected")),
        "mode": main.EXECUTION_MODE,
        "cash": main.dedupe_rows(cash_data.get("cash", [])),
        "positions": positions_data.get("positions", []),
    }


def account_summary():
    import main

    if not main.app_ib.connected_flag:
        return {"connected": False, "summary": []}

    try:
        rows = main.app_ib.ib.accountSummary()
        summary = []

        for r in rows:
            summary.append({
                "account": getattr(r, "account", None),
                "tag": getattr(r, "tag", None),
                "value": getattr(r, "value", None),
                "currency": getattr(r, "currency", None),
            })

        return {"connected": True, "summary": summary}

    except Exception as e:
        return {"connected": False, "error": str(e), "summary": []}
