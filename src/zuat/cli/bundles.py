"""Optional presentation only: all bundle actions enter through zuat.pub."""

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path

import click

from zuat import pub


def attach_bundles(cli):
    @cli.group("bundle")
    @click.option("--bundle-root", type=click.Path(path_type=Path, file_okay=False))
    @click.option("--home", type=click.Path(path_type=Path, file_okay=False))
    @click.pass_context
    def bundle(ctx, bundle_root, home):
        """Build plugins and explicitly bootstrap or remove registered targets."""
        ctx.ensure_object(dict)["bundle_context"] = {
            "bundle_root": bundle_root,
            "home": home,
        }

    def invoke(ctx, method, *args, json_output=False, **kwargs):
        options = {**ctx.obj["bundle_context"], "root": ctx.obj.get("root")}
        try:
            result = getattr(pub, method)(*args, **options, **kwargs)
        except pub.BundleError as error:
            raise click.ClickException(str(error)) from None
        payload = (
            asdict(result)
            if is_dataclass(result)
            else [asdict(item) for item in result]
        )
        if json_output:
            click.echo(json.dumps({"result": payload}, sort_keys=True))
        elif isinstance(result, pub.BundleOperationResult):
            click.echo(f"{result.operation}: {result.bundle_id}")
            for target in result.targets:
                click.echo(
                    f"{target.agent}: {target.status}"
                    + (f" ({target.reason})" if target.reason else "")
                )
        elif isinstance(result, pub.BundleBuild):
            click.echo(f"built: {result.bundle_id} {result.build_revision}")
        else:
            for record in (result,) if isinstance(result, pub.BundleRecord) else result:
                click.echo(f"bundle: {record.bundle_id}")
                for target in record.targets:
                    click.echo(f"  {target.agent}: last recorded {target.status}")
        if isinstance(result, pub.BundleOperationResult) and not result.ok:
            raise click.exceptions.Exit(1)

    @bundle.command("build")
    @click.argument("source")
    @click.option("--name")
    @click.option("--revision", default="HEAD")
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def build(ctx, source, name, revision, json_output):
        invoke(
            ctx,
            "build_bundle",
            source,
            name=name,
            revision=revision,
            json_output=json_output,
        )

    @bundle.command("list")
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def listing(ctx, json_output):
        """Show stored registrations, not freshly observed native status."""
        invoke(ctx, "list_bundles", json_output=json_output)

    @bundle.command("status")
    @click.argument("bundle_id")
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def status(ctx, bundle_id, json_output):
        """Show historical build and target-attempt evidence without mutation."""
        invoke(ctx, "get_bundle", bundle_id, json_output=json_output)

    @bundle.command("bootstrap")
    @click.argument("bundle_id")
    @click.option("--build-revision")
    @click.option(
        "--agent", "agents", multiple=True, type=click.Choice(pub.SUPPORTED_AGENTS)
    )
    @click.option("--trust", is_flag=True)
    @click.option("--force", is_flag=True)
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def bootstrap(ctx, bundle_id, build_revision, agents, trust, force, json_output):
        invoke(
            ctx,
            "bootstrap_bundle",
            bundle_id,
            build_revision=build_revision,
            agents=agents or None,
            trust=trust,
            force=force,
            json_output=json_output,
        )

    @bundle.command("remove")
    @click.argument("bundle_id")
    @click.option(
        "--agent", "agents", multiple=True, type=click.Choice(pub.SUPPORTED_AGENTS)
    )
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def remove(ctx, bundle_id, agents, json_output):
        invoke(
            ctx,
            "remove_bundle",
            bundle_id,
            agents=agents or None,
            json_output=json_output,
        )
