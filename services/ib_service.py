def status():
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
