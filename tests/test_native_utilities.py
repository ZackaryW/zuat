from pathlib import Path

import pytest

from zuat.gitcore import GitRegistry
from zuat.specs.native import AssetFile
from zuat.utils.documents import add_fragment, contains_fragment, remove_fragment
from zuat.utils.mutation import replace_tree
from zuat.utils.ownership import OwnershipRecord, OwnershipStore


def test_control_state_is_beneath_git_directory_and_never_tracked(tmp_path: Path) -> None:
    with GitRegistry(tmp_path / "registry") as registry:
        store = OwnershipStore(registry.control_root / "native", "codex")
        store.save(
            OwnershipRecord(
                "codex", "skill", "reviewer", "user", "native", "fingerprint"
            )
        )

        assert registry.control_root.is_relative_to(Path(registry.repo.git_dir))
        receipt = next((registry.control_root / "native").rglob("*.json"))
        tracked = set(registry.repo.git.ls_files().splitlines())
        relative_receipt = receipt.relative_to(registry.root).as_posix()
        assert relative_receipt not in tracked
        before = receipt.read_bytes()
        registry.create_profile("work")
        assert receipt.read_bytes() == before


def test_replace_tree_rolls_back_when_replacement_validation_fails(tmp_path: Path) -> None:
    destination = tmp_path / "asset"
    destination.mkdir()
    (destination / "old.txt").write_text("old", encoding="utf-8")

    with pytest.raises(Exception):
        replace_tree(
            destination,
            (
                AssetFile("new.txt", b"new"),
                AssetFile("../escape.txt", b"unsafe"),
            ),
        )

    assert (destination / "old.txt").read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "escape.txt").exists()


def test_fragment_reconciliation_preserves_unrelated_settings() -> None:
    document = {"model": "kept", "hooks": {"Start": [{"command": "existing"}]}}
    fragment = {"Stop": [{"hooks": [{"type": "command", "command": "echo ok"}]}]}

    installed = add_fragment(document, fragment)
    removed = remove_fragment(installed, fragment)

    assert contains_fragment(installed, fragment)
    assert removed == document
