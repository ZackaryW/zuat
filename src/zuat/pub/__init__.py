"""Supported public Python interface used by callers and the optional CLI."""

from __future__ import annotations

from pathlib import Path

from zuat.gitcore.models import (
    AssetEvidence,
    AssetRef,
    Authority,
    JournalEvent,
    Profile,
)
from zuat.pub.artifact_models import (
    ArtifactStatus,
    PluginArtifactContext,
)
from zuat.pub.models import (
    SUPPORTED_AGENTS,
    AssetInput,
    AssetInspection,
    AssetSelector,
    OperationResult,
    OperationStatus,
    ZuatRequest,
)
from zuat.pub.extensions import ZuatExtension, register_extension
from zuat.pub.skills import SkillCandidate, SkillLocation, locate_skill
from zuat.pub.bundles.models import (
    BundleCheck, BundleDiagnostics, BundleCleanupError,
    BundleBuild, BundleBuildError, BundleError, BundleNotFoundError,
    BundleOperationResult, BundleOutputError, BundleRecord, BundleStoreError, BundleTarget,
)
from zuat.specs.native import (
    PluginContribution,
    PluginRecord,
    PluginRef,
    PluginRevision,
)


def _call(
    method: str,
    request: object,
    *,
    root: str | Path | None = None,
    home=None,
    project_root=None,
    trust_project=False,
    **kwargs,
):
    """Open a short-lived service with the same explicit context as stateful callers.

    Import lazily so importing public types does not initialize Git or adapters;
    the context manager closes resources even when dispatch raises.
    """
    from zuat.pub.service import Zuat

    with Zuat(
        root=root, home=home, project_root=project_root, trust_project=trust_project
    ) as service:
        return getattr(service, method)(request, **kwargs)


def _selector(
    selector: AssetSelector | None,
    *,
    agent: str | None,
    kind: str | None,
    scope: str | None,
    authority: Authority | str | None,
    present: bool | None,
    provider: str | None = None,
    plugin_id: str | None = None,
    version: str | None = None,
    name: str | None = None,
) -> AssetSelector:
    """Reject mixed selection styles rather than silently overriding caller filters."""
    if selector is not None:
        if any(
            value is not None
            for value in (
                agent,
                kind,
                scope,
                authority,
                provider,
                plugin_id,
                version,
                name,
            )
        ):
            raise ValueError("pass either selector or keyword filters, not both")
        if present is not True:
            raise ValueError("pass either selector or keyword filters, not both")
        return selector
    return AssetSelector(
        agent=agent or "",
        kind=kind,
        scope=scope,
        authority=Authority(authority) if authority is not None else None,
        present=present,
        provider=provider,
        plugin_id=plugin_id,
        version=version,
        name=name,
    )


def __getattr__(name: str):
    """Load the stateful facade only on demand, keeping public type imports light."""
    if name == "Zuat":
        from zuat.pub.service import Zuat

        return Zuat
    raise AttributeError(name)


def status(
    request: ZuatRequest = ZuatRequest(), *, root: str | Path | None = None, **context
):
    """Observe selected agents, or report unresolved update intent before observation."""
    return _call("status", request, root=root, **context)


def inspect_asset(
    asset: AssetInput, *, root=None, home=None, project_root=None, trust_project=False
):
    """Compare source and native state without adoption; forward explicit runtime context."""
    return _call(
        "inspect_asset",
        asset,
        root=root,
        home=home,
        project_root=project_root,
        trust_project=trust_project,
    )


def update_asset(
    asset: AssetInput,
    *,
    force=False,
    root=None,
    home=None,
    project_root=None,
    trust_project=False,
):
    """Update one existing independent asset with verified, restorable before-state."""
    return _call(
        "update_asset",
        asset,
        force=force,
        root=root,
        home=home,
        project_root=project_root,
        trust_project=trust_project,
    )


def list_assets(
    selector: AssetSelector | None = None,
    *,
    agent: str | None = None,
    kind: str | None = None,
    scope: str | None = None,
    authority: Authority | str | None = None,
    present: bool | None = True,
    provider: str | None = None,
    plugin_id: str | None = None,
    version: str | None = None,
    name: str | None = None,
    root: str | Path | None = None,
    **context,
):
    """Observe assets matching the selector without granting ownership."""
    selected = _selector(
        selector,
        agent=agent,
        kind=kind,
        scope=scope,
        authority=authority,
        present=present,
        provider=provider,
        plugin_id=plugin_id,
        version=version,
        name=name,
    )
    return _call("list_assets", selected, root=root, **context)


