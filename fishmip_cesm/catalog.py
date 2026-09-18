"""Catalog CESM POP timeseries output and verify it is fit to preprocess."""

import re
from dataclasses import dataclass
from pathlib import Path

_TIMESERIES = re.compile(
    r"^(?P<case>.+)\.pop\.h\."
    r"(?P<variable>[A-Za-z0-9_]+)\."
    r"(?P<start>\d{6})-(?P<end>\d{6})\.nc$"
)


@dataclass(frozen=True)
class TimeseriesFile:
    case: str
    variable: str
    start: tuple[int, int]
    end: tuple[int, int]


def _year_month(stamp: str) -> tuple[int, int]:
    return int(stamp[:4]), int(stamp[4:])


def parse_timeseries_filename(name: str) -> TimeseriesFile | None:
    """Parse a POP monthly timeseries filename, or None if it is not one."""
    match = _TIMESERIES.match(name)
    if match is None:
        return None
    return TimeseriesFile(
        case=match["case"],
        variable=match["variable"],
        start=_year_month(match["start"]),
        end=_year_month(match["end"]),
    )


YearMonth = tuple[int, int]
Span = tuple[YearMonth, YearMonth]


def _to_index(ym: YearMonth) -> int:
    year, month = ym
    return year * 12 + (month - 1)


def _from_index(index: int) -> YearMonth:
    return index // 12, index % 12 + 1


def find_coverage_gaps(spans: list[Span], window: Span) -> list[Span]:
    """Return the sub-spans of `window` that `spans` does not cover.

    An empty result means the window is fully covered. Spans may overlap or
    arrive in any order.
    """
    window_start, window_end = (_to_index(ym) for ym in window)
    covered = set()
    for start, end in spans:
        covered.update(range(_to_index(start), _to_index(end) + 1))

    gaps: list[Span] = []
    gap_start: int | None = None
    for month in range(window_start, window_end + 1):
        if month in covered:
            if gap_start is not None:
                gaps.append((_from_index(gap_start), _from_index(month - 1)))
                gap_start = None
        elif gap_start is None:
            gap_start = month
    if gap_start is not None:
        gaps.append((_from_index(gap_start), _from_index(window_end)))
    return gaps


def scan_case_directory(directory: Path) -> list[TimeseriesFile]:
    """Parse every POP timeseries file in `directory`, skipping anything else."""
    found = []
    for path in sorted(Path(directory).iterdir()):
        parsed = parse_timeseries_filename(path.name)
        if parsed is not None:
            found.append(parsed)
    return found


@dataclass(frozen=True)
class CaseReport:
    case: str
    missing_variables: list[str]
    gaps: dict[str, list[Span]]

    @property
    def ok(self) -> bool:
        return not self.missing_variables and not any(self.gaps.values())


def verify_case(
    directory: Path,
    required_variables: list[str],
    window: Span,
) -> CaseReport:
    """Check one case directory supplies every required variable over `window`."""
    found = scan_case_directory(directory)
    by_variable: dict[str, list[Span]] = {}
    for entry in found:
        by_variable.setdefault(entry.variable, []).append((entry.start, entry.end))

    missing = [v for v in required_variables if v not in by_variable]
    gaps = {
        variable: find_coverage_gaps(by_variable[variable], window)
        for variable in required_variables
        if variable in by_variable
    }
    case = found[0].case if found else str(Path(directory).name)
    return CaseReport(case=case, missing_variables=missing, gaps=gaps)


MONTHLY_SUBPATH = Path("ocn") / "proc" / "tseries" / "month_1"


def verify_ensemble(
    root: Path,
    case_glob: str,
    required_variables: list[str],
    window: Span,
) -> list[CaseReport]:
    """Verify every case directory matching `case_glob` under `root`."""
    reports = []
    for case_dir in sorted(Path(root).glob(case_glob)):
        month_1 = case_dir / MONTHLY_SUBPATH
        if not month_1.is_dir():
            continue
        reports.append(verify_case(month_1, required_variables, window))
    return reports
