"""Optional Click presentation layer; every handler calls :mod:`zuat.pub`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from zuat import pub as api
from zuat.cli.plugins import attach_plugins

AGENT = click.Choice(api.SUPPORTED_AGENTS, case_sensitive=True)
KIND = click.Choice(("skill", "hook", "plugin"), case_sensitive=True)
SCOPE = click.Choice(("user", "project", "local", "managed"), case_sensitive=True)
AUTHORITY = click.Choice(
    ("authoritative", "unauthoritative", "conflicting", "partial", "indeterminate"),
    case_sensitive=True,
)


def _payload(result: Any) -> dict[str, Any]:
    value = result.to_dict() if hasattr(result, "to_dict") else result
    if not isinstance(value, dict):
        return {"value": value}
    return dict(value)


def _emit(result: Any, json_output: bool) -> None:
    payload = _payload(result)
    diagnostics = tuple(payload.pop("diagnostics", ()))
    if json_output:
        click.echo(json.dumps({"result": payload}, sort_keys=True))
    else:
        operation = str(payload.get("operation", "operation"))
        click.echo(f"{operation}: {payload.get('status', 'unknown')}")
        operation_id = payload.get("operation_id")
        if operation_id:
            click.echo(f"operation: {operation_id}")
        profile = payload.get("profile")
        if profile:
            click.echo(f"profile: {profile}")
        for plugin in payload.get("plugins", ()):
            ref = plugin["ref"]
            version = plugin.get("installed_version") if plugin["installed"] else plugin.get("available_version")
            state = plugin["activation"] if plugin["installed"] else "available"
            click.echo(f"plugin: {ref['agent']}/{ref['scope']} {ref['native_ref']} {version or 'unresolved'} {state}")
        for asset in payload.get("assets", ()):  # type: ignore[union-attr]
            if isinstance(asset, dict):
                detail = "/".join(
                    str(asset.get(key, "")) for key in ("agent", "scope", "kind")
                ).strip("/")
                authority = asset.get("authority")
                suffix = f" {authority}" if authority else ""
                click.echo(f"asset: {asset.get('asset_ref')} {detail}{suffix}".rstrip())
        for item in payload.get("profiles", ()):  # type: ignore[union-attr]
            if isinstance(item, dict):
                marker = " *" if item.get("selected") else ""
                click.echo(f"profile: {item.get('name')}{marker}")
        for event in payload.get("history", ()):  # type: ignore[union-attr]
            if isinstance(event, dict):
                forced = " forced" if event.get("forced") else ""
                click.echo(
                    "event: "
                    f"{event.get('operation_id')} {event.get('kind')} "
                    f"{event.get('outcome')}{forced}"
                )
    for diagnostic in diagnostics:
        click.echo(diagnostic, err=True)


def _finish(result: Any, json_output: bool) -> None:
    _emit(result, json_output)
    status = getattr(result, "status", None)
    if getattr(status, "value", status) == "failed":
        raise click.exceptions.Exit(1)


def _request(
    *,
    agents: tuple[str, ...] = api.SUPPORTED_AGENTS,
    assets: tuple[api.AssetInput, ...] = (),
    asset_refs: tuple[str, ...] = (),
    profile: str | None = None,
    operation_id: str | None = None,
    force: bool = False,
) -> api.ZuatRequest:
    return api.ZuatRequest(
        agents=agents,
        assets=assets,
        asset_refs=asset_refs,
        profile=profile,
        operation_id=operation_id,
        force=force,
    )


@click.group()
@click.option(
    "--root",
    type=click.Path(path_type=Path, file_okay=False),
    envvar="ZUAT_HOME",
    help="Use an explicit isolated registry root.",
)
@click.pass_context
def cli(context: click.Context, root: Path | None) -> None:
    """Observe and reconcile coding-agent assets."""
    context.ensure_object(dict)["root"] = root


def _root(context: click.Context) -> Path | None:
    return context.ensure_object(dict).get("root")


def _selected_agents(agents: tuple[str, ...]) -> tuple[str, ...]:
    return agents or api.SUPPORTED_AGENTS


attach_plugins(cli, _finish)


@cli.command("status")
@click.option("--agent", "agents", type=AGENT, multiple=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def status_command(
    context: click.Context, agents: tuple[str, ...], json_output: bool
) -> None:
    """Observe native assets and report their domain state."""
    _finish(
        api.status(_request(agents=_selected_agents(agents)), root=_root(context)),
        json_output,
    )


def _provider_options(function):
    for option in ("--name", "--version", "--plugin-id"):
        function = click.option(option)(function)
    return click.option("--provider", type=click.Choice(["global", "plugin"]))(function)


@cli.command("list-assets")
@click.option("--agent", type=AGENT, required=True)
@click.option("--kind", type=KIND)
@click.option("--scope", type=SCOPE)
@click.option("--authority", type=AUTHORITY)
@_provider_options
@click.option("--present/--absent", default=True, show_default=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def list_assets_command(
    context: click.Context,
    agent: str,
    kind: str | None,
    scope: str | None,
    authority: str | None,
    present: bool,
    json_output: bool,
    **provider_filters,
) -> None:
    """List assets matching explicit domain filters."""
    _finish(
        api.list_assets(
            agent=agent,
            kind=kind,
            scope=scope,
            authority=authority,
            present=present,
            **{key: value for key, value in provider_filters.items() if value is not None},
            root=_root(context),
        ),
        json_output,
    )


@cli.command("adopt-all")
@click.option("--agent", type=AGENT, required=True)
@click.option("--kind", type=KIND, required=True)
@click.option("--scope", type=SCOPE)
@click.option("--authority", type=AUTHORITY)
@_provider_options
@click.option("--present/--absent", default=True, show_default=True)
@click.option("--force", is_flag=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def adopt_all_command(
    context: click.Context,
    agent: str,
    kind: str,
    scope: str | None,
    authority: str | None,
    present: bool,
    force: bool,
    json_output: bool,
    **provider_filters,
) -> None:
    """Adopt every present asset matching the filters."""
    _finish(
        api.adopt_all(
            agent=agent,
            kind=kind,
            scope=scope,
            authority=authority,
            present=present,
            **{key: value for key, value in provider_filters.items() if value is not None},
            force=force,
            root=_root(context),
        ),
        json_output,
    )


@cli.command("uninstall-all")
@click.option("--agent", type=AGENT, required=True)
@click.option("--kind", type=KIND, required=True)
@click.option("--scope", type=SCOPE)
@click.option("--authority", type=AUTHORITY)
@_provider_options
@click.option("--present/--absent", default=True, show_default=True)
@click.option("--force", is_flag=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def uninstall_all_command(
    context: click.Context,
    agent: str,
    kind: str,
    scope: str | None,
    authority: str | None,
    present: bool,
    force: bool,
    json_output: bool,
    **provider_filters,
) -> None:
    """Uninstall every present asset matching the filters."""
    _finish(
        api.uninstall_all(
            agent=agent,
            kind=kind,
            scope=scope,
            authority=authority,
            present=present,
            **{key: value for key, value in provider_filters.items() if value is not None},
            force=force,
            root=_root(context),
        ),
        json_output,
    )


@cli.command("restore-all")
@click.option("--operation-id", required=True)
@click.option("--agent", type=AGENT, required=True)
@click.option("--kind", type=KIND)
@click.option("--scope", type=SCOPE)
@click.option("--authority", type=AUTHORITY)
@_provider_options
@click.option("--present/--absent", default=True, show_default=True)
@click.option("--force", is_flag=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def restore_all_command(
    context: click.Context,
    operation_id: str,
    agent: str,
    kind: str | None,
    scope: str | None,
    authority: str | None,
    present: bool,
    force: bool,
    json_output: bool,
    **provider_filters,
) -> None:
    """Recover matching assets from an operation's prior evidence."""
    _finish(
        api.restore_all(
            operation_id=operation_id,
            agent=agent,
            kind=kind,
            scope=scope,
            authority=authority,
            present=present,
            **{key: value for key, value in provider_filters.items() if value is not None},
            force=force,
            root=_root(context),
        ),
        json_output,
    )


