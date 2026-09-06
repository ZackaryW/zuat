import json
from pathlib import Path
from tempfile import TemporaryDirectory

from behave import given, then, when

from zuat.gitcore import GitRegistry, OperationKind, OperationOutcome
from zuat.pub import AssetInput, AssetSelector, OperationStatus, Zuat, ZuatRequest
from zuat.specs.registry import resolver_for


AGENTS = ("codex", "claude", "kimi", "pi")
DESTINATIONS = {
    "codex": ".codex/skills",
    "claude": ".claude/skills",
    "kimi": ".kimi-code/skills",
    "pi": ".pi/agent/skills",
}


class EmptyPlugins:
    def discover(self):
        return ()


def skill(version: str) -> str:
    return f"""---
name: reviewer
description: Review changes
---
Review {version}.
"""


def start(context, agents=AGENTS) -> tuple[Path, Path, Path]:
    context.temporary = TemporaryDirectory()
    root = Path(context.temporary.name)
    home = root / "home"
    project = root / "project"
    context.registry = GitRegistry(root / "registry")
    resolvers = {
        agent: resolver_for(
            agent,
            home=home,
            project_root=project,
            state_root=context.registry.control_root / "native",
            plugins=EmptyPlugins(),
        )
        for agent in agents
    }
    context.service = Zuat(registry=context.registry, resolvers=resolvers)
    context.home = home
    context.project = project
    return root, home, project


def native_skill(context, agent: str) -> Path:
    return context.home / DESTINATIONS[agent] / "reviewer/SKILL.md"


@given("an isolated Claude home with an existing skill and two shared hooks")
def isolated_claude(context) -> None:
    _, home, _ = start(context, ("claude",))
    reviewer = home / ".claude/skills/reviewer"
    reviewer.mkdir(parents=True)
    (reviewer / "SKILL.md").write_text(skill("one"), encoding="utf-8")
    settings = home / ".claude/settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(
        json.dumps(
            {
                "model": "unrelated-model",
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "first"}]},
                        {"hooks": [{"type": "command", "command": "neighbor"}]},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    context.claude_settings = settings


@when("I observe and adopt the existing Claude skill and first hook")
def adopt_claude(context) -> None:
    observed = context.service.status(ZuatRequest(agents=("claude",)))
    assert observed.status is OperationStatus.SUCCESS
    context.claude_hook_ref = next(
        item.ref
        for item in observed.assets
        if item.ref.kind == "hook" and item.ref.locator == "hooks/SessionStart/0"
    )
    selected = tuple(
        item.ref.id
        for item in observed.assets
        if item.ref.kind == "skill" or item.ref.id == context.claude_hook_ref.id
    )
    adopted = context.service.install(
        ZuatRequest(agents=("claude",), asset_refs=selected)
    )
    assert adopted.status is OperationStatus.SUCCESS
    context.adopt_operation = adopted.operation_id


@when("the adopted Claude hook drifts outside Zuat")
def drift_claude_hook(context) -> None:
    document = json.loads(context.claude_settings.read_text(encoding="utf-8"))
    document["hooks"]["SessionStart"][0]["hooks"][0]["command"] = "external"
    context.claude_settings.write_text(json.dumps(document), encoding="utf-8")


@when("I force the adopted Claude hook back to its desired content")
def force_claude_hook(context) -> None:
    source = Path(context.temporary.name) / "desired-hook.json"
    source.write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"type": "command", "command": "first"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    forced = context.service.install(
        ZuatRequest(
            agents=("claude",),
            assets=(
                AssetInput(
                    agent="claude",
                    kind="hook",
                    name="SessionStart-000",
                    locator=context.claude_hook_ref.locator,
                    source=str(source),
                ),
            ),
            force=True,
        )
    )
    assert forced.status is OperationStatus.SUCCESS
    context.force_operation = forced.operation_id


@when("I uninstall that Claude hook by its stable reference")
def uninstall_claude_hook(context) -> None:
    removed = context.service.uninstall(
        ZuatRequest(
            agents=("claude",), asset_refs=(context.claude_hook_ref.id,)
        )
    )
    assert removed.status is OperationStatus.SUCCESS, removed.to_dict()
    context.uninstall_operation = removed.operation_id


