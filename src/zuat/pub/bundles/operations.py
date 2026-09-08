"""Public one-pass bundle operations under the compiler store's writer lock."""

from zuat.gitcore import OperationKind, OperationOutcome
from zuat.pub.bundles.models import (
    BundleError,
    BundleOperationResult,
    BundleOutputError,
)
from zuat.pub.bundles.targets import TargetAttempt, observe
from zuat.specs.interface import ResolutionError


def _journal(service, bundle_id, targets, operation, *, force=False):
    """Append domain reference metadata, never compiler paths or source bodies."""
    with service.registry.operation():
        for target in targets:
            service.registry.append_event(
                OperationKind.UNINSTALL
                if operation == "remove"
                else OperationKind.UPDATE,
                OperationOutcome.SUCCESS
                if target.status in {"success", "current", "absent"}
                else OperationOutcome.INDETERMINATE,
                forced=force,
                metadata={
                    "state_kind": "plugin-lifecycle",
                    "bundle_id": bundle_id,
                    "build_revision": target.build_revision,
                    "plugin_agent": target.agent,
                },
            )


def _agents(agents, default):
    selected = tuple(
        default if agents is None else (agents,) if isinstance(agents, str) else agents
    )
    if (
        not selected
        or len(set(selected)) != len(selected)
        or set(selected) - {"codex", "claude", "pi", "kimi"}
    ):
        raise BundleError("select distinct supported agent kinds")
    return selected


def bootstrap(
    service, bundle_id, *, build_revision=None, agents=None, trust=False, force=False
):
    store = service._bundles
    with store.locked():
        record = store.get(bundle_id)
        state = store.read()
        selected = (
            next((b for b in record.builds if b.build_revision == build_revision), None)
            if build_revision
            else (record.builds[-1] if record.builds else None)
        )
        if selected is None:
            raise BundleOutputError("selected build is unavailable")
        targets = _agents(agents, selected.agents)
        if agents is None:
            available = []
            for agent in targets:
                resolver = service._resolver(agent)
                adapter = resolver.bundle_adapter()
                if adapter is None:
                    continue
                try:
                    native = resolver.plugin_adapter()
                    adapter.initialize(native)
                    observe(native, adapter.reference(record))
                    available.append(agent)
                except (OSError, ValueError, ResolutionError):
                    # Availability probing must not persist native stderr or
                    # turn one missing optional manager into a global failure.
                    pass
            # When none can be reached, retain explicit non-success outcomes
            # instead of reporting that an empty target set was installed.
            targets = tuple(available) or targets
        results = tuple(
            TargetAttempt(service, state, record, agent, selected).bootstrap(
                trust=trust, force=force
            )
            for agent in targets
        )
        _journal(service, bundle_id, results, "bootstrap", force=force)
        return BundleOperationResult(bundle_id, "bootstrap", results)


def remove(service, bundle_id, *, agents=None, purge=False):
    if purge and agents is not None:
        raise BundleError(
            "purge requires removal of all registered targets; omit agents"
        )
    store = service._bundles
    with store.locked():
        record = store.get(bundle_id)
        state = store.read()
        selected = (
            _agents(agents, tuple(t.agent for t in record.targets))
            if agents is not None or record.targets
            else ()
        )
        results = tuple(
            TargetAttempt(service, state, record, agent).remove()
            for agent in selected
            if any(t.agent == agent for t in record.targets)
        )
        outputs_removed = False
        if all(t["status"] == "absent" for t in state["bundles"][bundle_id]["targets"]):
            if purge:
                from zuat.pub.bundles.cleanup import purge as purge_outputs

                purge_outputs(service, record)
                outputs_removed = True
            del state["bundles"][bundle_id]
            store.write(state)
        _journal(service, bundle_id, results, "remove")
        return BundleOperationResult(bundle_id, "remove", results, outputs_removed)
