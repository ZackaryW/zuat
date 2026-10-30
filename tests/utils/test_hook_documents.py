"""Pin the event-fragment hook document shape behind its resolver-selected seam."""

import pytest

from zuat.specs.interface import ResolutionError
from zuat.utils.hook_documents import FragmentHookDocument


START = {"matcher": "startup", "hooks": [{"type": "command", "command": "a"}]}
COMPACT = {"matcher": "compact", "hooks": [{"type": "command", "command": "b"}]}
STOP = {"hooks": [{"type": "command", "command": "c"}]}
MAPPING = {"hooks": {"SessionStart": [START, COMPACT], "Stop": [STOP]}, "unrelated": True}
LISTED = {"hooks": [{"event": "Stop", "command": "x"}, {"event": "Session Start", "command": "y"}]}


def test_mapping_entries_are_single_event_fragments_with_positional_locators():
    entries, rejected = FragmentHookDocument().entries(MAPPING)

    assert rejected == []
    assert entries == [
        ("SessionStart-000", {"SessionStart": [START]}, "hooks/SessionStart/0"),
        ("SessionStart-001", {"SessionStart": [COMPACT]}, "hooks/SessionStart/1"),
        ("Stop-000", {"Stop": [STOP]}, "hooks/Stop/0"),
    ]


def test_list_entries_use_their_event_names_and_indexes():
    entries, rejected = FragmentHookDocument().entries(LISTED)

    assert rejected == []
    assert [(slug, locator) for slug, _, locator in entries] == [
        ("Stop-000", "hooks/0"),
        ("Session-Start-001", "hooks/1"),
    ]


@pytest.mark.parametrize(
    "document,message",
    [
        ({"hooks": {"Stop": "nope"}}, "hooks: native hooks mapping has an unsupported shape"),
        ({"hooks": {"Stop": ["nope"]}}, "hooks: Stop/0 is not an object"),
        ({"hooks": ["nope"]}, "hooks: 0 is not an object"),
        ({"hooks": "nope"}, "hooks: native hooks value has an unsupported shape"),
    ],
)
def test_malformed_entries_are_rejected_without_guessing(document, message):
    entries, rejected = FragmentHookDocument().entries(document)

    assert entries == []
    assert rejected == [message]


def test_absent_hooks_have_no_entries():
    assert FragmentHookDocument().entries({"unrelated": 1}) == ([], [])


@pytest.mark.parametrize(
    "locator,expected",
    [("hooks/Stop/0", "hooks/Stop/0"), ("hooks/3", "hooks/3"), ("hooks/powerspec", None), (None, None)],
)
def test_only_indexed_locators_are_positional(locator, expected):
    assert FragmentHookDocument().positional(locator) == expected


def test_select_resolves_a_complete_group_and_rejects_ambiguity():
    shape = FragmentHookDocument()

    assert shape.select(MAPPING, {"SessionStart": [START, COMPACT]}) == {
        "SessionStart": [START, COMPACT]
    }
    assert shape.select(MAPPING, {"PreToolUse": [STOP]}) is None
    with pytest.raises(ResolutionError):
        shape.select({"hooks": {"SessionStart": [START, START]}}, {"SessionStart": [START]})


def test_remove_and_replace_at_locator_keep_neighbors():
    shape = FragmentHookDocument()

    removed = shape.remove_at(MAPPING, "hooks/SessionStart/0")
    replaced = shape.replace_at(MAPPING, "hooks/Stop/0", {"Stop": [START]})

    assert removed["hooks"] == {"SessionStart": [COMPACT], "Stop": [STOP]}
    assert replaced["hooks"]["Stop"] == [START]
    assert MAPPING["hooks"]["SessionStart"] == [START, COMPACT]
