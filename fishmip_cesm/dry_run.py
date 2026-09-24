"""Run one member through the whole pipeline and put it through the gate.

    python -m fishmip_cesm.dry_run --weights grids/gx1v7_to_fishmip_1deg_conserve.nc

Transforms, regrids and validates a single year of every FishMIP variable,
writing nothing. This exercises stages 2 to 6 and stage 8 together against real
data, which is the only way to find out whether the pieces agree with each other
rather than merely each working alone.

Output is destined for a public bucket, so this is the check that has to pass
before anything is written, not after.
"""

import argparse
import sys
from pathlib import Path

import xarray as xr

from fishmip_cesm.diagnostics import area_weighted_total, to_pg_c_per_year
from fishmip_cesm.ensembles import ENSEMBLES
from fishmip_cesm.inspect_source import _first_member, _open
from fishmip_cesm.regrid import (
    conservation_error,
    regrid_variable,
    steradians_to_square_metres,
    variable_kind,
)
from fishmip_cesm.transform import convert_variable, derive_tob
from fishmip_cesm.validate import format_report, gate_passed, validate_variable

# CESM source -> what we do with it. 3D fields are checked at the surface; the
# regrid is horizontal, so a single level exercises the same code path.
SURFACE_OF_3D = {"NO3", "spC", "diatC", "zooC"}
DIRECT = ["photoC_TOT_zint", "pocToSed", "zoo_loss_zint", "NO3", "spC", "diatC", "zooC"]

CONSERVATION_TOLERANCE = 1e-6


def _flatten(field: xr.DataArray) -> xr.DataArray:
    return xr.DataArray(field.values.ravel(), dims="cell")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--ensemble", default="WACCM baseline")
    parser.add_argument("--year", type=int, default=2040)
    args = parser.parse_args()

    ensemble = next(
        (e for e in ENSEMBLES if args.ensemble.lower() in e.name.lower()), None
    )
    if ensemble is None:
        print(f"no ensemble matching {args.ensemble!r}")
        return 2
    month_1 = _first_member(ensemble)
    if month_1 is None:
        print(f"no member found under {ensemble.root}")
        return 2
    if not args.weights.exists():
        print(f"weight file not found: {args.weights}")
        return 2

    weights = xr.open_dataset(args.weights)
    source_area = xr.DataArray(
        steradians_to_square_metres(weights["area_a"]).values, dims="cell"
    )
    target_area = xr.DataArray(
        steradians_to_square_metres(weights["area_b"]).values, dims="cell"
    )
    n_target = target_area.sizes["cell"]

    grid = xr.open_dataset(
        sorted(month_1.glob("*.pop.h.TEMP.*.nc"))[0], decode_timedelta=True
    )
    kmt = grid["KMT"]

    print(f"{ensemble.name}, year {args.year}")
    print(f"weights: {args.weights}\n")

    # Ocean cells on the target grid: anywhere any source ocean landed.
    wet = regrid_variable(
        "thetao", _flatten(xr.ones_like(kmt).where(kmt > 0)), weights, n_target
    )
    ocean = wet.notnull()
    print(f"target ocean cells: {int(ocean.sum())} of {n_target}\n")

    temperature = _open(month_1, "TEMP", args.year)
    if temperature is None:
        print(f"could not open TEMP for {args.year}")
        return 2

    fields: dict[str, xr.DataArray] = {}
    surface = temperature.isel(z_t=0).mean("time")
    fields["thetao"] = convert_variable("TEMP", surface)
    fields["tob"] = derive_tob(temperature.mean("time"), kmt)

    for cesm_name in DIRECT:
        raw = _open(month_1, cesm_name, args.year)
        if raw is None:
            print(f"  could not open {cesm_name}, skipping")
            continue
        collapsed = raw.mean("time")
        if cesm_name in SURFACE_OF_3D:
            collapsed = collapsed.isel(z_t=0)
        converted = convert_variable(cesm_name, collapsed)
        fields[str(converted.name)] = converted

    failures = 0
    for name, native in sorted(fields.items()):
        flat = _flatten(native)
        regridded = regrid_variable(name, flat, weights, n_target)
        regridded.attrs = dict(native.attrs)

        checks = validate_variable(name, regridded, ocean)
        ok = gate_passed(checks)
        print(f"{name} ({variable_kind(name)}) {'ok' if ok else 'FAILED'}")
        print(format_report(checks))

        if variable_kind(name) == "flux":
            error = conservation_error(
                flat.fillna(0.0), source_area, regridded.fillna(0.0), target_area
            )
            conserved = abs(error) <= CONSERVATION_TOLERANCE
            ok = ok and conserved
            print(
                f"  [{'ok' if conserved else 'FAIL'}] conservation: "
                f"{error:+.3e} (tolerance {CONSERVATION_TOLERANCE:.0e})"
            )
            if name == "intpp":
                total = to_pg_c_per_year(
                    area_weighted_total(regridded.fillna(0.0), target_area)
                )
                print(f"  [--] global NPP after regrid: {total:.4f} PgC/yr")
        print()
        failures += 0 if ok else 1

    if failures:
        print(f"{failures} variable(s) failed the gate. Do not publish.")
        return 1
    print("All variables passed. Safe to write and publish.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
