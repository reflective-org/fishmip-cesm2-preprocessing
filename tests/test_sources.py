import pytest

from fishmip_cesm.sources import member_cases, member_labels, variable_files


class FakeEnsemble:
    def __init__(self, root, case_glob, layout):
        self.root = root
        self.case_glob = case_glob
        self.layout = layout
        self.name = "fake"


def _case_layout(tmp_path):
    """<case>/ocn/proc/tseries/month_1/<case>.pop.h.<VAR>.<range>.nc"""
    for member in ("001", "002"):
        case = f"b.e21.BWHIST.f09_g17.CMIP6-historical-WACCM.{member}"
        month_1 = tmp_path / case / "ocn" / "proc" / "tseries" / "month_1"
        month_1.mkdir(parents=True)
        for variable in ("TEMP", "NO3"):
            (month_1 / f"{case}.pop.h.{variable}.185001-201412.nc").touch()
    return FakeEnsemble(
        tmp_path, "b.e21.BWHIST.f09_g17.CMIP6-historical-WACCM.[0-9][0-9][0-9]", "case"
    )


def _variable_layout(tmp_path):
    """<VAR>/<case>.pop.h.<VAR>.<range>.nc -- how CESM2-LE is stored."""
    for variable in ("TEMP", "NO3"):
        directory = tmp_path / variable
        directory.mkdir(parents=True)
        for case in (
            "b.e21.BHISTcmip6.f09_g17.LE2-1001.001",
            "b.e21.BHISTsmbb.f09_g17.LE2-1301.011",
        ):
            for decade in ("185001-185912", "186001-186912"):
                (directory / f"{case}.pop.h.{variable}.{decade}.nc").touch()
    return FakeEnsemble(tmp_path, "b.e21.BHISTsmbb.f09_g17.LE2-*", "variable")


def test_case_layout_finds_its_members(tmp_path):
    ensemble = _case_layout(tmp_path)

    assert member_cases(ensemble) == [
        "b.e21.BWHIST.f09_g17.CMIP6-historical-WACCM.001",
        "b.e21.BWHIST.f09_g17.CMIP6-historical-WACCM.002",
    ]


def test_variable_layout_finds_its_members(tmp_path):
    # Case names have to be recovered from filenames: there are no case
    # directories to list.
    ensemble = _variable_layout(tmp_path)

    assert member_cases(ensemble) == ["b.e21.BHISTsmbb.f09_g17.LE2-1301.011"]


def test_variable_layout_ignores_cases_the_glob_excludes(tmp_path):
    ensemble = _variable_layout(tmp_path)

    assert not any("cmip6" in case for case in member_cases(ensemble))


def test_case_layout_collects_a_variable_across_its_chunks(tmp_path):
    ensemble = _case_layout(tmp_path)
    case = member_cases(ensemble)[0]

    found = variable_files(ensemble, case, "TEMP")

    assert len(found) == 1
    assert found[0].name.endswith(".TEMP.185001-201412.nc")


def test_variable_layout_collects_a_variable_across_its_chunks(tmp_path):
    ensemble = _variable_layout(tmp_path)
    case = member_cases(ensemble)[0]

    found = variable_files(ensemble, case, "TEMP")

    assert len(found) == 2
    assert all(f.parent.name == "TEMP" for f in found)
    assert all(case in f.name for f in found)


def test_variable_layout_does_not_mix_cases(tmp_path):
    ensemble = _variable_layout(tmp_path)
    case = member_cases(ensemble)[0]

    found = variable_files(ensemble, case, "TEMP")

    assert not any("1001" in f.name for f in found)


def test_an_unknown_layout_is_refused(tmp_path):
    ensemble = FakeEnsemble(tmp_path, "*", "something-else")

    with pytest.raises(ValueError, match="something-else"):
        member_cases(ensemble)


def test_member_labels_are_the_three_digit_suffix():
    from fishmip_cesm.sources import member_label

    assert member_label("b.e21.BWHIST.f09_g17.CMIP6-historical-WACCM.002") == "002"
    assert member_label("b.e21.BHISTsmbb.f09_g17.LE2-1301.011") == "011"


def test_colliding_member_labels_are_refused():
    # Two Large Ensemble cases can share a three-digit suffix, and identical
    # labels would mean two members writing to the same filename.
    from fishmip_cesm.sources import member_labels

    with pytest.raises(ValueError, match="001"):
        member_labels(
            [
                "b.e21.BHISTsmbb.f09_g17.LE2-1001.001",
                "b.e21.BHISTsmbb.f09_g17.LE2-1011.001",
            ]
        )


