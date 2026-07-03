def permission():
    import main
    return main.execution_permission()


def paper_order(req):
    import main
    return main.paper_order(req)


def pretrade_order(req):
    import main
    return main.pretrade_order(req)


def route_order(req):
    import main
    return main.route_order(req)


def audit_orders():
    import main
    return main.audit_orders()


def intelligence():
    import main
    return main.execution_intelligence_endpoint()


def intelligence_v2():
    import main
    return main.execution_intelligence_v2_endpoint()
