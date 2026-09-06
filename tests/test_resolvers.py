import ast
from pathlib import Path

import pytest

from zuat.specs.claude import ClaudeResolver
from zuat.specs.codex import CodexResolver
from zuat.specs.interface import AgentResolver, ConflictPolicy, ResolutionError
from zuat.specs.kimi import KimiResolver
from zuat.specs.native import (
    PluginActivation,
    PluginLifecycleResult,
    PluginRecord,
    PluginRef,
)
from zuat.specs.pi import PiResolver
from zuat.specs.registry import resolver_for


SKILL = """---
name: reviewer
description: Review changes
---
Review the selected change.
"""


@pytest.mark.parametrize("agent", ("codex", "claude", "kimi", "pi"))
def test_resolver_contract_observes_native_skill(
    agent: str, tmp_path: Path
) -> None:
    destinations = {
        "codex": ".codex/skills",
        "claude": ".claude/skills",
        "kimi": ".kimi-code/skills",
        "pi": ".pi/agent/skills",
    }
    home = tmp_path / "home"
    native = home / destinations[agent] / "reviewer"
    native.mkdir(parents=True)
    (native / "SKILL.md").write_text(SKILL, encoding="utf-8")
    observations = tmp_path / "observations"
    class EmptyInventory:
        def discover(self, *, include_available=False):
            return ()
    resolver = resolver_for(agent, home=home, plugins=EmptyInventory())

    assert isinstance(resolver, AgentResolver)
    observation = resolver.observe(observations)

    assert [asset.name for asset in observation.assets if asset.kind == "skill"] == [
        "reviewer"
    ]
    assert (observations / agent / "user/skills/reviewer/SKILL.md").read_text(
        encoding="utf-8"
    ) == SKILL


def test_agent_trees_with_identical_assets_diverge_independently(tmp_path: Path) -> None:
    home = tmp_path / "home"
    for relative in (".codex/skills/reviewer", ".claude/skills/reviewer"):
        native = home / relative
        native.mkdir(parents=True)
        (native / "SKILL.md").write_text(SKILL, encoding="utf-8")
    observations = tmp_path / "observations"
    resolver_for("codex", home=home).observe(observations)
    resolver_for("claude", home=home).observe(observations)

    codex = observations / "codex/user/skills/reviewer/SKILL.md"
    claude = observations / "claude/user/skills/reviewer/SKILL.md"
    codex.write_text(SKILL + "Codex only.\n", encoding="utf-8")

    assert claude.read_text(encoding="utf-8") == SKILL


def test_unknown_agent_is_rejected_without_fallback(tmp_path: Path) -> None:
    with pytest.raises(ResolutionError, match="unsupported agent"):
        resolver_for("other", home=tmp_path)


def test_preflight_rejects_cross_agent_plan(tmp_path: Path) -> None:
    codex = resolver_for("codex", home=tmp_path / "home")
    claude = resolver_for("claude", home=tmp_path / "home")
    plan = codex.plan(tmp_path / "profile", conflict_policy=ConflictPolicy.ABORT)
    with pytest.raises(ResolutionError, match="plan belongs"):
        claude.preflight(plan)


@pytest.mark.parametrize(
    "resolver_type", (CodexResolver, ClaudeResolver, KimiResolver, PiResolver)
)
def test_each_agent_module_owns_the_full_resolver_contract(
    resolver_type: type,
) -> None:
    assert {
        "observe",
        "plan",
        "preflight",
        "plan_uninstall",
        "materialize",
    } <= set(resolver_type.__dict__)


def test_shared_utilities_do_not_switch_on_concrete_agent_identity() -> None:
    utility_root = Path(__file__).parents[1] / "src/zuat/utils"
    identities = (
        "Agent.CODEX",
        "Agent.CLAUDE",
        "Agent.KIMI",
        "Agent.PI",
        "'codex'",
        "'claude'",
        "'kimi'",
        "'pi'",
        '"codex"',
        '"claude"',
        '"kimi"',
        '"pi"',
    )
    for path in utility_root.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.If, ast.IfExp, ast.Match)):
                continue
            source = ast.get_source_segment(text, node)
            assert source is not None
            assert not any(identity in source for identity in identities), (
                f"agent-specific branch in {path.name}"
            )


def test_symbolic_link_candidate_is_rejected_without_ingesting_target(
    tmp_path: Path,
) -> None:
    target = tmp_path / "credential"
    target.write_text("secret", encoding="utf-8")
    native = tmp_path / "home/.codex/skills"
    native.mkdir(parents=True)
    link = native / "leak"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    observations = tmp_path / "observations"
    observation = resolver_for("codex", home=tmp_path / "home").observe(
        observations
    )

    assert observation.rejected
    assert not (observations / "codex/user/skills/leak").exists()


