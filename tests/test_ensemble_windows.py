import pytest

from fishmip_cesm.ensembles import (
    ANALYSIS_WINDOW,
    BASELINE_WINDOW,
    ENSEMBLES,
    HISTORICAL_WINDOW,
    months_in,
)
from fishmip_cesm.naming import output_filename, window_from_filename


def test_every_ensemble_declares_its_own_window():
    # Historical runs 1850-2014 and piControl is a long model-year control, so
    # a single global window cannot describe the set.
    for ensemble in ENSEMBLES:
        assert ensemble.window is not None


def test_the_srm_ensembles_use_the_common_window():
    # SAI and MCB only exist from 2035, so the comparison window is theirs.
    for ensemble in ENSEMBLES:
        if ensemble.experiment_id in ("g6-1p5k-sai", "g6-1p5k-mcb"):
            assert ensemble.window == ANALYSIS_WINDOW


def test_the_baseline_runs_from_the_start_of_the_scenario():
    # ssp245 is not an SRM run. Starting it at 2035 left a 20-year hole
    # between the end of historical and the start of the scenario, exactly
    # where the two are meant to join.
    baselines = [e for e in ENSEMBLES if e.experiment_id == "ssp245"]

    assert baselines
    for ensemble in baselines:
        assert ensemble.window == BASELINE_WINDOW
        assert ensemble.window[0] == (2015, 1)


def test_the_baseline_window_continues_the_historical_one():
    # No gap and no overlap: historical ends 2014-12, the baseline starts
    # 2015-01, so the two concatenate into one continuous record.
    (_, (last_year, last_month)) = HISTORICAL_WINDOW
    ((first_year, first_month), _) = BASELINE_WINDOW

    assert (first_year, first_month) == (last_year + 1, 1)
    assert last_month == 12


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


def test_the_large_ensemble_entry_is_variable_layout_and_pins_one_case():
    # Its archive is variable-first, and a looser glob would match several
    # members whose three-digit labels collide.
    le = next(e for e in ENSEMBLES if e.layout == "variable")

    assert le.experiment_id == "historical"
    assert le.source_id == "cesm2-cam6"
    assert "smbb" in le.case_glob
    assert "*" not in le.case_glob and "[" not in le.case_glob


def test_every_other_ensemble_is_case_layout():
    variable_layout = [e for e in ENSEMBLES if e.layout == "variable"]

    assert len(variable_layout) == 1
