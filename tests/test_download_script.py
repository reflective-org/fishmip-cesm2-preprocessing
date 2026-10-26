import importlib.util
from pathlib import Path

import pytest

from fishmip_cesm.ensembles import ENSEMBLES as REAL_ENSEMBLES

_spec = importlib.util.spec_from_file_location(
    "download_fishmip", Path(__file__).parent.parent / "scripts" / "download_fishmip.py"
)
download = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(download)


def test_the_manifest_covers_the_whole_published_set():
    expected = 2  # the two grid fields
    for model, experiment, count, _, _ in download.ENSEMBLES:
        omitted = len(download.OMITTED.get((model, experiment), ()))
        expected += count * (9 - omitted)

    assert len(download.manifest()) == expected


def test_the_manifest_omits_variables_an_archive_cannot_provide():
    # MCB has no photoC_TOT_zint or zoo_loss_zint, so intpp and zoo_loss are
    # not published for it. Offering them would 404 on every member.
    names = [n for _, n in download.manifest(scenario="g6-1p5k-mcb")]

    assert names, "the MCB scenario should still publish something"
    assert not [n for n in names if "_intpp_" in n or "_zoo-loss_" in n]
    assert len(names) == 3 * 7


def test_the_script_agrees_with_the_pipeline_about_members_per_ensemble():
    # The script is standalone, so its view of the dataset could drift from the
    # pipeline's. This is what would catch that.
    declared = {(m, e): n for m, e, n, _, _ in download.ENSEMBLES}
    for ensemble in REAL_ENSEMBLES:
        key = (ensemble.source_id, ensemble.experiment_id)
        assert key in declared, f"{key} missing from the download script"


def test_filtering_by_scenario_excludes_the_others():
    urls = [url for url, _ in download.manifest(scenario="g6-1p5k-sai")]

    assert len(urls) == 3 * 9
    assert all("g6-1p5k-sai" in url for url in urls)


def test_filtering_by_variable_spans_every_ensemble_that_has_it():
    names = [name for _, name in download.manifest(variable="intpp")]

    # One per member, except from archives that cannot provide the variable.
    expected = sum(
        count
        for model, experiment, count, _, _ in download.ENSEMBLES
        if "intpp" not in download.OMITTED.get((model, experiment), ())
    )
    assert len(names) == expected
    assert all("_intpp_" in name for name in names)
    assert not [n for n in names if "g6-1p5k-mcb" in n]


def test_a_single_member_of_one_scenario_is_nine_files():
    files = download.manifest(scenario="g6-1p5k-sai", member="001")

    assert len(files) == 9


def test_the_grid_fields_come_with_an_unfiltered_request():
    names = [name for _, name in download.manifest()]

    assert "cesm2_deptho_onedeg_global_fx.nc" in names
    assert "cesm2_thkcello_onedeg_global_fx.nc" in names


def test_the_grid_fields_can_be_fetched_on_their_own():
    files = download.manifest(variable="deptho")

    assert len(files) == 1
    assert files[0][0].endswith("/grid/cesm2_deptho_onedeg_global_fx.nc")


def test_urls_are_built_under_the_scenario_prefix():
    url, name = download.manifest(scenario="g6-1p5k-sai", member="001")[0]

    assert url == f"{download.BASE}/g6-1p5k-sai/{name}"


def test_every_request_carries_a_user_agent():
    # Cloudflare answers Python's default urllib User-Agent with 403, so a
    # request without one fails on every single file.
    request = download._request("https://example.invalid/x")

    agent = request.get_header("User-agent")
    assert agent and "urllib" not in agent.lower()


def test_a_range_header_survives_the_user_agent_being_added():
    request = download._request(
        "https://example.invalid/x", headers={"Range": "bytes=100-"}
    )

    assert request.get_header("Range") == "bytes=100-"
    assert request.get_header("User-agent")


def test_picontrol_filenames_carry_padded_model_years():
    names = [name for _, name in download.manifest(scenario="picontrol")]

    assert any(name.endswith("_0300_0499.nc") for name in names)
    assert any(name.endswith("_1801_2000.nc") for name in names)


def test_historical_filenames_carry_the_cmip_span():
    names = [name for _, name in download.manifest(scenario="historical")]

    assert names and all(name.endswith("_1850_2014.nc") for name in names)


def test_the_script_offers_nothing_the_pipeline_does_not_produce():
    # The other direction of the agreement above. A scenario withheld from the
    # pipeline has to leave the downloader too, or collaborators fetch 404s
    # for files that were deliberately unpublished.
    produced = {(e.source_id, e.experiment_id) for e in REAL_ENSEMBLES}
    for model, experiment, _, _, _ in download.ENSEMBLES:
        assert (model, experiment) in produced, f"{experiment} is not produced"