@pytest.mark.parametrize(
    ("agent", "filename", "content", "native_config", "unrelated"),
    [
        (
            "codex",
            "guard.json",
            '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo ok"}]}]}}',
            ".codex/hooks.json",
            '{"unrelated":"kept"}',
        ),
        (
            "claude",
            "guard.json",
            '{"hooks":{"Stop":[{"hooks":[{"type":"command","command":"echo ok"}]}]}}',
            ".claude/settings.json",
            '{"unrelated":"kept"}',
        ),
        (
            "kimi",
            "guard.toml",
            '[[hooks]]\nevent = "Stop"\ncommand = "echo ok"\n',
            ".kimi-code/config.toml",
            'model = "unrelated"\n',
        ),
        (
            "pi",
            "guard.js",
            "export default function guard() {}\n",
            None,
            None,
        ),
    ],
)
def test_each_agent_owns_hook_format_location_mutation_and_verification(
    agent: str,
    filename: str,
    content: str,
    native_config: str | None,
    unrelated: str | None,
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    if native_config is not None:
        config = home / native_config
        config.parent.mkdir(parents=True)
        config.write_text(unrelated or "", encoding="utf-8")
    profile = tmp_path / "profile"
    desired = profile / agent / "user/hooks" / filename
    desired.parent.mkdir(parents=True)
    desired.write_text(content, encoding="utf-8")
    resolver = resolver_for(agent, home=home, state_root=tmp_path / "control")

    plan = resolver.plan(profile, conflict_policy=ConflictPolicy.REPLACE)
    resolver.preflight(plan)
    installed = resolver.materialize(plan)
    observation = resolver.observe(tmp_path / "observations")

    assert installed.verified
    assert len([asset for asset in observation.assets if asset.kind == "hook"]) == 1
    if unrelated is not None:
        assert "unrelated" in (home / native_config).read_text(encoding="utf-8")


@pytest.mark.parametrize("agent", ("codex", "claude", "kimi", "pi"))
def test_plugin_partial_evidence_never_converges(agent: str, tmp_path: Path) -> None:
    ref = PluginRef(agent, "example@market", "user", "market")
    record = PluginRecord(
        ref,
        "example",
        True,
        PluginActivation.PARTIAL,
        native_evidence={"enabled": False, "installed": True},
    )

    class PartialPlugins:
        def contributions(self, record):
            return ()
        def preflight(self, ref, operation, *, desired=None):
            pass

        def reconcile(self, desired):
            return self.install(desired.ref)

        def discover(self):
            return (record,)

        def install(self, selected, *, trust=False):
            return PluginLifecycleResult(
                "install", selected, "partial", before=record, after=record
            )

        def remove(self, selected):
            return PluginLifecycleResult(
                "remove", selected, "partial", before=record, after=record
            )

    resolver = resolver_for(
        agent,
        home=tmp_path / "home",
        state_root=tmp_path / "control",
        plugins=PartialPlugins(),
    )
    profile = tmp_path / "profile"
    observation = resolver.observe(profile)

    plan = resolver.plan(profile)
    resolver.preflight(plan)
    result = resolver.materialize(plan)

    declaration = next(asset for asset in observation.assets if asset.kind == "plugin")
    assert declaration.evidence["activation"] == "partial"
    assert result.state == "partial"
    assert not result.verified


def test_pi_rejects_extension_directory_without_native_entry_point(
    tmp_path: Path,
) -> None:
    extension = tmp_path / "home/.pi/agent/extensions/guard"
    extension.mkdir(parents=True)
    (extension / "helper.ts").write_text(
        "export const guard = true;\n", encoding="utf-8"
    )

    observation = resolver_for("pi", home=tmp_path / "home").observe(
        tmp_path / "observations"
    )

    assert not [asset for asset in observation.assets if asset.kind == "hook"]
    assert any("index.ts or index.js" in item for item in observation.rejected)


def test_kimi_project_hook_is_an_explicit_preflight_failure(tmp_path: Path) -> None:
    hook = tmp_path / "profile/kimi/project/hooks/guard.toml"
    hook.parent.mkdir(parents=True)
    hook.write_text(
        '[[hooks]]\nevent = "Stop"\ncommand = "echo ok"\n', encoding="utf-8"
    )
    resolver = resolver_for(
        "kimi", home=tmp_path / "home", project_root=tmp_path / "project"
    )

    plan = resolver.plan(tmp_path / "profile")

    with pytest.raises(ResolutionError, match="project"):
        resolver.preflight(plan)


def test_unowned_native_asset_requires_explicit_replacement(tmp_path: Path) -> None:
    home = tmp_path / "home"
    native = home / ".codex/skills/reviewer"
    native.mkdir(parents=True)
    (native / "SKILL.md").write_text(SKILL + "Native drift.\n", encoding="utf-8")
    desired = tmp_path / "profile/codex/user/skills/reviewer"
    desired.mkdir(parents=True)
    (desired / "SKILL.md").write_text(SKILL, encoding="utf-8")
    resolver = resolver_for("codex", home=home, state_root=tmp_path / "control")

    plan = resolver.plan(tmp_path / "profile")

    with pytest.raises(ResolutionError, match="unmanaged"):
        resolver.preflight(plan)
    assert (native / "SKILL.md").read_text(encoding="utf-8").endswith(
        "Native drift.\n"
    )


@pytest.mark.parametrize(
    ("agent", "destination"),
    [
        ("codex", ".agents/skills/reviewer/SKILL.md"),
        ("claude", ".claude/skills/reviewer/SKILL.md"),
        ("kimi", ".kimi-code/skills/reviewer/SKILL.md"),
        ("pi", ".pi/skills/reviewer/SKILL.md"),
    ],
)
def test_each_agent_owns_project_skill_destination(
    agent: str, destination: str, tmp_path: Path
) -> None:
    profile = tmp_path / "profile"
    desired = profile / agent / "project/skills/reviewer"
    desired.mkdir(parents=True)
    (desired / "SKILL.md").write_text(SKILL, encoding="utf-8")
    project = tmp_path / "project"
    resolver = resolver_for(
        agent,
        home=tmp_path / "home",
        project_root=project,
        state_root=tmp_path / "control",
    )

    plan = resolver.plan(profile)
    resolver.preflight(plan)
    result = resolver.materialize(plan)

    assert result.verified
    assert (project / destination).read_text(encoding="utf-8") == SKILL
