"""Integrate a published intpp file globally, in PgC/yr.

    python scripts/check_npp.py OUTPUT.nc [--year 2040]

Net primary production is the one quantity here with a value everybody knows:
roughly 40-60 PgC/yr. That is what caught the original intpp mapping, which
used POC_PROD_zint + DOC_prod_zint and integrated to 18.2 -- entirely plausible
looking at a map, and wrong by a factor of nearly three.

Worth running against any archive whose provenance is uncertain, since a field
can carry the right name and the wrong contents.
"""

import argparse
import sys
from pathlib import Path

import xarray as xr

from fishmip_cesm.diagnostics import (
    area_weighted_total,
    cell_area_like,
    to_pg_c_per_year,
)

_PLAUSIBLE = (40.0, 60.0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--year", type=int, default=None)
    args = parser.parse_args()

    with xr.open_dataset(args.path) as dataset:
        if "intpp" not in dataset:
            print(f"not an intpp file: {list(dataset.data_vars)}")
            return 2
        field = dataset["intpp"]
        year = args.year or int(str(field["time"].values[0])[:4])
        annual = field.sel(time=str(year)).mean("time")
        total = to_pg_c_per_year(area_weighted_total(annual, cell_area_like(annual)))

    low, high = _PLAUSIBLE
    verdict = "ok" if low <= total <= high else "OUT OF RANGE"
    print(f"{args.path.name}")
    print(f"  {year}: {total:.2f} PgC/yr  (expected {low:.0f}-{high:.0f})  {verdict}")
    return 0 if verdict == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
