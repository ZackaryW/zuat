from copy import deepcopy

import pytest

from zuat.utils.documents import contains_fragment


@pytest.mark.parametrize("current", [
    {}, {"other": [1]}, {"start": None}, {"start": "invalid"},
    {"start": [1]}, {"start": [1], "stop": "invalid"},
])
def test_mapping_containment_requires_every_key_and_list(current):
    document = {"events": current}
    wanted = {"start": [1], "stop": [2]}
    before = deepcopy(document)
    assert not contains_fragment(document, wanted, key="events")
    assert document == before


def test_mapping_containment_accepts_complete_subset_without_mutation():
    document = {"events": {"start": [0, 1], "stop": [2], "other": [3]}}
    before = deepcopy(document)
    assert contains_fragment(document, {"start": [1], "stop": [2]}, key="events")
    assert not contains_fragment(document, {"start": "invalid"}, key="events")
    assert document == before
