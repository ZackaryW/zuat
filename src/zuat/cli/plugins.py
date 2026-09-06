"""Thin Click plugin handlers using only the supported Python interface."""

from pathlib import Path

import click

from zuat import pub as api


def attach_plugins(cli, finish):
    @cli.group("plugin")
    @click.option("--agent", type=click.Choice(api.SUPPORTED_AGENTS), required=True)
    @click.option("--home", type=click.Path(path_type=Path, file_okay=False))
    @click.option("--project-root", type=click.Path(path_type=Path, file_okay=False))
    @click.option(
        "--trust-project",
        is_flag=True,
        help="Trust the selected project's native configuration for this invocation.",
    )
    @click.pass_context
    def group(ctx, agent, home, project_root, trust_project):
        ctx.ensure_object(dict)["plugin_context"] = dict(
            agent=agent,
            home=home,
            project_root=project_root,
            trust_project=trust_project,
        )

    def context(ctx):
        values = dict(ctx.obj["plugin_context"])
        agent = values.pop("agent")
        return agent, {**values, "root": ctx.obj.get("root")}

    @group.command("discover")
    @click.option("--available", is_flag=True)
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def discover(ctx, available, json_output):
        agent, options = context(ctx)
        finish(
            api.discover_plugins(agent, include_available=available, **options),
            json_output,
        )

    @group.command("install")
    @click.argument("plugin_id")
    @click.option(
        "--scope",
        type=click.Choice(["user", "project", "local", "managed"]),
        default="user",
    )
    @click.option("--source")
    @click.option("--trust", is_flag=True)
    @click.option("--force", is_flag=True)
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def install(ctx, plugin_id, scope, source, trust, force, json_output):
        agent, options = context(ctx)
        finish(
            api.install_plugin(
                api.PluginRef(agent, plugin_id, scope, source),
                trust=trust,
                force=force,
                **options,
            ),
            json_output,
        )

    def mutation(name, operation):
        @group.command(name)
        @click.argument("plugin_id")
        @click.option(
            "--scope",
            type=click.Choice(["user", "project", "local", "managed"]),
            default="user",
        )
        @click.option("--force", is_flag=True)
        @click.option("--json", "json_output", is_flag=True)
        @click.pass_context
        def command(ctx, plugin_id, scope, force, json_output):
            agent, options = context(ctx)
            finish(
                getattr(api, operation)(
                    api.PluginRef(agent, plugin_id, scope), force=force, **options
                ),
                json_output,
            )

    mutation("update", "update_plugin")
    mutation("remove", "remove_plugin")

    @group.group("artifact")
    def artifact():
        """Inspect and configure host-registered artifact extensions."""

    @artifact.command("status")
    @click.argument("plugin_id")
    @click.argument("identifier")
    @click.option("--scope", default="user")
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def status(ctx, plugin_id, identifier, scope, json_output):
        agent, options = context(ctx)
        result = api.artifact_status(
            api.PluginRef(agent, plugin_id, scope), identifier, **options
        )
        finish(
            {
                "operation": "artifact-status",
                "status": result.reason,
                **result.to_dict(),
            },
            json_output,
        )

    @artifact.command("set")
    @click.argument("plugin_id")
    @click.argument("identifier")
    @click.argument("policy", type=click.Choice(["inherit", "enabled", "disabled"]))
    @click.option("--scope", default="user")
    @click.option("--json", "json_output", is_flag=True)
    @click.pass_context
    def set_policy(ctx, plugin_id, identifier, policy, scope, json_output):
        agent, options = context(ctx)
        finish(
            api.set_artifact_policy(
                api.PluginRef(agent, plugin_id, scope), identifier, policy, **options
            ),
            json_output,
        )
