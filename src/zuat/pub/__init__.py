"""Supported public Python interface used by callers and the optional CLI."""

from __future__ import annotations

from pathlib import Path
from zuat.pub.artifact_models import ArtifactExtension, ArtifactStatus, PluginArtifactContext
from zuat.specs.native import PluginRef, PluginRecord, PluginRevision, PluginContribution

from zuat.gitcore.models import AssetEvidence, AssetRef, Authority, JournalEvent, Profile
from zuat.pub.models import (
    AssetInput,
    AssetSelector,
    OperationResult,
    OperationStatus,
    SUPPORTED_AGENTS,
    ZuatRequest,
)


def _call(method: str, request: object, *, root: str | Path | None = None, **kwargs):
    from zuat.pub.service import Zuat

    with Zuat(root=root) as service:
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
    if selector is not None:
        if any(value is not None for value in (agent, kind, scope, authority, provider, plugin_id, version, name)):
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
        provider=provider, plugin_id=plugin_id, version=version, name=name,
    )


def __getattr__(name: str):
    if name == "Zuat":
        from zuat.pub.service import Zuat

        return Zuat
    raise AttributeError(name)


def status(request: ZuatRequest = ZuatRequest(), *, root: str | Path | None = None):
    return _call("status", request, root=root)


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
):
    selected = _selector(
        selector,
        agent=agent,
        kind=kind,
        scope=scope,
        authority=authority,
        present=present,
        provider=provider, plugin_id=plugin_id, version=version, name=name,
    )
    return _call("list_assets", selected, root=root)


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
):
    selected = _selector(
        selector,
        agent=agent,
        kind=kind,
        scope=scope,
        authority=authority,
        present=present,
        provider=provider, plugin_id=plugin_id, version=version, name=name,
    )
    return _call("adopt_all", selected, root=root, force=force)


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
):
    selected = _selector(
        selector,
        agent=agent,
        kind=kind,
        scope=scope,
        authority=authority,
        present=present,
        provider=provider, plugin_id=plugin_id, version=version, name=name,
    )
    return _call("uninstall_all", selected, root=root, force=force)


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
):
    selected = _selector(
        selector,
        agent=agent,
        kind=kind,
        scope=scope,
        authority=authority,
        present=present,
        provider=provider, plugin_id=plugin_id, version=version, name=name,
    )
    return _call(
        "restore_all",
        operation_id,
        root=root,
        selector=selected,
        force=force,
    )


def install(request: ZuatRequest, *, root: str | Path | None = None):
    return _call("install", request, root=root)


def uninstall(request: ZuatRequest, *, root: str | Path | None = None):
    return _call("uninstall", request, root=root)


def profiles(request: ZuatRequest = ZuatRequest(), *, root: str | Path | None = None):
    return _call("profiles", request, root=root)


def create_profile(request: ZuatRequest, *, root: str | Path | None = None):
    return _call("create_profile", request, root=root)


def switch_profile(request: ZuatRequest, *, root: str | Path | None = None):
    return _call("switch_profile", request, root=root)


def history(request: ZuatRequest = ZuatRequest(), *, root: str | Path | None = None):
    return _call("history", request, root=root)


def revert(request: ZuatRequest, *, root: str | Path | None = None):
    return _call("revert", request, root=root)


def _plugin_call(method, *args, root=None, home=None, project_root=None, trust_project=False, **kwargs):
    from zuat.pub.service import Zuat
    with Zuat(root=root, home=home, project_root=project_root, trust_project=trust_project) as service:
        return getattr(service, method)(*args, **kwargs)


def discover_plugins(agent, *, include_available=False, **context):
    return _plugin_call("discover_plugins", agent, include_available=include_available, **context)


def install_plugin(ref, *, trust=False, force=False, **context):
    return _plugin_call("install_plugin", ref, trust=trust, force=force, **context)


def update_plugin(ref, *, force=False, **context):
    return _plugin_call("update_plugin", ref, force=force, **context)


def remove_plugin(ref, *, force=False, **context):
    return _plugin_call("remove_plugin", ref, force=force, **context)


def register_artifact(extension):
    from zuat.pub.artifacts import register_extension
    register_extension(extension)


def resolve_artifacts(agent, identifier, **context):
    return _plugin_call("resolve_artifacts", agent, identifier, **context)


def artifact_status(ref, identifier, *, revision=None, **context):
    return _plugin_call("artifact_status", ref, identifier, revision=revision, **context)


def set_artifact_policy(ref, identifier, policy, **context):
    return _plugin_call("set_artifact_policy", ref, identifier, policy, **context)


def clear_artifact_policy(ref, identifier, **context):
    return _plugin_call("clear_artifact_policy", ref, identifier, **context)


__all__ = [
    "PluginRef", "PluginRecord", "PluginRevision", "PluginContribution",
    "ArtifactExtension", "ArtifactStatus", "PluginArtifactContext",
    "discover_plugins", "install_plugin", "update_plugin", "remove_plugin",
    "register_artifact", "resolve_artifacts", "artifact_status", "set_artifact_policy", "clear_artifact_policy",
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