def adopt_all(
    selector: AssetSelector | None = None,
    *,
    agent: str | None = None,
    kind: str | None = None,
    scope: str | None = None,
    authority: Authority | str | None = None,
    present: bool | None = True,
    provider: str | None = None,
    plugin_id: str | None = None,
    version: str | None = None,
    name: str | None = None,
    force: bool = False,
    root: str | Path | None = None,
    **context,
):
    """Adopt selected present assets through one recoverable install operation."""
    selected = _selector(
        selector,
        agent=agent,
        kind=kind,
        scope=scope,
        authority=authority,
        present=present,
        provider=provider,
        plugin_id=plugin_id,
        version=version,
        name=name,
    )
    return _call("adopt_all", selected, root=root, force=force, **context)


def uninstall_all(
    selector: AssetSelector | None = None,
    *,
    agent: str | None = None,
    kind: str | None = None,
    scope: str | None = None,
    authority: Authority | str | None = None,
    present: bool | None = True,
    provider: str | None = None,
    plugin_id: str | None = None,
    version: str | None = None,
    name: str | None = None,
    force: bool = False,
    root: str | Path | None = None,
    **context,
):
    """Remove selected present assets through one recoverable operation."""
    selected = _selector(
        selector,
        agent=agent,
        kind=kind,
        scope=scope,
        authority=authority,
        present=present,
        provider=provider,
        plugin_id=plugin_id,
        version=version,
        name=name,
    )
    return _call("uninstall_all", selected, root=root, force=force, **context)


def restore_all(
    operation_id: str,
    selector: AssetSelector | None = None,
    *,
    agent: str | None = None,
    kind: str | None = None,
    scope: str | None = None,
    authority: Authority | str | None = None,
    present: bool | None = True,
    provider: str | None = None,
    plugin_id: str | None = None,
    version: str | None = None,
    name: str | None = None,
    force: bool = False,
    root: str | Path | None = None,
    **context,
):
    """Restore selected before-state assets, preserving unrelated later additions."""
    selected = _selector(
        selector,
        agent=agent,
        kind=kind,
        scope=scope,
        authority=authority,
        present=present,
        provider=provider,
        plugin_id=plugin_id,
        version=version,
        name=name,
    )
    return _call(
        "restore_all",
        operation_id,
        root=root,
        selector=selected,
        force=force,
        **context,
    )


def install(request: ZuatRequest, *, root: str | Path | None = None, **context):
    """Install explicit inputs or adopt references through the selected profile."""
    return _call("install", request, root=root, **context)


def uninstall(request: ZuatRequest, *, root: str | Path | None = None, **context):
    """Remove explicit references, requiring force for conflicting or unowned state."""
    return _call("uninstall", request, root=root, **context)


def profiles(
    request: ZuatRequest = ZuatRequest(), *, root: str | Path | None = None, **context
):
    """List named desired profiles without claiming native application."""
    return _call("profiles", request, root=root, **context)


def create_profile(request: ZuatRequest, *, root: str | Path | None = None, **context):
    """Record a named profile after preserving current observed drift."""
    return _call("create_profile", request, root=root, **context)


def switch_profile(request: ZuatRequest, *, root: str | Path | None = None, **context):
    """Reconcile a profile through native resolvers before publishing its selection."""
    return _call("switch_profile", request, root=root, **context)


def history(
    request: ZuatRequest = ZuatRequest(), *, root: str | Path | None = None, **context
):
    """Return domain history without exposing the private Git tracking mechanism."""
    return _call("history", request, root=root, **context)


def revert(request: ZuatRequest, *, root: str | Path | None = None, **context):
    """Append an inverse of a successful operation; never reset or erase history."""
    return _call("revert", request, root=root, **context)


def _plugin_call(
    method,
    *args,
    root=None,
    home=None,
    project_root=None,
    trust_project=False,
    bundle_root=None,
    **kwargs,
):
    """Dispatch runtime plugin/artifact calls with one short-lived service context.

    Unlike request-based asset operations, these methods accept domain values;
    keep resource lifetime and explicit context forwarding identical to _call.
    """
    from zuat.pub.service import Zuat

    with Zuat(
        root=root, home=home, project_root=project_root, trust_project=trust_project,
        bundle_root=bundle_root,
    ) as service:
        return getattr(service, method)(*args, **kwargs)


def discover_plugins(agent, *, include_available=False, **context):
    """Discover native revisions and contribution pointers, not copied plugin sources."""
    return _plugin_call(
        "discover_plugins", agent, include_available=include_available, **context
    )


def get_bundle(bundle_id, **context):
    """Get a stored registration; this is not a live native status query."""
    return _plugin_call("get_bundle", bundle_id, **context)


