from pathlib import Path

import pytest

from zuat.gitcore import (
    GitRegistry,
    InvalidRegistryPathError,
    OperationKind,
    OperationOutcome,
    RegistryLockedError,
)


def test_second_registry_cannot_interleave_a_domain_transaction(
    tmp_path: Path,
) -> None:
    with GitRegistry(tmp_path / "registry") as first:
        with first.operation():
            with GitRegistry(first.root) as second:
                with pytest.raises(RegistryLockedError):
                    with second.operation():
                        second.append_event(
                            OperationKind.INSTALL, OperationOutcome.SUCCESS
                        )
        assert first.history() == ()


@pytest.mark.parametrize(
    "locator",
    ("../escape", "/absolute/path", r"C:\absolute\path", "skills/../escape"),
)
def test_hostile_native_locators_are_rejected_before_state_changes(
    tmp_path: Path, locator: str
) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        before = registry.projected_state()
        with pytest.raises(InvalidRegistryPathError):
            registry.ensure_asset_ref(
                agent="codex", kind="skill", scope="user", locator=locator
            )
        assert registry.projected_state() == before
        assert registry.history() == ()
