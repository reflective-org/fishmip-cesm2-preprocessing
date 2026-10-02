"""Write the time-invariant fields: deptho and thkcello.

    python -m fishmip_cesm.write_static --weights WEIGHTS [--write] [--out-dir DIR]

These do not vary in time, and the ocean grid is the same for every member and
every scenario, so they are **two files for the whole set** rather than two per
member. They are derived from whichever ensemble is to hand; the result is
identical either way.

Small enough to be an afterthought -- a few megabytes against 280 GB -- but
FEISTY needs `deptho` and the project specification asks for both, so without
them the set is incomplete.
"""

import argparse
import sys
from pathlib import Path

import xarray as xr

from fishmip_cesm.ensembles import ENSEMBLES
from fishmip_cesm.naming import FIXED_PREFIX, fixed_filename, object_key, BUCKET
from fishmip_cesm.output import to_fishmip_dataset, unflatten
from fishmip_cesm.regrid import regrid_variable
from fishmip_cesm.transform import convert_variable, masked_thickness
from fishmip_cesm.validate import check_range, check_units, gate_passed
from fishmip_cesm.write_output import (
    COMPRESSION,
    _members,
    _to_cells,
    compression,
)


def _grid_of(month_1: Path) -> xr.Dataset:
    """POP's static grid fields, which ride along in every history file."""
    return xr.open_dataset(
        sorted(month_1.glob("*.pop.h.TEMP.*.nc"))[0], decode_timedelta=True
    )


def build_fixed_fields(grid: xr.Dataset, weights, n_target: int) -> dict:
    """Regrid deptho and thkcello onto the FishMIP grid."""
    kmt = grid["KMT"]

    deptho = convert_variable("HT", grid["HT"].where(kmt > 0))
    thkcello = convert_variable("dz", masked_thickness(grid["dz"], kmt))

    fields = {}
    for name, native in (("deptho", deptho), ("thkcello", thkcello)):
        regridded = regrid_variable(name, _to_cells(native), weights, n_target)
        field = unflatten(regridded)
        field.attrs = dict(native.attrs)
        fields[name] = field
    return fields


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--complevel", type=int, default=4)
    args = parser.parse_args()

    if not args.weights.exists():
        print(f"weight file not found: {args.weights}")
        return 2
    weights = xr.open_dataset(args.weights)
    n_target = weights.sizes["n_b"]

    month_1 = next(
        (m for e in ENSEMBLES for m in _members(e)), None
    )
    if month_1 is None:
        print("no member found to take the grid from")
        return 2
    print(f"grid from {month_1}\n")

    fields = build_fixed_fields(_grid_of(month_1), weights, n_target)

    failures = 0
    for name, field in fields.items():
        filename = fixed_filename(name)
        checks = [check_range(name, field), check_units(name, field)]
        if not gate_passed(checks):
            failures += 1
            print(f"{name}: FAILED the gate, not written")
            for check in checks:
                if not check.passed:
                    print(f"  {check.name}: {check.detail}")
            continue

        if not args.write:
            size = field.nbytes / 1e6
            print(f"would write {filename}  ({size:.1f} MB)")
            print(f"         -> s3://{BUCKET}/{object_key(FIXED_PREFIX, filename)}")
            continue

        dataset = to_fishmip_dataset(
            name,
            field,
            model="cesm2",
            scenario="fx",
            member="none",
            cesm_source="HT" if name == "deptho" else "dz",
            description="CESM2 POP gx1v7, time-invariant",
        )
        args.out_dir.mkdir(parents=True, exist_ok=True)
        target = args.out_dir / filename
        dataset.to_netcdf(target, encoding={name: compression(args.complevel)})
        print(f"wrote {target} ({target.stat().st_size / 1e6:.1f} MB)")

    if failures:
        return 1
    if not args.write:
        print("\nDRY RUN -- pass --write to produce these.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
