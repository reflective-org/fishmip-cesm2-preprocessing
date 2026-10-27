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


def test_without_a_pattern_every_key_is_selected():
    from fishmip_cesm.withdraw import keys_to_remove

    keys = ["fishmip/ssp245/a_2015_2100.nc", "fishmip/ssp245/b_2035_2069.nc"]

    assert keys_to_remove(keys, None) == keys


def test_a_pattern_selects_only_the_superseded_window():
    # ssp245 now holds both windows under one prefix, so withdrawing the old
    # files by prefix would take the new ones with them.
    from fishmip_cesm.withdraw import keys_to_remove

    keys = [
        "fishmip/ssp245/cesm2-cam6_ssp245_001_intpp_onedeg_global_monthly_2015_2100.nc",
        "fishmip/ssp245/cesm2-cam6_ssp245_001_intpp_onedeg_global_monthly_2035_2069.nc",
    ]

    selected = keys_to_remove(keys, "*_2035_2069.nc")

    assert selected == [keys[1]]


def test_a_pattern_matching_nothing_selects_nothing():
    from fishmip_cesm.withdraw import keys_to_remove

    assert keys_to_remove(["fishmip/ssp245/a_2015_2100.nc"], "*_1999_2000.nc") == []
