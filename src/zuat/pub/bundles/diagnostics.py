"""Read-only health checks, deliberately separate from lifecycle attempts."""

from zuat.pub.bundles.models import BundleCheck, BundleDiagnostics, BundleOutputError
from zuat.pub.bundles.operations import _agents
from zuat.specs.interface import ResolutionError
from zuat.specs.native import PluginOperationError, UnsupportedNativeOperation


def _manager(service, agent):
    """Probe only discovery: initialization/preparation may create native files."""
    try:
        resolver = service._resolver(agent)
        if resolver.bundle_adapter() is None:
            raise UnsupportedNativeOperation("bundle bootstrap unsupported")
        native = resolver.plugin_adapter()
        native.discover()
        if native.discovery_diagnostics:
            return BundleCheck(
                "manager", agent, "indeterminate", reason="native-inventory-incomplete"
            )
        return BundleCheck("manager", agent, "ok")
    except UnsupportedNativeOperation:
        return BundleCheck(
            "manager", agent, "unsupported", reason="bundle-bootstrap-unsupported"
        )
    except (FileNotFoundError, PluginOperationError):
        return BundleCheck(
            "manager", agent, "unavailable", reason="native-manager-unavailable"
        )
    except (OSError, ValueError, TypeError, KeyError, ResolutionError):
        # Never expose raw native output or attempt recovery from a health check.
        return BundleCheck(
            "manager", agent, "indeterminate", reason="native-inventory-incomplete"
        )


def doctor(service, bundle_id, *, agents=None):
    """Inspect selected retained outputs and managers, not desired-state convergence.

    No writer lock is taken: that lock creates storage. Concurrent changes may
    make a check unavailable; callers can explicitly repeat this point-in-time
    observation. Corrupt indexes and unknown handles remain typed failures.
    """
    record = service.get_bundle(bundle_id)
    selected = _agents(
        agents, tuple(dict.fromkeys(a for b in record.builds for a in b.agents))
    )
    checks = []
    for build in record.builds:
        for agent in selected:
            if agent not in build.agents:
                continue
            try:
                service.resolve_bundle(
                    bundle_id, build_revision=build.build_revision, agent=agent
                )
                check = BundleCheck("output", agent, "ok", build.build_revision)
            except BundleOutputError:
                check = BundleCheck(
                    "output",
                    agent,
                    "unavailable",
                    build.build_revision,
                    "build-output-unavailable",
                )
            checks.append(check)
    checks.extend(_manager(service, agent) for agent in selected)
    return BundleDiagnostics(bundle_id, tuple(checks))
