"""Keyed hook documents: one top-level entry per hook name, identity by name."""

import json

import pytest

from zuat.specs.interface import ResolutionError
from zuat.specs.native import Agent, InvalidAssetError
from zuat.utils.assets import load_keyed_json_hook
from zuat.utils.documents import add_keyed, contains_keyed, read_keyed_json, remove_keyed
from zuat.utils.hook_documents import KeyedHookDocument


ENTRY = {"SessionStart": [{"type": "command", "command": "pspec resolve hook", "timeout": 5}]}
OTHER = {"PostToolUse": [{"matcher": "run_command", "hooks": [{"command": "./lint.sh"}]}]}
DOC = {"other": OTHER, "powerspec": ENTRY}


def test_group_selects_the_entry_at_the_hook_name():
    shape = KeyedHookDocument()

    assert shape.group(DOC, {"powerspec": ENTRY}, None, (), None, "user") == {"powerspec": ENTRY}
    assert shape.select(DOC, {"powerspec": {"Stop": []}}) == {"powerspec": ENTRY}


def test_group_reports_an_absent_name_as_none():
    assert KeyedHookDocument().group({"other": OTHER}, {"powerspec": ENTRY}, None, (), None, "user") is None


def test_group_rejects_a_non_object_entry():
    with pytest.raises(ResolutionError):
        KeyedHookDocument().group({"powerspec": ["x"]}, {"powerspec": ENTRY}, None, (), None, "user")


def test_group_requires_a_single_named_fragment():
    with pytest.raises(ResolutionError):
        KeyedHookDocument().group(DOC, {"a": ENTRY, "b": ENTRY}, None, (), None, "user")


def test_entries_are_one_named_fragment_each():
    entries, rejected = KeyedHookDocument().entries({**DOC, "bad name": ENTRY, "broken": 3})

    assert entries == [
        ("other", {"other": OTHER}, "hooks/other"),
        ("powerspec", {"powerspec": ENTRY}, "hooks/powerspec"),
        ("bad-name", {"bad name": ENTRY}, "hooks/bad name"),
    ]
    assert rejected == ["hooks: broken is not an object"]


def test_named_entries_are_never_positional_or_regrouped():
    shape = KeyedHookDocument()

    assert shape.positional("hooks/3") is None
    assert shape.claim_owned(DOC, ()) == ([], set(), [])


def test_locator_edits_touch_only_the_named_entry():
    shape = KeyedHookDocument()

    assert shape.remove_at(DOC, "hooks/powerspec") == {"other": OTHER}
    assert shape.replace_at(DOC, "hooks/powerspec", {"powerspec": OTHER}) == {"other": OTHER, "powerspec": OTHER}
    assert DOC == {"other": OTHER, "powerspec": ENTRY}
    with pytest.raises(InvalidAssetError):
        shape.remove_at(DOC, "hooks/missing")


def test_containment_add_and_remove_preserve_neighbors():
    assert contains_keyed(DOC, {"powerspec": ENTRY})
    assert not contains_keyed(DOC, {"powerspec": OTHER})
    assert add_keyed({"other": OTHER}, {"powerspec": ENTRY}) == DOC
    assert add_keyed(DOC, {"powerspec": OTHER})["powerspec"] == OTHER
    assert remove_keyed(DOC, {"powerspec": ENTRY}) == {"other": OTHER}
    assert remove_keyed(DOC, {"powerspec": OTHER}) == DOC
    assert remove_keyed({"powerspec": ENTRY}, {"powerspec": ENTRY}) == {}


def test_strict_reader_rejects_duplicate_names_and_non_objects(tmp_path):
    path = tmp_path / "hooks.json"
    assert read_keyed_json(path) == {}

    path.write_text('{"powerspec": {}, "powerspec": {"Stop": []}}', encoding="utf-8")
    with pytest.raises(InvalidAssetError, match="duplicate"):
        read_keyed_json(path)

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(InvalidAssetError):
        read_keyed_json(path)

    path.write_text(json.dumps({"powerspec": {"a": {"x": 1, "x": 2}}}), encoding="utf-8")
    assert read_keyed_json(path) == {"powerspec": {"a": {"x": 2}}}


def test_source_loader_uses_the_stem_as_its_only_name(tmp_path):
    source = tmp_path / "powerspec.json"
    source.write_text(json.dumps({"powerspec": ENTRY}, indent=4), encoding="utf-8")
    compact = tmp_path / "compact" / "powerspec.json"
    compact.parent.mkdir()
    compact.write_text(json.dumps({"powerspec": ENTRY}, separators=(",", ":")), encoding="utf-8")

    loaded = load_keyed_json_hook(source, agent=Agent.CLAUDE)

    assert (loaded.name, loaded.fragment) == ("powerspec", {"powerspec": ENTRY})
    assert loaded.compatible_agents == frozenset({Agent.CLAUDE})
    assert loaded.fingerprint == load_keyed_json_hook(compact, agent=Agent.CLAUDE).fingerprint


@pytest.mark.parametrize(
    "filename,document",
    [
        ("other.json", {"powerspec": ENTRY}),
        ("powerspec.json", {"powerspec": ENTRY, "extra": ENTRY}),
        ("powerspec.json", {"powerspec": ["not", "an", "object"]}),
        ("powerspec.json", []),
        ("powerspec.toml", {"powerspec": ENTRY}),
    ],
)
def test_source_loader_rejects_identity_mismatches(tmp_path, filename, document):
    source = tmp_path / filename
    source.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(InvalidAssetError):
        load_keyed_json_hook(source, agent=Agent.CLAUDE)
