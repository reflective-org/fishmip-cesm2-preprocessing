"""Open one real member on GLADE and sanity-check the stage 2 transforms.

    fishmip-inspect-source [--ensemble NAME] [--year YEAR]

Reads a single year from one member, applies the conversions, and reports
quantities whose correct magnitude is known independently. The point is to catch
unit errors: a field scaled by the wrong power of ten looks perfectly reasonable
on its own, and only a comparison against a known global number exposes it.

Nothing is written. This is a read-only check to run before building the regrid.
"""

import argparse
import sys
from pathlib import Path

import xarray as xr

from fishmip_cesm.catalog import parse_timeseries_filename
from fishmip_cesm.diagnostics import area_weighted_total, to_pg_c_per_year
from fishmip_cesm.ensembles import ENSEMBLES
from fishmip_cesm.transform import (
    convert_variable,
    derive_intpp,
    derive_tob,
    subset_to_window,
)

# Global net primary production is roughly 40-60 PgC/yr. CESM2 sits in range.
EXPECTED_NPP_RANGE = (30.0, 80.0)


def _first_member(ensemble) -> Path | None:
    for case_dir in sorted(ensemble.root.glob(ensemble.case_glob)):
        month_1 = case_dir / "ocn" / "proc" / "tseries" / "month_1"
        if month_1.is_dir():
            return month_1
    return None


def _open(month_1: Path, variable: str, year: int) -> xr.DataArray | None:
    """Open whichever timeseries chunk contains `year`."""
    for path in sorted(month_1.glob(f"*.pop.h.{variable}.*.nc")):
        parsed = parse_timeseries_filename(path.name)
        if parsed and parsed.start[0] <= year <= parsed.end[0]:
            data = xr.open_dataset(path, decode_timedelta=True)[variable]
            return subset_to_window(data, ((year, 1), (year, 12)))
    return None


def _report_range(name: str, field: xr.DataArray) -> None:
    print(
        f"  {name:>10}: min {float(field.min()):>12.4g}  "
        f"max {float(field.max()):>12.4g}  units {field.attrs.get('units', '?')}"
    )


def inspect(ensemble, year: int) -> bool:
    print(f"\n=== {ensemble.name} [{ensemble.model}], year {year} ===")
    month_1 = _first_member(ensemble)
    if month_1 is None:
        print(f"  no member found under {ensemble.root}")
        return False
    print(f"  {month_1}")

    grid = xr.open_dataset(
        sorted(month_1.glob("*.pop.h.TEMP.*.nc"))[0], decode_timedelta=True
    )
    for name in ("KMT", "TAREA", "HT", "dz"):
        if name not in grid:
            print(f"  MISSING grid field {name}")
            return False

    area = convert_variable("TAREA", grid["TAREA"])
    kmt = grid["KMT"]

    temperature = _open(month_1, "TEMP", year)
    poc = _open(month_1, "POC_PROD_zint", year)
    doc = _open(month_1, "DOC_prod_zint", year)
    if temperature is None or poc is None or doc is None:
        print(f"  could not open TEMP/POC_PROD_zint/DOC_prod_zint for {year}")
        return False

    thetao = convert_variable("TEMP", temperature)
    tob = derive_tob(temperature, kmt)
    intpp = derive_intpp(poc, doc)

    _report_range("thetao", thetao)
    _report_range("tob", tob)
    _report_range("intpp", intpp)
    _report_range("areacello", area)
    _report_range("deptho", convert_variable("HT", grid["HT"]))

    total_area = float(area.where(kmt > 0).sum())
    print(f"\n  ocean area: {total_area:.4g} m2  (expect ~3.6e14)")

    npp = to_pg_c_per_year(area_weighted_total(intpp.mean("time"), area))
    low, high = EXPECTED_NPP_RANGE
    verdict = "ok" if low <= npp <= high else "OUT OF RANGE"
    print(f"  global NPP: {npp:.1f} PgC/yr  (expect {low:.0f}-{high:.0f})  {verdict}")
    return verdict == "ok"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ensemble", help="substring of an ensemble name")
    parser.add_argument("--year", type=int, default=2040)
    args = parser.parse_args()

    selected = [
        e
        for e in ENSEMBLES
        if not args.ensemble or args.ensemble.lower() in e.name.lower()
    ]
    if not selected:
        print(f"no ensemble matching {args.ensemble!r}")
        return 2

    results = [inspect(e, args.year) for e in selected]
    print()
    if all(results):
        print("All inspected ensembles look physically sane.")
        return 0
    print("Some checks failed or fell out of range -- see above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