@cli.command("install")
@click.option("--agent", "agents", type=AGENT, multiple=True, required=True)
@click.option("--asset-ref", "asset_refs", multiple=True)
@click.option("--source", type=click.Path(path_type=Path))
@click.option("--kind", type=KIND)
@click.option("--name")
@click.option("--scope", type=SCOPE, default="user", show_default=True)
@click.option("--locator")
@click.option("--profile")
@click.option("--force", is_flag=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def install_command(
    context: click.Context,
    agents: tuple[str, ...],
    asset_refs: tuple[str, ...],
    source: Path | None,
    kind: str | None,
    name: str | None,
    scope: str,
    locator: str | None,
    profile: str | None,
    force: bool,
    json_output: bool,
) -> None:
    """Install source content or adopt observed assets by stable reference."""
    if source is None and not asset_refs:
        raise click.UsageError("install requires --source or --asset-ref")
    if source is not None and kind is None:
        raise click.UsageError("--source requires --kind")
    if source is not None and len(agents) != 1:
        raise click.UsageError("--source requires exactly one --agent")
    assets = (
        (
            api.AssetInput(
                agent=agents[0],
                kind=kind,
                scope=scope,
                name=name,
                locator=locator,
                source=str(source),
            ),
        )
        if source is not None and kind is not None
        else ()
    )
    _finish(
        api.install(
            _request(
                agents=agents,
                assets=assets,
                asset_refs=asset_refs,
                profile=profile,
                force=force,
            ),
            root=_root(context),
        ),
        json_output,
    )


@cli.command("uninstall")
@click.option("--agent", "agents", type=AGENT, multiple=True, required=True)
@click.option("--asset-ref", "asset_refs", multiple=True, required=True)
@click.option("--profile")
@click.option("--force", is_flag=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def uninstall_command(
    context: click.Context,
    agents: tuple[str, ...],
    asset_refs: tuple[str, ...],
    profile: str | None,
    force: bool,
    json_output: bool,
) -> None:
    """Uninstall assets by stable reference."""
    _finish(
        api.uninstall(
            _request(
                agents=agents,
                asset_refs=asset_refs,
                profile=profile,
                force=force,
            ),
            root=_root(context),
        ),
        json_output,
    )


@cli.group("profile")
def profile_group() -> None:
    """Manage named desired-state profiles."""


@profile_group.command("list")
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def profile_list_command(context: click.Context, json_output: bool) -> None:
    _finish(api.profiles(root=_root(context)), json_output)


@profile_group.command("create")
@click.argument("profile")
@click.option("--agent", "agents", type=AGENT, multiple=True, required=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def profile_create_command(
    context: click.Context,
    profile: str,
    agents: tuple[str, ...],
    json_output: bool,
) -> None:
    _finish(
        api.create_profile(
            _request(profile=profile, agents=agents), root=_root(context)
        ),
        json_output,
    )


@profile_group.command("switch")
@click.argument("profile")
@click.option("--agent", "agents", type=AGENT, multiple=True, required=True)
@click.option("--force", is_flag=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def profile_switch_command(
    context: click.Context,
    profile: str,
    agents: tuple[str, ...],
    force: bool,
    json_output: bool,
) -> None:
    _finish(
        api.switch_profile(
            _request(profile=profile, agents=agents, force=force),
            root=_root(context),
        ),
        json_output,
    )


@cli.command("history")
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def history_command(context: click.Context, json_output: bool) -> None:
    """Show ordered domain operations."""
    _finish(api.history(root=_root(context)), json_output)


@cli.command("revert")
@click.option("--operation-id", required=True)
@click.option("--agent", "agents", type=AGENT, multiple=True, required=True)
@click.option("--force", is_flag=True)
@click.option("--json", "json_output", is_flag=True)
@click.pass_context
def revert_command(
    context: click.Context,
    operation_id: str,
    agents: tuple[str, ...],
    force: bool,
    json_output: bool,
) -> None:
    """Apply a prior operation's inverse as a new operation."""
    _finish(
        api.revert(
            _request(agents=agents, operation_id=operation_id, force=force),
            root=_root(context),
        ),
        json_output,
    )
