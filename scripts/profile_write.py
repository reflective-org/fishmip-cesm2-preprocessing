"""Time each stage of one variable's write, to find where the time actually goes.

    python scripts/profile_write.py --weights grids/gx1v7_to_fishmip_1deg_conserve.nc

Reads, regrids and writes a single year and reports the split. Reasoning about
this has already cost two rounds; the point is to measure reading against
computing against writing rather than argue about them.
"""

import argparse
import time
from pathlib import Path

import xarray as xr

from fishmip_cesm.chunking import time_chunk
from fishmip_cesm.ensembles import ENSEMBLES
from fishmip_cesm.output import unflatten
from fishmip_cesm.regrid import regrid_variable
from fishmip_cesm.transform import centre_time, convert_variable, depth_dim
from fishmip_cesm.write_output import COMPRESSION, _members, _to_cells, _window_paths

CESM_OF = {"thetao": "TEMP", "intpp": "photoC_TOT_zint", "no3": "NO3"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--ensemble", default="MCB")
    ap.add_argument("--variable", default="thetao", choices=sorted(CESM_OF))
    ap.add_argument("--year", type=int, default=2040)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", type=Path, default=Path("profile_tmp.nc"))
    args = ap.parse_args()

    import dask

    dask.config.set(scheduler="threads", num_workers=args.workers)

    weights = xr.open_dataset(args.weights)
    n_target = weights.sizes["n_b"]

    ensemble = next(e for e in ENSEMBLES if args.ensemble.lower() in e.name.lower())
    month_1 = _members(ensemble)[0]
    cesm = CESM_OF[args.variable]
    window = ((args.year, 1), (args.year, 12))
    paths = _window_paths(month_1, cesm, window)

    probe = xr.open_dataset(paths[0], decode_timedelta=True)[cesm]
    depth = depth_dim(probe)
    levels = probe.sizes[depth] if depth else 1
    chunk = time_chunk(levels)

    print(f"{cesm}: {len(paths)} file(s), {levels} level(s)")
    print(f"dask: {chunk} months/chunk, {args.workers} workers")
    print(f"netCDF internal chunking: {probe.encoding.get('chunksizes')}")
    print(f"netCDF compression: zlib={probe.encoding.get('zlib')}")

    def _year(dataset):
        return centre_time(dataset)[cesm].sel(
            time=slice(f"{args.year}-01", f"{args.year}-12")
        )

    start = time.perf_counter()
    raw = _year(
        xr.open_mfdataset(
            paths, combine="by_coords", decode_timedelta=True, chunks={"time": chunk}
        )
    )
    t_open = time.perf_counter() - start

    start = time.perf_counter()
    loaded = raw.compute()
    t_read = time.perf_counter() - start
    gb = loaded.nbytes / 1e9

    # Re-open so the regrid does its own reading, as the writer does.
    raw = _year(
        xr.open_mfdataset(
            paths, combine="by_coords", decode_timedelta=True, chunks={"time": chunk}
        )
    )
    start = time.perf_counter()
    regridded = unflatten(
        regrid_variable(
            args.variable, _to_cells(convert_variable(cesm, raw)), weights, n_target
        )
    ).compute()
    t_regrid = time.perf_counter() - start

    start = time.perf_counter()
    xr.Dataset({args.variable: regridded}).to_netcdf(
        args.out, encoding={args.variable: COMPRESSION}
    )
    t_write = time.perf_counter() - start
    args.out.unlink(missing_ok=True)

    print(f"\n  one year = {gb:.2f} GB read")
    print(f"  open        {t_open:7.1f} s")
    print(f"  read only   {t_read:7.1f} s   ({gb / max(t_read, 1e-9):.2f} GB/s)")
    print(f"  read+regrid {t_regrid:7.1f} s")
    print(f"  write       {t_write:7.1f} s")
    print(f"\n  regrid beyond reading: {max(t_regrid - t_read, 0):.1f} s")
    print(f"  whole variable is 35x: ~{(t_regrid + t_write) * 35 / 60:.0f} min")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
