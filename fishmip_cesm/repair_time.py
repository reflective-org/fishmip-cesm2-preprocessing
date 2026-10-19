"""Rewrite a time axis that only Python can read, without touching the data.

    python -m fishmip_cesm.repair_time --out-dir "$OUT_DIR"           # lists only
    python -m fishmip_cesm.repair_time --out-dir "$OUT_DIR" --apply

xarray writes a time axis relative to its first value, so a sub-second
remainder in the timestamps becomes a fractional-second base such as
"nanoseconds since 2035-01-16 13:00:00.000001536". Python reads that back
perfectly. udunits does not parse it at all: ncdump prints raw integers and CDO
reports every timestamp as 0000-00-00 00:00:00, with no error either way.

`transform.centre_time` no longer produces such an axis, but files written
before that fix carry one. The timestamps themselves are only a fraction of a
second out, so the repair is to round them to the whole second they were always
meant to land on and restate the units -- a few kilobytes of a multi-gigabyte
file. Regenerating the data would cost days and change nothing else.

Every repair is checked by reading the file back before moving on, and any file
whose timestamps move by more than half a second is left as it was.
"""

import argparse
import re
import sys
from pathlib import Path

import netCDF4
import numpy as np

from fishmip_cesm.validate import check_time_encoding

_NS_PER_SECOND = 1_000_000_000
_SECONDS_PER_HOUR = 3600

# Every CF time unit, in nanoseconds. cftime refuses 'nanoseconds' outright --
# it accepts microseconds and coarser -- which is why this works on the
# offsets directly instead of decoding them into dates.
_NANOSECONDS_PER = {
    "nanoseconds": 1,
    "microseconds": 1_000,
    "milliseconds": 1_000_000,
    "seconds": _NS_PER_SECOND,
    "minutes": 60 * _NS_PER_SECOND,
    "hours": _SECONDS_PER_HOUR * _NS_PER_SECOND,
    "days": 86_400 * _NS_PER_SECOND,
}

_UNITS = re.compile(r"^\s*(\w+)\s+since\s+(.*?)\s*$")
# A base's own fractional second, which is the whole problem: xarray anchors
# the axis on its first value, so any remainder there lands in the units.
_FRACTION = re.compile(r"^(.*?\d{2}:\d{2}:\d{2})\.(\d+)(.*)$")

# Timestamps are meant to be whole seconds; more drift than this means the
# axis was misread rather than tidied.
_MAX_DRIFT_SECONDS = 0.5


def _time_encoding(path: Path) -> tuple[str | None, str]:
    """The units and calendar recorded on the file's time axis."""
    with netCDF4.Dataset(path) as dataset:
        if "time" not in dataset.variables:
            return None, "standard"
        time = dataset.variables["time"]
        return getattr(time, "units", None), getattr(time, "calendar", "standard")


def needs_repair(path: Path) -> bool:
    """Whether this file's time axis is unreadable outside Python."""
    units, _ = _time_encoding(path)
    if units is None:  # deptho and thkcello carry no time axis
        return False
    return not check_time_encoding(units).passed


def _split_units(units: str) -> tuple[int, str, int]:
    """Nanoseconds per step, the base truncated to a whole second, and its
    fractional part in nanoseconds."""
    matched = _UNITS.match(units)
    if not matched:
        raise ValueError(f"cannot read time units: {units!r}")
    step, base = matched.group(1), matched.group(2)
    if step not in _NANOSECONDS_PER:
        raise ValueError(f"unknown time unit {step!r} in {units!r}")

    fraction = _FRACTION.match(base)
    if not fraction:
        return _NANOSECONDS_PER[step], base, 0
    digits = fraction.group(2)[:9].ljust(9, "0")
    return (
        _NANOSECONDS_PER[step],
        fraction.group(1) + fraction.group(3),
        int(digits),
    )


def _whole_seconds(values, units: str) -> tuple[list[int], str]:
    """Offsets from a whole-second base, rounded to the nearest second.

    Python integers throughout: a nanosecond count across 35 years runs to
    1e18, and folding the base's fraction back in before rounding has to be
    exact or the repair invents the drift it is meant to remove.
    """
    per_step, base, fraction = _split_units(units)
    seconds = []
    for value in values:
        nanoseconds = int(value) * per_step + fraction
        seconds.append((nanoseconds + _NS_PER_SECOND // 2) // _NS_PER_SECOND)
    return seconds, base


def repair_file(path: Path) -> bool:
    """Restate one file's time axis in whole seconds. True if it was changed."""
    if not needs_repair(path):
        return False

    units, _ = _time_encoding(path)
    with netCDF4.Dataset(path) as dataset:
        raw = np.asarray(dataset.variables["time"][:])
    seconds, base = _whole_seconds(raw, units)

    # Prefer hours, to match the files that were always readable, but only when
    # every stamp is a whole number of them -- otherwise say it in seconds
    # rather than quietly round the axis to the nearest hour.
    if all(offset % _SECONDS_PER_HOUR == 0 for offset in seconds):
        new_units = f"hours since {base}"
        values = [offset // _SECONDS_PER_HOUR for offset in seconds]
    else:
        new_units = f"seconds since {base}"
        values = seconds

    with netCDF4.Dataset(path, "a") as dataset:
        time = dataset.variables["time"]
        time.units = new_units
        time[:] = np.asarray(values, dtype="int64")

    drift = _drift(path, seconds)
    if drift > _MAX_DRIFT_SECONDS:
        raise ValueError(f"{path.name}: timestamps moved {drift:.3f}s, not repaired")
    return True


def _drift(path: Path, intended: list[int]) -> float:
    """How far the written axis sits from the seconds it was meant to carry."""
    units, _ = _time_encoding(path)
    with netCDF4.Dataset(path) as dataset:
        raw = np.asarray(dataset.variables["time"][:])
    written, _ = _whole_seconds(raw, units)
    return max(abs(w - i) for w, i in zip(written, intended))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually rewrite. Without this, nothing is changed.",
    )
    args = parser.parse_args()

    paths = sorted(args.out_dir.glob("*.nc"))
    if not paths:
        print(f"no files in {args.out_dir}")
        return 2

    broken = [p for p in paths if needs_repair(p)]
    print(f"{len(paths)} file(s), {len(broken)} with an unreadable time axis\n")
    if not broken:
        print("nothing to repair")
        return 0

    if not args.apply:
        for path in broken[:10]:
            units, _ = _time_encoding(path)
            print(f"  {path.name}\n      {units}")
        if len(broken) > 10:
            print(f"  ... and {len(broken) - 10} more")
        print("\nDRY RUN -- pass --apply to rewrite these time axes.")
        return 0

    failures = 0
    for path in broken:
        try:
            repair_file(path)
            print(f"repaired {path.name}")
        except (OSError, ValueError) as error:
            failures += 1
            print(f"FAILED {path.name}: {error}")

    remaining = [p for p in paths if needs_repair(p)]
    print(f"\n{len(broken) - failures} repaired, {len(remaining)} still unreadable")
    return 1 if failures or remaining else 0


if __name__ == "__main__":
    sys.exit(main())
