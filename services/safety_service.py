def readiness():
    import main
    return main.checks_readiness()


def summary():
    import main
    return main.safety_summary()


def final_check():
    import main
    return main.safety_final_check()


def system_status():
    import main
    return main.system_status()