def test_distinct_labels_pass_through():
    from fishmip_cesm.sources import member_labels

    assert member_labels(
        [
            "b.e21.BWHIST.f09_g17.CMIP6-historical-WACCM.001",
            "b.e21.BWHIST.f09_g17.CMIP6-historical-WACCM.002",
        ]
    ) == ["001", "002"]


def test_reports_cover_a_case_layout_ensemble(tmp_path):
    from fishmip_cesm.sources import ensemble_reports

    ensemble = _case_layout(tmp_path)
    ensemble.window = ((1850, 1), (2014, 12))

    reports = ensemble_reports(ensemble, ["TEMP", "NO3"])

    assert len(reports) == 2
    assert all(r.ok for r in reports)


def test_reports_cover_a_variable_layout_ensemble(tmp_path):
    # The input verifier has to understand both layouts, not just the writer.
    from fishmip_cesm.sources import ensemble_reports

    ensemble = _variable_layout(tmp_path)
    ensemble.window = ((1850, 1), (1869, 12))

    reports = ensemble_reports(ensemble, ["TEMP", "NO3"])

    assert len(reports) == 1
    assert reports[0].case == "b.e21.BHISTsmbb.f09_g17.LE2-1301.011"
    assert reports[0].ok


def test_reports_name_a_variable_missing_from_a_variable_layout(tmp_path):
    from fishmip_cesm.sources import ensemble_reports

    ensemble = _variable_layout(tmp_path)
    ensemble.window = ((1850, 1), (1869, 12))

    reports = ensemble_reports(ensemble, ["TEMP", "spC"])

    assert reports[0].missing_variables == ["spC"]


def test_reports_find_a_gap_in_a_variable_layout(tmp_path):
    from fishmip_cesm.sources import ensemble_reports

    ensemble = _variable_layout(tmp_path)
    ensemble.window = ((1850, 1), (1889, 12))  # two decades beyond what exists

    reports = ensemble_reports(ensemble, ["TEMP"])

    assert not reports[0].ok
    assert reports[0].gaps["TEMP"]


def test_the_writer_and_the_verifier_resolve_the_same_members(tmp_path):
    # These drifted once: the writer learned about variable-first archives and
    # the verifier did not, so a whole ensemble read as empty.
    from fishmip_cesm.sources import ensemble_reports

    for build in (_case_layout, _variable_layout):
        root = tmp_path / build.__name__
        root.mkdir()
        ensemble = build(root)
        ensemble.window = ((1850, 1), (1859, 12))

        from_writer = member_cases(ensemble)
        from_verifier = [r.case for r in ensemble_reports(ensemble, ["TEMP"])]

        assert from_writer == from_verifier


def _flat_archive(tmp_path):
    """One directory of <case>.pop.h.<VAR>.nc, as the G6-1.5K-MCB runs ship.

    No member directories, no variable directories, and no date range in the
    name -- the whole record of one variable sits in a single file.
    """
    for member in ("001", "002", "003"):
        for variable in ("TEMP", "NO3", "spC"):
            path = tmp_path / f"BSSP245.G6-1.5K-MCB.massbal.{member}.pop.h.{variable}.nc"
            path.write_bytes(b"")
    # A stray script lives alongside the data in the real archive.
    (tmp_path / "transfer_ocn.sh").write_text("#!/bin/sh\n")
    return FakeEnsemble(
        root=tmp_path,
        case_glob="BSSP245.G6-1.5K-MCB.massbal.[0-9][0-9][0-9]",
        layout="flat",
    )


def test_a_flat_archive_yields_its_members(tmp_path):
    ensemble = _flat_archive(tmp_path)

    assert member_cases(ensemble) == [
        "BSSP245.G6-1.5K-MCB.massbal.001",
        "BSSP245.G6-1.5K-MCB.massbal.002",
        "BSSP245.G6-1.5K-MCB.massbal.003",
    ]


def test_a_flat_archive_ignores_files_that_are_not_data(tmp_path):
    ensemble = _flat_archive(tmp_path)

    assert all("transfer" not in case for case in member_cases(ensemble))


def test_a_flat_archive_finds_one_file_per_variable(tmp_path):
    ensemble = _flat_archive(tmp_path)

    found = variable_files(ensemble, "BSSP245.G6-1.5K-MCB.massbal.002", "NO3")

    assert [p.name for p in found] == [
        "BSSP245.G6-1.5K-MCB.massbal.002.pop.h.NO3.nc"
    ]


def test_a_flat_member_label_is_its_trailing_number(tmp_path):
    ensemble = _flat_archive(tmp_path)

    assert member_labels(member_cases(ensemble)) == ["001", "002", "003"]