def add_bundle(source, *, name=None, revision="HEAD", agents=None, trust=False, force=False, **context):
    """Build and bootstrap one exact revision with ordinary trust/force rules."""
    return _plugin_call(
        "add_bundle", source, name=name, revision=revision, agents=agents,
        trust=trust, force=force, **context,
    )


def build_bundle(source, *, name=None, revision="HEAD", **context):
    """Compile a source into immutable outputs in the selected compiler store."""
    return _plugin_call("build_bundle", source, name=name, revision=revision, **context)


def resolve_bundle(bundle_id, *, build_revision=None, agent, **context):
    """Resolve one integrity-checked retained build without private path knowledge."""
    return _plugin_call("resolve_bundle", bundle_id, build_revision=build_revision, agent=agent, **context)


def list_bundles(**context):
    """List bundle handles from the explicitly selected compiler store."""
    return _plugin_call("list_bundles", **context)


def doctor_bundle(bundle_id, *, agents=None, **context):
    """Inspect selected build integrity and manager availability without repair."""
    return _plugin_call("doctor_bundle", bundle_id, agents=agents, **context)


def bootstrap_bundle(bundle_id, *, build_revision=None, agents=None, trust=False, force=False, **context):
    """Attempt independent native targets with explicit source trust and force."""
    return _plugin_call("bootstrap_bundle", bundle_id, build_revision=build_revision, agents=agents, trust=trust, force=force, **context)


def remove_bundle(bundle_id, *, agents=None, purge=False, **context):
    """Remove registered targets; explicit purge requires complete removal."""
    return _plugin_call("remove_bundle", bundle_id, agents=agents, purge=purge, **context)


def install_plugin(ref, *, trust=False, force=False, **context):
    """Install through the native manager with explicit trust for non-catalog sources."""
    return _plugin_call("install_plugin", ref, trust=trust, force=force, **context)


def update_plugin(ref, *, force=False, **context):
    """Update through the native manager while preserving recovery evidence."""
    return _plugin_call("update_plugin", ref, force=force, **context)


def remove_plugin(ref, *, force=False, **context):
    """Remove an entire native plugin installation, not its individual contributions."""
    return _plugin_call("remove_plugin", ref, force=force, **context)


def resolve_artifacts(agent, identifier, **context):
    """Return artifacts eligible under both native state and host selection policy."""
    return _plugin_call("resolve_artifacts", agent, identifier, **context)


def artifact_status(ref, identifier, *, revision=None, **context):
    """Report eligibility for the current installation, optionally requiring a revision."""
    return _plugin_call(
        "artifact_status", ref, identifier, revision=revision, **context
    )


def set_artifact_policy(ref, identifier, policy, **context):
    """Journal host artifact selection without modifying native plugin activation."""
    return _plugin_call("set_artifact_policy", ref, identifier, policy, **context)


def clear_artifact_policy(ref, identifier, **context):
    """Append inherited host policy rather than erasing its earlier decisions."""
    return _plugin_call("clear_artifact_policy", ref, identifier, **context)


__all__ = [
    "BundleCleanupError",
    "doctor_bundle", "BundleCheck", "BundleDiagnostics",
    "add_bundle",
    "bootstrap_bundle", "remove_bundle",
    "build_bundle", "resolve_bundle",
    "BundleBuild", "BundleBuildError", "BundleError", "BundleNotFoundError",
    "BundleOperationResult", "BundleOutputError", "BundleRecord", "BundleStoreError",
    "BundleTarget", "get_bundle", "list_bundles",
    "AssetInspection",
    "inspect_asset",
    "update_asset",
    "PluginRef",
    "PluginRecord",
    "PluginRevision",
    "PluginContribution",
    "ZuatExtension",
    "ArtifactStatus",
    "PluginArtifactContext",
    "discover_plugins",
    "install_plugin",
    "update_plugin",
    "remove_plugin",
    "register_extension",
    "resolve_artifacts",
    "artifact_status",
    "set_artifact_policy",
    "clear_artifact_policy",
    "AssetEvidence",
    "AssetInput",
    "AssetSelector",
    "AssetRef",
    "Authority",
    "JournalEvent",
    "OperationResult",
    "OperationStatus",
    "Profile",
    "SUPPORTED_AGENTS",
    "SkillCandidate",
    "SkillLocation",
    "locate_skill",
    "Zuat",
    "ZuatRequest",
    "adopt_all",
    "create_profile",
    "history",
    "install",
    "list_assets",
    "profiles",
    "revert",
    "restore_all",
    "status",
    "switch_profile",
    "uninstall",
    "uninstall_all",
]
