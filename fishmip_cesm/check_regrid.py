"""Verify a generated weight file conserves the global integral. Run on Casper.

    fishmip-check-regrid --weights grids/gx1v7_to_fishmip_1deg_conserve.nc

Regrids one real year of `intpp` from gx1v7 onto the FishMIP grid and compares
the global integral before and after. A first-order conservative regrid should
preserve it to floating-point noise; anything larger means the weights, the
grids or the masks are wrong.

The absolute value is checked too. Global NPP was measured at 49.3 PgC/yr on the
native grid, so a regrid that conserves relative to a source we had already got
wrong would still be wrong.
"""

import argparse
import sys
from pathlib import Path

import xarray as xr

from fishmip_cesm.diagnostics import area_weighted_total, to_pg_c_per_year
from fishmip_cesm.ensembles import ENSEMBLES
from fishmip_cesm.inspect_source import _first_member, _open
from fishmip_cesm.regrid import (
    apply_weights,
    conservation_error,
    steradians_to_square_metres,
)
from fishmip_cesm.transform import convert_variable

# A first-order conservative regrid should do far better than this; the
# threshold is loose enough to tolerate accumulation over ~10^5 cells.
TOLERANCE = 1e-6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--ensemble", default="WACCM baseline")
    parser.add_argument("--year", type=int, default=2040)
    args = parser.parse_args()

    if not args.weights.exists():
        print(f"weight file not found: {args.weights}")
        return 2

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

    weights = xr.open_dataset(args.weights)
    for name in ("S", "row", "col", "area_a", "area_b"):
        if name not in weights:
            print(f"weight file is missing {name}")
            return 2

    photo = _open(month_1, "photoC_TOT_zint", args.year)
    if photo is None:
        print(f"could not open photoC_TOT_zint for {args.year}")
        return 2

    intpp = convert_variable("photoC_TOT_zint", photo).mean("time")
    source_area = steradians_to_square_metres(weights["area_a"])
    target_area = steradians_to_square_metres(weights["area_b"])

    flat = xr.DataArray(intpp.values.ravel(), dims="cell").fillna(0.0)
    regridded = apply_weights(flat, weights, n_target=target_area.sizes["n_b"])

    source_area = xr.DataArray(source_area.values, dims="cell")
    target_area = xr.DataArray(target_area.values, dims="cell")

    error = conservation_error(flat, source_area, regridded.fillna(0.0), target_area)
    npp_before = to_pg_c_per_year(area_weighted_total(flat, source_area))
    npp_after = to_pg_c_per_year(
        area_weighted_total(regridded.fillna(0.0), target_area)
    )

    print(f"weights:  {args.weights}")
    print(f"ensemble: {ensemble.name}, year {args.year}\n")
    print(f"  source cells: {source_area.sizes['cell']}")
    print(f"  target cells: {target_area.sizes['cell']}")
    print(f"  global NPP before: {npp_before:.4f} PgC/yr")
    print(f"  global NPP after:  {npp_after:.4f} PgC/yr")
    print(f"  conservation error: {error:+.3e}  (tolerance {TOLERANCE:.0e})")

    if abs(error) <= TOLERANCE:
        print("\nConservative regrid verified.")
        return 0
    print("\nNOT CONSERVATIVE -- check the method, grids and masks.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
