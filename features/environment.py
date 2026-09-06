def after_scenario(context, scenario):
    service = getattr(context, "service", None)
    if service is not None:
        service.close()
    registry = getattr(context, "registry", None)
    if registry is not None:
        registry.close()
    temporary = getattr(context, "temporary", None)
    if temporary is not None:
        temporary.cleanup()