@then("the unrelated Claude hook and setting remain unchanged")
def verify_claude_neighbors(context) -> None:
    document = json.loads(context.claude_settings.read_text(encoding="utf-8"))
    assert document["model"] == "unrelated-model"
    assert document["hooks"]["SessionStart"] == [
        {"hooks": [{"type": "command", "command": "neighbor"}]}
    ]


@then("the Claude lifecycle operations appear in causal journal order")
def verify_claude_history(context) -> None:
    events = {item.operation_id: item for item in context.registry.history()}
    adopted = events[context.adopt_operation]
    forced = events[context.force_operation]
    removed = events[context.uninstall_operation]
    assert adopted.kind is OperationKind.INSTALL
    assert forced.kind is OperationKind.INSTALL
    assert forced.forced
    assert removed.kind is OperationKind.UNINSTALL
    assert adopted.sequence < forced.sequence < removed.sequence
    assert all(
        item.outcome is OperationOutcome.SUCCESS for item in (adopted, forced, removed)
    )


@given("an isolated Codex home with a version one skill and two named profiles")
def isolated_codex_profiles(context) -> None:
    _, home, _ = start(context, ("codex",))
    reviewer = home / ".codex/skills/reviewer"
    reviewer.mkdir(parents=True)
    (reviewer / "SKILL.md").write_text(skill("one"), encoding="utf-8")
    observed = context.service.status(ZuatRequest(agents=("codex",)))
    context.codex_ref = next(item.ref for item in observed.assets)
    assert context.service.install(
        ZuatRequest(agents=("codex",), asset_refs=(context.codex_ref.id,))
    ).ok
    assert context.service.create_profile(
        ZuatRequest(agents=("codex",), profile="work")
    ).ok


@when("the work profile is configured with version two of the skill")
def configure_work(context) -> None:
    assert context.service.switch_profile(
        ZuatRequest(agents=("codex",), profile="work")
    ).ok
    source = Path(context.temporary.name) / "reviewer-v2"
    source.mkdir()
    (source / "SKILL.md").write_text(skill("two"), encoding="utf-8")
    updated = context.service.install(
        ZuatRequest(
            agents=("codex",),
            assets=(
                AssetInput(
                    agent="codex",
                    kind="skill",
                    name="reviewer",
                    locator=context.codex_ref.locator,
                    source=str(source),
                ),
            ),
        )
    )
    assert updated.ok
    assert context.service.switch_profile(
        ZuatRequest(agents=("codex",), profile="default")
    ).ok


@when("native Codex drifts while the default profile is selected")
def drift_codex(context) -> None:
    native_skill(context, "codex").write_text(skill("drift"), encoding="utf-8")


@then("an unforced switch to work is rejected without selecting it")
def reject_unforced_switch(context) -> None:
    rejected = context.service.switch_profile(
        ZuatRequest(agents=("codex",), profile="work")
    )
    assert rejected.status is OperationStatus.FAILED
    assert context.registry.projected_state().selected_profile == "default"
    assert native_skill(context, "codex").read_text(encoding="utf-8") == skill(
        "drift"
    )


@when("I force the switch to work and revert that operation")
def force_and_revert_switch(context) -> None:
    forced = context.service.switch_profile(
        ZuatRequest(agents=("codex",), profile="work", force=True)
    )
    assert forced.ok
    context.forced_switch = forced.operation_id
    reverted = context.service.revert(
        ZuatRequest(agents=("codex",), operation_id=forced.operation_id)
    )
    assert reverted.ok
    context.revert_operation = reverted.operation_id


@then("the default profile and version one native skill are restored")
def verify_profile_revert(context) -> None:
    assert context.registry.projected_state().selected_profile == "default"
    assert native_skill(context, "codex").read_text(encoding="utf-8") == skill("one")


@then("the revert is a new operation that references the forced switch")
def verify_forward_revert(context) -> None:
    reverted = context.registry.event(context.revert_operation)
    forced = context.registry.event(context.forced_switch)
    assert reverted.kind is OperationKind.REVERT
    assert reverted.reverts == forced.operation_id
    assert reverted.sequence > forced.sequence


@given("isolated native homes contain the same skill for every supported agent")
def isolated_all_agents(context) -> None:
    _, home, _ = start(context)
    for agent in AGENTS:
        reviewer = home / DESTINATIONS[agent] / "reviewer"
        reviewer.mkdir(parents=True)
        (reviewer / "SKILL.md").write_text(skill("shared"), encoding="utf-8")


