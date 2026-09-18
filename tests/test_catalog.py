from fishmip_cesm.catalog import (
    find_coverage_gaps,
    parse_timeseries_filename,
    scan_case_directory,
    verify_case,
    verify_ensemble,
)


def test_parses_case_variable_and_time_range_from_pop_monthly_filename():
    parsed = parse_timeseries_filename(
        "b.e21.BSSP245smbb.f09_g17.MCB-feedback-1DOF.001"
        ".pop.h.POC_PROD_zint.203501-206912.nc"
    )

    assert parsed.case == "b.e21.BSSP245smbb.f09_g17.MCB-feedback-1DOF.001"
    assert parsed.variable == "POC_PROD_zint"
    assert parsed.start == (2035, 1)
    assert parsed.end == (2069, 12)


def test_returns_none_for_a_file_that_is_not_a_pop_timeseries():
    assert parse_timeseries_filename("TREFHTMN.h1.bad") is None


def test_reports_no_gaps_when_files_tile_the_requested_window():
    files = [((2015, 1), (2064, 12)), ((2065, 1), (2100, 12))]

    assert find_coverage_gaps(files, window=((2035, 1), (2069, 12))) == []


def test_reports_gaps_when_a_case_covers_only_fragments_of_the_window():
    # The real walkerl/SSP245smbb 001_rerun case: every variable is present,
    # but coverage is only 2035-2036 and 2063-2064.
    files = [((2035, 1), (2036, 12)), ((2063, 1), (2064, 12))]

    assert find_coverage_gaps(files, window=((2035, 1), (2069, 12))) == [
        ((2037, 1), (2062, 12)),
        ((2065, 1), (2069, 12)),
    ]


def test_scans_a_case_directory_ignoring_files_that_are_not_timeseries(tmp_path):
    case = "b.e21.BSSP245smbb.f09_g17.MCB-feedback-1DOF.001"
    for name in [
        f"{case}.pop.h.TEMP.203501-206912.nc",
        f"{case}.pop.h.zooC.203501-206912.nc",
        "TREFHTMN.h1.bad",
    ]:
        (tmp_path / name).touch()

    found = scan_case_directory(tmp_path)

    assert sorted(f.variable for f in found) == ["TEMP", "zooC"]


WINDOW = ((2035, 1), (2069, 12))
CASE = "b.e21.BSSP245smbb.f09_g17.MCB-feedback-1DOF.001"


def test_flags_a_required_variable_that_is_missing_entirely(tmp_path):
    (tmp_path / f"{CASE}.pop.h.TEMP.203501-206912.nc").touch()

    report = verify_case(tmp_path, required_variables=["TEMP", "zooC"], window=WINDOW)

    assert report.missing_variables == ["zooC"]


def test_flags_coverage_gaps_when_variables_are_present_but_fragmentary(tmp_path):
    # Regression for walkerl/SSP245smbb ...001_rerun, which passed a
    # variable-name check but supplied only 2035-2036 and 2063-2064.
    for variable in ("TEMP", "zooC"):
        (tmp_path / f"{CASE}.pop.h.{variable}.203501-203612.nc").touch()
        (tmp_path / f"{CASE}.pop.h.{variable}.206301-206412.nc").touch()

    report = verify_case(tmp_path, required_variables=["TEMP", "zooC"], window=WINDOW)

    assert report.missing_variables == []
    assert report.gaps["TEMP"] == [
        ((2037, 1), (2062, 12)),
        ((2065, 1), (2069, 12)),
    ]


def test_reports_a_complete_case_as_ok(tmp_path):
    for variable in ("TEMP", "zooC"):
        (tmp_path / f"{CASE}.pop.h.{variable}.201501-206412.nc").touch()
        (tmp_path / f"{CASE}.pop.h.{variable}.206501-210012.nc").touch()

    report = verify_case(tmp_path, required_variables=["TEMP", "zooC"], window=WINDOW)

    assert report.ok


def test_verifies_every_case_directory_under_an_ensemble_root(tmp_path):
    prefix = "b.e21.BSSP245smbb.f09_g17.MCB-feedback-1DOF"
    for member in ("001", "002"):
        month_1 = tmp_path / f"{prefix}.{member}" / "ocn" / "proc" / "tseries" / "month_1"
        month_1.mkdir(parents=True)
        (month_1 / f"{prefix}.{member}.pop.h.TEMP.203501-206912.nc").touch()
    (tmp_path / "README").touch()

    reports = verify_ensemble(
        tmp_path, case_glob="b.e21.*", required_variables=["TEMP"], window=WINDOW
    )

    assert [r.case for r in reports] == [f"{prefix}.001", f"{prefix}.002"]
    assert all(r.ok for r in reports)
