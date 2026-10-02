"""The gate that stands between processed output and publication.

Output goes to a public bucket, and publishing is not reversible the way a local
write is -- once files are out they can be fetched and cached by others. So the
checks run before upload, not after, and they fail closed: a variable with no
declared range stops the gate rather than passing through it.
"""

from dataclasses import dataclass

import xarray as xr


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


# Bounds exist to catch unit slips, sign errors and regridding damage, not to
# police plausible variation. Upper bounds carry the maximum measured in the
# 2026-09-24 dry run (WACCM baseline, 2040, surface) so the headroom is visible.
PLAUSIBLE_RANGES = {
    # Seawater freezes near -1.9 degC at the surface but around -3.5 degC at
    # 5000 m, and water formed against ice at depth keeps a potential
    # temperature below the surface freezing point. That is Ice Shelf Water, and
    # it is the coldest thing in a full-depth Southern Ocean field: measured
    # minima here run to -3.19 degC. A bound of -2.5 rejected 25 perfectly good
    # files. A Kelvin slip still lands at ~270 and is still caught.
    "thetao": (-3.5, 40.0),  # degC; measured -3.19 to 35.8
    "tob": (-3.5, 40.0),  # measured -2.13 to 32.8
    "intpp": (0.0, 1e-4),  # mol m-2 s-1; measured 6.0e-6
    "expc-bot": (0.0, 1e-4),  # measured 1.9e-6
    "zoo_loss": (0.0, 1e-4),  # measured 4.8e-7
    "no3": (0.0, 0.1),  # mol m-3; measured 0.023
    "phyc": (0.0, 0.2),  # measured 0.0063
    "phydiat": (0.0, 0.2),  # measured 0.057 -- a bloom, and over my first guess
    "zooc": (0.0, 0.2),  # measured 0.0026
    "deptho": (0.0, 11000.0),  # m
    "thkcello": (0.0, 1000.0),  # m
}


def check_range(fishmip_name: str, field: xr.DataArray) -> Check:
    """Confirm a field's values are physically plausible, ignoring land."""
    low, high = PLAUSIBLE_RANGES[fishmip_name]
    smallest = float(field.min())
    largest = float(field.max())
    passed = low <= smallest and largest <= high
    return Check(
        name=f"{fishmip_name} range",
        passed=passed,
        detail=(
            f"min {smallest:.4g}, max {largest:.4g}; "
            f"expected {low:.4g} to {high:.4g}"
        ),
    )


def check_no_ocean_holes(field: xr.DataArray, ocean: xr.DataArray) -> Check:
    """Confirm every cell containing ocean actually carries a value.

    A regrid that silently drops cells leaves gaps the range check cannot see,
    because a missing value has no value to be out of range.
    """
    holes = int((ocean & field.isnull()).sum())
    return Check(
        name="ocean coverage",
        passed=holes == 0,
        detail=f"{holes} ocean cell(s) with no value",
    )


def _expected_units(fishmip_name: str) -> str:
    """The units this variable should carry, converted or derived."""
    from fishmip_cesm.transform import fishmip_units

    return fishmip_units(fishmip_name)


def check_units(fishmip_name: str, field: xr.DataArray) -> Check:
    """Confirm the field still declares the units the conversion gave it."""
    expected = _expected_units(fishmip_name)
    actual = field.attrs.get("units")
    return Check(
        name=f"{fishmip_name} units",
        passed=actual == expected,
        detail=f"units {actual!r}; expected {expected!r}",
    )


def validate_variable(
    fishmip_name: str,
    field: xr.DataArray,
    ocean: xr.DataArray,
) -> list[Check]:
    """Every per-field check the gate applies before a variable may be published."""
    return [
        check_range(fishmip_name, field),
        check_units(fishmip_name, field),
        check_no_ocean_holes(field, ocean),
    ]


def gate_passed(checks: list[Check]) -> bool:
    """One failure is enough. There is no partial credit before publication."""
    return all(check.passed for check in checks)


def format_report(checks: list[Check]) -> str:
    return "\n".join(
        f"  [{'ok' if c.passed else 'FAIL'}] {c.name}: {c.detail}" for c in checks
    )


@dataclass(frozen=True)
class ClipReport:
    variable: str
    cells: int
    most_negative: float
    removed_fraction: float

    def describe(self) -> str:
        if self.cells == 0:
            return f"{self.variable}: nothing clipped"
        return (
            f"{self.variable}: clipped {self.cells} cell(s), "
            f"most negative {self.most_negative:.4g}, "
            f"{self.removed_fraction:.3%} of the field removed"
        )


def may_be_negative(fishmip_name: str) -> bool:
    """Whether this variable can physically take negative values."""
    return PLAUSIBLE_RANGES[fishmip_name][0] < 0


def clip_negatives(
    fishmip_name: str,
    field: xr.DataArray,
    *,
    defer: bool = False,
):
    """Clip physically impossible negatives to zero, reporting what was removed.

    MARBL's advection scheme produces small negative tracer values. They are
    numerical, not physical, and negative concentrations are not usable forcing
    -- but clipping edits data on its way to a public bucket, so the amount
    removed is reported rather than absorbed silently.

    Refused for variables that may legitimately be negative: sea water reaches
    -1.9 degC, and clipping temperature would be both wrong and hard to notice.

    With `defer`, the statistics come back unevaluated so the caller can compute
    them in the same pass as the write. Evaluating them here instead costs an
    entire extra read of the source -- around fourteen minutes for a full-depth
    variable on campaign storage.
    """
    low, _ = PLAUSIBLE_RANGES[fishmip_name]
    if low < 0:
        raise ValueError(
            f"{fishmip_name} may legitimately be negative; refusing to clip"
        )

    negative = field < 0
    stats = (
        negative.sum(),
        field.where(negative).sum(),
        field.where(~negative).sum(),
        field.min(),
    )
    clipped = field.where(~negative, 0.0)

    if defer:
        return clipped, stats
    if field.chunks is not None:
        import dask

        stats = dask.compute(*stats)
    return clipped, clip_report(fishmip_name, stats)


def clip_report(fishmip_name: str, stats) -> ClipReport:
    """Assemble a report from evaluated clip statistics."""
    cells, removed, kept, smallest = (float(s) for s in stats)
    return ClipReport(
        variable=fishmip_name,
        cells=int(cells),
        most_negative=smallest if cells else 0.0,
        removed_fraction=abs(removed) / kept if kept else 0.0,
    )


def check_time_coverage(field: xr.DataArray, window) -> Check:
    """Confirm the time axis is exactly the months the window asks for.

    This exists because POP stamps monthly means at the end of their interval.
    Slicing the raw stamps shifted every month by one and silently dropped the
    last month of the window -- an error that changes a seasonal cycle and that
    every other check passed.
    """
    (start_year, start_month), (end_year, end_month) = window
    expected = (end_year - start_year) * 12 + (end_month - start_month) + 1

    times = field["time"].values
    found = len(times)
    first = str(times[0])[:7]
    last = str(times[-1])[:7]
    wanted_first = f"{start_year}-{start_month:02d}"
    wanted_last = f"{end_year}-{end_month:02d}"

    passed = found == expected and first == wanted_first and last == wanted_last
    return Check(
        name="time coverage",
        passed=passed,
        detail=(
            f"{found} months {first} to {last}; "
            f"expected {expected} months {wanted_first} to {wanted_last}"
        ),
    )
