import pytest

from fishmip_cesm.ensembles import ANALYSIS_WINDOW, ENSEMBLES, months_in
from fishmip_cesm.naming import output_filename, window_from_filename


def test_every_ensemble_declares_its_own_window():
    # Historical runs 1850-2014 and piControl is a long model-year control, so
    # a single global window cannot describe the set.
    for ensemble in ENSEMBLES:
        assert ensemble.window is not None


def test_the_scenario_ensembles_still_use_the_common_window():
    for ensemble in ENSEMBLES:
        if ensemble.experiment_id in ("ssp245", "g6-1p5k-sai", "g6-1p5k-mcb"):
            assert ensemble.window == ANALYSIS_WINDOW


@pytest.mark.parametrize(
    "window, expected",
    [
        (((2035, 1), (2069, 12)), 420),
        (((1850, 1), (2014, 12)), 1980),
        (((1, 1), (165, 12)), 1980),
    ],
)
def test_month_counts(window, expected):
    assert months_in(window) == expected


def test_a_filename_carries_its_own_window_back():
    # Verification has to know what to expect per file, and the filename is the
    # only thing a published file travels with.
    name = output_filename(
        model="cesm2-waccm6",
        scenario="historical",
        member="001",
        variable="intpp",
        start_year=1850,
        end_year=2014,
    )

    assert window_from_filename(name) == ((1850, 1), (2014, 12))


def test_a_name_without_a_window_returns_none():
    assert window_from_filename("cesm2_deptho_onedeg_global_fx.nc") is None
