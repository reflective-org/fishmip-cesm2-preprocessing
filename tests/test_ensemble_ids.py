import pytest

from fishmip_cesm.ensembles import ENSEMBLES
from fishmip_cesm.naming import object_key, output_filename


def _by_name(fragment: str):
    return next(e for e in ENSEMBLES if fragment.lower() in e.name.lower())


@pytest.mark.parametrize(
    "fragment, source_id, experiment_id",
    [
        ("WACCM baseline", "cesm2-waccm6", "ssp245"),
        ("SAI", "cesm2-waccm6", "g6-1p5k-sai"),
        ("CAM6 baseline", "cesm2-cam6", "ssp245"),
        ("MCB", "cesm2-cam6", "g6-1p5k-mcb"),
    ],
)
def test_each_ensemble_declares_publishable_identifiers(
    fragment, source_id, experiment_id
):
    # Filenames must not be built from display labels. "SSP2-4.5 (WACCM
    # baseline)" is a label for humans; publishing it as a scenario token gives
    # ssp2-4p5-waccm-baseline, which is not an experiment anyone can look up.
    ensemble = _by_name(fragment)

    assert ensemble.source_id == source_id
    assert ensemble.experiment_id == experiment_id


def test_the_two_baselines_share_a_scenario_and_differ_by_model():
    waccm = _by_name("WACCM baseline")
    cam6 = _by_name("CAM6 baseline")

    assert waccm.experiment_id == cam6.experiment_id
    assert waccm.source_id != cam6.source_id

    waccm_file = output_filename(
        model=waccm.source_id,
        scenario=waccm.experiment_id,
        member="001",
        variable="intpp",
        start_year=2035,
        end_year=2069,
    )
    cam6_file = output_filename(
        model=cam6.source_id,
        scenario=cam6.experiment_id,
        member="001",
        variable="intpp",
        start_year=2035,
        end_year=2069,
    )

    assert waccm_file != cam6_file
    assert waccm_file.startswith("cesm2-waccm6_ssp245_001_intpp_")
    assert object_key(scenario=waccm.experiment_id, filename=waccm_file) == (
        f"fishmip/ssp245/{waccm_file}"
    )
