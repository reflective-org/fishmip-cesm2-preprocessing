"""Finding a member's files, whichever way its archive is laid out.

Two layouts are in play, and they are not interchangeable:

**case** -- each member is a directory holding all its variables:

    <root>/<case>/ocn/proc/tseries/month_1/<case>.pop.h.<VAR>.<range>.nc

**variable** -- each variable is a directory holding all members, which is how
the CESM2 Large Ensemble is stored:

    <root>/<VAR>/<case>.pop.h.<VAR>.<range>.nc

In the variable layout there are no case directories to list, so the members
have to be recovered from the filenames themselves.
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