@when("I observe and adopt that skill for every supported agent")
def adopt_all_agents(context) -> None:
    observed = context.service.status(ZuatRequest(agents=AGENTS))
    assert observed.status is OperationStatus.SUCCESS
    assert observed.completeness == "complete"
    context.refs = {
        item.ref.agent: item.ref for item in observed.assets if item.ref.kind == "skill"
    }
    adopted = context.service.install(
        ZuatRequest(
            agents=AGENTS,
            asset_refs=tuple(context.refs[agent].id for agent in AGENTS),
        )
    )
    assert adopted.ok
    context.agent_outcomes = {
        item.agent: item.state for item in adopted.materializations
    }


@when("I uninstall only the Codex asset by its stable reference")
def uninstall_only_codex(context) -> None:
    removed = context.service.uninstall(
        ZuatRequest(
            agents=("codex",), asset_refs=(context.refs["codex"].id,)
        )
    )
    assert removed.ok


@then("each agent has an independent stable asset identity")
def verify_independent_refs(context) -> None:
    assert {context.refs[agent].agent for agent in AGENTS} == set(AGENTS)
    assert len({context.refs[agent].id for agent in AGENTS}) == len(AGENTS)


@then("only Codex native state changed while every agent reported its own outcome")
def verify_isolated_mutation(context) -> None:
    assert not native_skill(context, "codex").exists()
    for agent in ("claude", "kimi", "pi"):
        assert native_skill(context, agent).read_text(encoding="utf-8") == skill(
            "shared"
        )
    assert context.agent_outcomes == {agent: "converged" for agent in AGENTS}


@given("an isolated Codex skill is archived before an interrupted deletion")
def archived_interrupted_codex(context) -> None:
    _, home, _ = start(context, ("codex",))
    reviewer = home / ".codex/skills/reviewer"
    reviewer.mkdir(parents=True)
    native = reviewer / "SKILL.md"
    native.write_text(skill("interrupted"), encoding="utf-8")
    evidence = context.service.status(ZuatRequest(agents=("codex",))).assets[0]
    normalized = str(evidence.evidence["normalized_path"])
    context.registry.archive_asset(
        evidence.ref,
        normalized,
        context.registry.observation_root / normalized,
        str(evidence.fingerprint),
    )
    context.registry.begin_operation(
        OperationKind.UNINSTALL,
        profile="default",
        before=(evidence,),
    )
    native.unlink()
    reviewer.rmdir()
    context.interrupted_evidence = evidence


@when("I reopen the registry and restore all skills from the interruption")
def reopen_and_restore_interrupted(context) -> None:
    root = context.registry.root
    context.registry.close()
    context.registry = GitRegistry(root)
    resolver = resolver_for(
        "codex",
        home=context.home,
        project_root=context.project,
        state_root=context.registry.control_root / "native",
        plugins=EmptyPlugins(),
    )
    context.service = Zuat(
        registry=context.registry,
        resolvers={"codex": resolver},
    )
    context.interruption = next(
        event
        for event in reversed(context.registry.history())
        if event.kind is OperationKind.RECOVERY
    )
    context.restored = context.service.restore_all(
        context.interruption.operation_id,
        AssetSelector(agent="codex", kind="skill"),
    )


@then("the Codex skill and its unauthoritative state are restored")
def verify_interrupted_content(context) -> None:
    assert context.restored.ok, context.restored.to_dict()
    assert native_skill(context, "codex").read_text(encoding="utf-8") == skill(
        "interrupted"
    )
    evidence = context.service.list_assets(
        AssetSelector(agent="codex", kind="skill")
    ).assets[0]
    assert evidence.fingerprint == context.interrupted_evidence.fingerprint
    assert evidence.authority.value == "unauthoritative"


@then("the recovery is appended after the interrupted operation evidence")
def verify_interrupted_history(context) -> None:
    restored = context.registry.event(context.restored.operation_id)
    assert context.interruption.outcome is OperationOutcome.INDETERMINATE
    assert restored.kind is OperationKind.RESTORE
    assert restored.metadata["restores"] == context.interruption.operation_id
    assert restored.sequence > context.interruption.sequence
