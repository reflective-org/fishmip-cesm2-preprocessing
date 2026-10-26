"""Finding a member's files, whichever way its archive is laid out.

Two layouts are in play, and they are not interchangeable:

**case** -- each member is a directory holding all its variables:

    <root>/<case>/ocn/proc/tseries/month_1/<case>.pop.h.<VAR>.<range>.nc

**variable** -- each variable is a directory holding all members, which is how
the CESM2 Large Ensemble is stored:

    <root>/<VAR>/<case>.pop.h.<VAR>.<range>.nc

**flat** -- one directory, one file per member and variable, carrying the whole
record rather than a chunk of it, which is how the G6-1.5K-MCB runs ship:

    <root>/<case>.pop.h.<VAR>.nc

Neither of the last two has case directories to list, so the members have to be
recovered from the filenames. The flat layout also has no date range in the
name, so its span is only knowable by opening a file -- coverage cannot be
checked from the filesystem alone the way it can for the others.
"""

from fnmatch import fnmatch
from pathlib import Path

from fishmip_cesm.catalog import parse_timeseries_filename

MONTHLY_SUBPATH = Path("ocn") / "proc" / "tseries" / "month_1"

# Present in every ocean run, so it is a safe place to look for the member list.
_PROBE_VARIABLE = "TEMP"


def member_cases(ensemble) -> list[str]:
    """The case names of every member of this ensemble, in order."""
    if ensemble.layout == "case":
        return [
            directory.name
            for directory in sorted(ensemble.root.glob(ensemble.case_glob))
            if (directory / MONTHLY_SUBPATH).is_dir()
        ]
    if ensemble.layout == "flat":
        cases = set()
        for path in ensemble.root.glob(f"*.pop.h.{_PROBE_VARIABLE}.nc"):
            case = path.name.removesuffix(f".pop.h.{_PROBE_VARIABLE}.nc")
            if fnmatch(case, ensemble.case_glob):
                cases.add(case)
        return sorted(cases)
    if ensemble.layout == "variable":
        cases = set()
        for path in (ensemble.root / _PROBE_VARIABLE).glob(
            f"*.pop.h.{_PROBE_VARIABLE}.*.nc"
        ):
            parsed = parse_timeseries_filename(path.name)
            if parsed and fnmatch(parsed.case, ensemble.case_glob):
                cases.add(parsed.case)
        return sorted(cases)
    raise ValueError(f"unknown layout: {ensemble.layout}")


def variable_files(ensemble, case: str, variable: str) -> list[Path]:
    """Every timeseries chunk of one variable for one member."""
    if ensemble.layout == "case":
        directory = ensemble.root / case / MONTHLY_SUBPATH
        pattern = f"*.pop.h.{variable}.*.nc"
    elif ensemble.layout == "variable":
        directory = ensemble.root / variable
        # Anchored on the case: one directory holds every member.
        pattern = f"{case}.pop.h.{variable}.*.nc"
    elif ensemble.layout == "flat":
        # One file holds the whole record, so there is no range to match.
        directory = ensemble.root
        pattern = f"{case}.pop.h.{variable}.nc"
    else:
        raise ValueError(f"unknown layout: {ensemble.layout}")
    return sorted(directory.glob(pattern))


def member_label(case: str) -> str:
    """The short member identifier used in published filenames."""
    return case.rsplit(".", 1)[-1]


def member_labels(cases: list[str]) -> list[str]:
    """Labels for a set of cases, refusing any collision.

    Large Ensemble cases carry two numbers -- LE2-1001.001 and LE2-1011.001
    share the suffix 001 -- so two members can claim the same label and the
    second would overwrite the first's output under an identical filename.
    """
    labels = [member_label(case) for case in cases]
    duplicates = {label for label in labels if labels.count(label) > 1}
    if duplicates:
        raise ValueError(
            f"member labels collide: {', '.join(sorted(duplicates))}. "
            "Narrow the case glob so each member has a distinct suffix."
        )
    return labels


def _span_from_file(path: Path):
    """Read one file's covered span, for archives with no range in the name."""
    import xarray as xr

    from fishmip_cesm.transform import covered_span

    try:
        with xr.open_dataset(path, decode_timedelta=True) as dataset:
            return covered_span(dataset["time"].values)
    except (OSError, ValueError, KeyError, IndexError):
        return None


def ensemble_reports(ensemble, required_variables: list[str]) -> list:
    """Coverage reports for every member, in either layout.

    The writer and the input verifier have to agree about where a member's
    files are. They did not: the writer learned about variable-first archives
    and this did not, so the Large Ensemble looked empty.
    """
    from fishmip_cesm.catalog import CaseReport, find_coverage_gaps

    reports = []
    for case in member_cases(ensemble):
        spans_by_variable = {}
        for variable in required_variables:
            spans = []
            for path in variable_files(ensemble, case, variable):
                if ensemble.layout == "flat":
                    # No range in the name, so the span is only knowable by
                    # reading the file. Skipping the check instead would pass
                    # any coverage gap in this ensemble unseen.
                    span = _span_from_file(path)
                    if span:
                        spans.append(span)
                    continue
                parsed = parse_timeseries_filename(path.name)
                if parsed:
                    spans.append((parsed.start, parsed.end))
            if spans:
                spans_by_variable[variable] = spans

        reports.append(
            CaseReport(
                case=case,
                missing_variables=[
                    v for v in required_variables if v not in spans_by_variable
                ],
                gaps={
                    variable: find_coverage_gaps(spans, ensemble.window)
                    for variable, spans in spans_by_variable.items()
                },
            )
        )
    return reports
