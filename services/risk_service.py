def limits():
    import main
    return main.load_risk_limits()


def runtime():
    import main
    return main.risk_runtime()


def kill_switch():
    import main
    return main.risk_kill_switch()


def permission_risk_limits():
    import main
    return main.permission_risk_limits()


def permission_runtime_counters():
    import main
    return main.permission_runtime_counters()
