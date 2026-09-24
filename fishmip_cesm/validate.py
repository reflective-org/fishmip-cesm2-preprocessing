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


# Generous bounds. These are not tuned to CESM2 -- they exist to catch unit
# slips, sign errors and regridding damage, not to police plausible variation.
PLAUSIBLE_RANGES = {
    "thetao": (-2.5, 40.0),  # degC; a Kelvin slip lands at ~290
    "tob": (-2.5, 40.0),
    "intpp": (0.0, 1e-4),  # mol m-2 s-1; observed max ~1.4e-5
    "expc-bot": (0.0, 1e-4),
    "zoo_loss": (0.0, 1e-4),
    "no3": (0.0, 0.1),  # mol m-3; deep ocean ~0.035
    "phyc": (0.0, 0.05),
    "phydiat": (0.0, 0.05),
    "zooc": (0.0, 0.05),
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
