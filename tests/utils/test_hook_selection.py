from copy import deepcopy

import pytest

from zuat.specs.interface import ResolutionError
from zuat.utils.inspection import selected_fragment


def group(mapping, *commands):
    entries = [{"event": "Start", "command": command} for command in commands]
    return {"Start": entries} if mapping else entries


@pytest.mark.parametrize("mapping", [True, False])
def test_selection_requires_complete_group(mapping):
    with pytest.raises(ResolutionError, match="partial|incomplete|ambiguous"):
        selected_fragment({"hooks": group(mapping, "one")}, group(mapping, "one", "two"))


@pytest.mark.parametrize("mapping", [True, False])
def test_selection_preserves_native_order_and_inputs(mapping):
    document = {"hooks": group(mapping, "neighbor", "two", "one")}
    wanted = group(mapping, "one", "two")
    original = deepcopy((document, wanted))
    for _ in range(2):
        assert selected_fragment(document, wanted) == group(mapping, "two", "one")
        assert (document, wanted) == original


@pytest.mark.parametrize("mapping", [True, False])
def test_selection_rejects_duplicate_and_missing_members(mapping):
    with pytest.raises(ResolutionError, match="ambiguous"):
        selected_fragment({"hooks": group(mapping, "one", "one")}, group(mapping, "one"))
    with pytest.raises(ResolutionError, match="partial|incomplete|ambiguous"):
        selected_fragment({"hooks": group(mapping, "one", "other")}, group(mapping, "one", "two"))
    assert selected_fragment({}, group(mapping, "one", "two")) is None


@pytest.mark.parametrize("fragment", [{"Start": ["bad"]}, ["bad"], {"Start": "bad"}])
def test_selection_rejects_malformed_shapes(fragment):
    with pytest.raises(ResolutionError):
        selected_fragment({"hooks": fragment}, fragment)


def test_partial_group_across_events_is_not_a_complete_target():
    with pytest.raises(ResolutionError, match="partial|incomplete|ambiguous"):
        selected_fragment(
            {"hooks": {"Start": [{"command": "one"}]}},
            {"Start": [{"command": "one"}], "Stop": [{"command": "two"}]},
        )


def test_duplicate_requested_members_do_not_establish_absence():
    with pytest.raises(ResolutionError, match="ambiguous"):
        selected_fragment({}, group(True, "one", "one"))


@pytest.mark.parametrize("mapping", [True, False])
def test_exact_group_reports_complete_partial_absent_and_ambiguous(mapping):
    from zuat.utils.inspection import exact_group
    wanted = group(mapping, "one", "two")
    assert exact_group({}, wanted).status == "absent"
    assert exact_group({"hooks": group(mapping, "one")}, wanted).status == "partial"
    assert exact_group({"hooks": group(mapping, "other")}, wanted).status == "ambiguous"
    result = exact_group({"hooks": group(mapping, "neighbor", "two", "one")}, wanted)
    assert result.status == "complete" and result.positions == (1, 2)
    assert result.fragment == group(mapping, "two", "one")
