from pathlib import Path

from zuat.gitcore import GitRegistry, OperationKind, OperationOutcome


def test_private_registry_initializes_an_isolated_linear_journal(
    tmp_path: Path,
) -> None:
    project_git = Path.cwd() / ".git"
    before = project_git.stat().st_mtime_ns

    with GitRegistry(tmp_path / "registry") as registry:
        assert registry.root == (tmp_path / "registry").resolve()
        assert registry.projected_state().selected_profile == "default"
        assert [profile.name for profile in registry.profiles()] == ["default"]
        assert registry.history() == ()
        assert not registry.repo.bare

    assert project_git.stat().st_mtime_ns == before


def test_events_append_in_one_domain_order_without_exposing_git_identity(
    tmp_path: Path,
) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        initial_commit_count = sum(1 for _ in registry.repo.iter_commits())
        first = registry.append_event(
            OperationKind.INSTALL,
            OperationOutcome.SUCCESS,
            profile="default",
        )
        second = registry.append_event(
            OperationKind.UNINSTALL,
            OperationOutcome.REJECTED,
            profile="default",
            diagnostics=("force required",),
        )

        assert [event.operation_id for event in registry.history()] == [
            first.operation_id,
            second.operation_id,
        ]
        assert [event.sequence for event in registry.history()] == [1, 2]
        assert sum(1 for _ in registry.repo.iter_commits()) == initial_commit_count + 2
        assert registry.repo.head.commit.author.name == "Zuat"
        assert registry.repo.head.commit.author.email == "zuat@local.invalid"
        for event in registry.history():
            assert not (
                {"revision", "commit", "branch", "tree", "index"}
                & set(event.to_dict())
            )
