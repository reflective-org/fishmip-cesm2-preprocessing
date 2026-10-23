"""Guard rails on removing published objects."""

import pytest

from fishmip_cesm.withdraw import object_prefix


def test_a_scenario_becomes_its_own_prefix():
    assert object_prefix("g6-1p5k-mcb") == "fishmip/g6-1p5k-mcb/"


def test_the_trailing_slash_is_not_optional():
    # "fishmip/historical" without it also matches a hypothetical
    # "fishmip/historical-extra/", which would be deleted unasked.
    assert object_prefix("historical").endswith("/")


@pytest.mark.parametrize("scenario", ["", "   ", "/", "fishmip", "..", "*"])
def test_a_prefix_that_could_reach_too_far_is_refused(scenario):
    # Deleting is not reversible and the bucket is public. A prefix that
    # escapes one scenario could take the whole published set with it.
    with pytest.raises(ValueError):
        object_prefix(scenario)


def test_a_scenario_cannot_contain_a_separator():
    with pytest.raises(ValueError):
        object_prefix("g6-1p5k-mcb/../ssp245")
