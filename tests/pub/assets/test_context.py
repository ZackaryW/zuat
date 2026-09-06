import json

import pytest

from zuat.pub import AssetInput, AssetSelector, Zuat, ZuatRequest
from zuat.specs.claude import ClaudeResolver


class EmptyPlugins:
    def discover(self):
        return ()


SKILL = "---\nname: reviewer\ndescription: Review\n---\nReview A.\n"
HOOK = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo A"}]}]}}


def service(tmp_path, project, plugins=None):
    root = tmp_path / "registry"
    home = tmp_path / "home"
    return Zuat(
        root=root,
        home=home,
        project_root=project,
        resolvers={
            "claude": ClaudeResolver(
                home=home,
                project_root=project,
                state_root=root / ".git/zuat/native",
                plugins=plugins or EmptyPlugins(),
            )
        },
    )


def native_assets(root):
    skill = root / ".claude/skills/reviewer/SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(SKILL, encoding="utf-8")
    (root / ".claude/settings.json").write_text(json.dumps(HOOK), encoding="utf-8")


def test_observation_separates_project_payloads_and_retains_other_context(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    for root in (a, b, tmp_path / "home"):
        native_assets(root)
    with service(tmp_path, a) as first:
        observed_a = first.status(ZuatRequest(agents=("claude",))).assets
    with service(tmp_path, b) as second:
        observed_b = second.status(ZuatRequest(agents=("claude",))).assets
        project_a = {item.ref.id for item in observed_a if item.ref.scope == "project"}
        project_b = {item.ref.id for item in observed_b if item.ref.scope == "project"}
        assert project_a.isdisjoint(project_b)
        assert project_a | project_b <= {
            item.ref.id for item in second.registry.latest_observation()
        }
        for item in (*observed_a, *observed_b):
            assert (
                second.registry.observation_root / item.evidence["normalized_path"]
            ).exists()
        assert {item.ref.id for item in observed_a if item.ref.scope == "user"} == {
            item.ref.id for item in observed_b if item.ref.scope == "user"
        }
    with service(tmp_path, a / ".." / "a") as reopened:
        assert {
            item.ref.id
            for item in reopened.status(ZuatRequest(agents=("claude",))).assets
        } == {item.ref.id for item in observed_a}


@pytest.mark.parametrize("kind", ["skill", "hook"])
def test_install_ownership_and_removal_are_project_local(tmp_path, kind):
    source = tmp_path / ("reviewer" if kind == "skill" else "reviewer.json")
    if kind == "skill":
        source.mkdir()
        (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    else:
        source.write_text(json.dumps(HOOK), encoding="utf-8")
    refs = []
    for project in (tmp_path / "a", tmp_path / "b"):
        with service(tmp_path, project) as current:
            result = current.install(
                ZuatRequest(
                    agents=("claude",),
                    assets=(
                        AssetInput(
                            "claude",
                            kind,
                            scope="project",
                            name="reviewer",
                            source=str(source),
                        ),
                    ),
                )
            )
            assert result.ok, result.diagnostics
            refs.append(result.assets[0].ref.id)
    assert refs[0] != refs[1]
    with service(tmp_path, tmp_path / "a") as current:
        result = current.uninstall(
            ZuatRequest(agents=("claude",), asset_refs=(refs[0],))
        )
        assert result.ok, result.diagnostics
    b = tmp_path / "b/.claude"
    if kind == "skill":
        assert (b / "skills/reviewer/SKILL.md").read_text(encoding="utf-8") == SKILL
    else:
        assert json.loads((b / "settings.json").read_text(encoding="utf-8")) == HOOK


def install_skill(current, tmp_path):
    source = tmp_path / "package/reviewer"
    source.mkdir(parents=True, exist_ok=True)
    (source / "SKILL.md").write_text(SKILL, encoding="utf-8")
    result = current.install(
        ZuatRequest(
            agents=("claude",),
            assets=(
                AssetInput(
                    "claude",
                    "skill",
                    scope="project",
                    name="reviewer",
                    source=str(source),
                ),
            ),
        )
    )
    assert result.ok, result.diagnostics
    return result


@pytest.mark.parametrize("project", ["b", None])
def test_foreign_revert_rejects_before_native_changes(tmp_path, project):
    with service(tmp_path, tmp_path / "a") as first:
        installed = install_skill(first, tmp_path)
    with service(tmp_path, tmp_path / project if project else None) as other:
        before = other.registry.history()
        result = other.revert(
            ZuatRequest(
                agents=("claude",), operation_id=installed.operation_id, force=True
            )
        )
        assert not result.ok
        assert other.registry.history() == before
        assert (tmp_path / "a/.claude/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL


def test_empty_project_and_incomplete_inventory_retain_registered_other_project(
    tmp_path,
):
    with service(tmp_path, tmp_path / "a") as first:
        installed = install_skill(first, tmp_path)
    with service(tmp_path, tmp_path / "b") as other:
        result = other.list_assets(AssetSelector("claude", scope="project"))
        assert result.ok and not result.assets
        retained = {item.ref.id: item for item in other.registry.latest_observation()}
        assert retained[installed.assets[0].ref.id].present


def test_mixed_profile_preserves_other_project_and_reports_coverage(tmp_path):
    with service(tmp_path, tmp_path / "a") as first:
        a = install_skill(first, tmp_path)
    with service(tmp_path, tmp_path / "b") as second:
        b = install_skill(second, tmp_path)
    with service(tmp_path, tmp_path / "a") as first:
        result = first.switch_profile(
            ZuatRequest(agents=("claude",), profile="default")
        )
        assert result.ok, result.diagnostics
        assert set(first.registry.projected_state().profile("default").assets) == {
            a.assets[0].ref.id,
            b.assets[0].ref.id,
        }
        assert result.data["coverage"]["excluded_asset_refs"] == (b.assets[0].ref.id,)
        assert (tmp_path / "b/.claude/skills/reviewer/SKILL.md").read_text(
            encoding="utf-8"
        ) == SKILL


def test_context_free_ordinary_project_state_rejected_without_history_mutation(
    tmp_path,
):
    with service(tmp_path, tmp_path / "a") as current:
        current.registry.ensure_asset_ref(
            agent="claude", kind="skill", scope="project", locator="skills/old"
        )
        before = current.registry.history()
        result = current.status(ZuatRequest(agents=("claude",)))
        assert not result.ok
        assert any("fresh registry" in message for message in result.diagnostics)
        assert current.registry.history() == before


def test_context_free_profile_payload_cannot_be_silently_ignored(tmp_path):
    with service(tmp_path, tmp_path / "a") as current:
        payload = (
            current.registry.profile_root() / "claude/project/skills/reviewer/SKILL.md"
        )
        payload.parent.mkdir(parents=True)
        payload.write_text(SKILL, encoding="utf-8")
        result = current.switch_profile(
            ZuatRequest(agents=("claude",), profile="default")
        )
        assert not result.ok
        assert any("fresh registry" in message for message in result.diagnostics)
        assert payload.read_text(encoding="utf-8") == SKILL


def test_context_bound_hook_sidecar_cannot_target_another_project(tmp_path):
    with service(tmp_path, tmp_path / "a") as current:
        from zuat.utils.contexts import project_context, scope_path

        target = (
            current.registry.profile_root()
            / "claude"
            / scope_path("project", project_context(tmp_path / "a"))
            / "hooks/reviewer.json"
        )
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps(HOOK), encoding="utf-8")
        target.with_name(target.name + ".zuat.json").write_text(
            json.dumps(
                {
                    "scope": "project",
                    "native_locator": f"contexts/{project_context(tmp_path / 'b')}/hooks/reviewer",
                }
            ),
            encoding="utf-8",
        )
        result = current.switch_profile(
            ZuatRequest(agents=("claude",), profile="default", force=True)
        )
        assert not result.ok
        assert not (tmp_path / "a/.claude/settings.json").exists()


def test_other_project_does_not_infer_absence_without_prior_broad_observation(tmp_path):
    from tests.pub.assets.test_inspection import source_asset

    native_assets(tmp_path / "a")
    asset = source_asset(tmp_path)
    with service(tmp_path, tmp_path / "a") as first:
        updated = first.update_asset(asset, force=True)
        assert updated.ok
    with service(tmp_path, tmp_path / "b") as other:
        observed = other.status(ZuatRequest(agents=("claude",)))
        assert observed.ok
        assert updated.assets[0].ref.id not in {item.ref.id for item in observed.assets}
