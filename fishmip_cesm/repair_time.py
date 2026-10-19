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
import sys
from pathlib import Path

import cftime
import netCDF4
import numpy as np

from fishmip_cesm.validate import check_time_encoding

# Counting in seconds from the calendar's own epoch keeps every value inside
# the range where float64 holds integers exactly, which counting in days and
# scaling to microseconds does not.
_ROUNDING_UNITS = "seconds since 0001-01-01"
_SECONDS_PER_HOUR = 3600
# Timestamps are meant to be whole seconds; more drift than this means the
# repair misread the axis rather than tidied it.
_MAX_DRIFT_SECONDS = 0.5


def _time_encoding(path: Path) -> tuple[str | None, str]:
    """The units and calendar recorded on the file's time axis."""
    with netCDF4.Dataset(path) as dataset:
        if "time" not in dataset.variables:
            return None, "standard"
        time = dataset.variables["time"]
        return (
            getattr(time, "units", None),
            getattr(time, "calendar", "standard"),
        )


def needs_repair(path: Path) -> bool:
    """Whether this file's time axis is unreadable outside Python."""
    units, _ = _time_encoding(path)
    if units is None:  # deptho and thkcello carry no time axis
        return False
    return not check_time_encoding(units).passed


def _rounded_to_the_second(dates, calendar):
    seconds = cftime.date2num(dates, _ROUNDING_UNITS, calendar)
    return cftime.num2date(np.round(seconds), _ROUNDING_UNITS, calendar)


def _clean_units(first) -> tuple[str, int]:
    """Units anchored on the first timestamp, and the seconds they count in."""
    stamp = (
        f"{first.year:04d}-{first.month:02d}-{first.day:02d} "
        f"{first.hour:02d}:{first.minute:02d}:{first.second:02d}"
    )
    return f"hours since {stamp}", _SECONDS_PER_HOUR


def repair_file(path: Path) -> bool:
    """Restate one file's time axis in whole seconds. True if it was changed."""
    if not needs_repair(path):
        return False

    units, calendar = _time_encoding(path)
    with netCDF4.Dataset(path) as dataset:
        raw = dataset.variables["time"][:]
    original = cftime.num2date(np.asarray(raw), units, calendar)
    rounded = _rounded_to_the_second(original, calendar)

    new_units, step = _clean_units(rounded[0])
    offsets = cftime.date2num(rounded, new_units.replace("hours", "seconds"), calendar)
    if np.any(np.asarray(offsets) % step):
        # Not a whole number of hours apart, so say it in seconds instead of
        # silently rounding the axis to the nearest hour.
        new_units = new_units.replace("hours", "seconds")
        step = 1
    values = np.round(np.asarray(offsets) / step).astype("int64")

    with netCDF4.Dataset(path, "a") as dataset:
        time = dataset.variables["time"]
        time.units = new_units
        time[:] = values

    drift = _drift(path, original)
    if drift > _MAX_DRIFT_SECONDS:
        raise ValueError(f"{path.name}: timestamps moved {drift:.3f}s, not repaired")
    return True


def _drift(path: Path, original) -> float:
    """The largest distance any timestamp moved, read back from the file."""
    units, calendar = _time_encoding(path)
    with netCDF4.Dataset(path) as dataset:
        raw = dataset.variables["time"][:]
    written = cftime.num2date(np.asarray(raw), units, calendar)
    return max(abs((w - o).total_seconds()) for w, o in zip(written, original))


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
