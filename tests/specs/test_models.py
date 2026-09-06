from pathlib import Path

import pytest

from zuat.specs.native import (
    Agent,
    AssetFile,
    InvalidAssetError,
    PluginActivation,
    PluginRecord,
    PluginRef,
    Scope,
    SkillSource,
)


def test_native_contracts_are_zuat_owned_and_serializable(tmp_path: Path) -> None:
    source = tmp_path / "reviewer"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: reviewer\ndescription: Review changes\n---\nReview.\n",
        encoding="utf-8",
    )

    skill = SkillSource.from_path(source)
    ref = PluginRef(Agent.CODEX, "example@market", Scope.USER, "market")
    record = PluginRecord(
        ref,
        "example",
        True,
        PluginActivation.PARTIAL,
        native_evidence={"installed": True, "enabled": False},
    )

    assert skill.name == "reviewer"
    assert skill.files == (
        AssetFile("SKILL.md", (source / "SKILL.md").read_bytes()),
    )
    assert record.to_dict()["activation"] == "partial"
    assert record.to_dict()["ref"]["agent"] == "codex"


def test_skill_frontmatter_requires_semantic_yaml_name(tmp_path: Path) -> None:
    source = tmp_path / "invalid"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\ndescription: no name\n---\nMissing required metadata.\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidAssetError, match="name"):
        SkillSource.from_path(source)


def test_asset_collection_rejects_symbolic_links(tmp_path: Path) -> None:
    source = tmp_path / "skill"
    source.mkdir()
    (source / "SKILL.md").write_text(
        "---\nname: skill\ndescription: Safe\n---\nSafe.\n", encoding="utf-8"
    )
    target = tmp_path / "secret"
    target.write_text("secret", encoding="utf-8")
    try:
        (source / "leak").symlink_to(target)
    except OSError:
        pytest.skip("symbolic links are unavailable")

    with pytest.raises(InvalidAssetError, match="symbolic link"):
        SkillSource.from_path(source)
