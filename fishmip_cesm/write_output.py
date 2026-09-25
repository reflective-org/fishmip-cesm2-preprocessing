"""Produce the FishMIP forcing files. Dry run by default.

    python -m fishmip_cesm.write_output --weights WEIGHTS [--write] [--out-dir DIR]

Without --write this reads directory listings only -- nothing is opened,
decoded or held -- and prints what it would produce and how large it would be.
The full set at full depth runs to hundreds of gigabytes, so knowing the shape
of the job before starting it is worth a few seconds.

With --write, fields stream through the regrid a year at a time. A full-depth
variable over the analysis window is around 25 GB, so it is never held whole.

Every file goes through the stage 8 gate before it is written. A variable that
fails is skipped and reported; it is not written and then corrected, because the
destination is a public bucket and a withdrawn file is worse than a late one.
"""

import argparse
import sys
from pathlib import Path

import xarray as xr

from fishmip_cesm.catalog import parse_timeseries_filename
from fishmip_cesm.ensembles import ANALYSIS_WINDOW, ENSEMBLES
from fishmip_cesm.naming import BUCKET
from fishmip_cesm.output import to_fishmip_dataset, unflatten
from fishmip_cesm.plan import plan_output
from fishmip_cesm.regrid import regrid_variable
from fishmip_cesm.transform import (
    CONVERSIONS,
    convert_variable,
    depth_dim,
    derive_tob,
    subset_to_window,
)
from fishmip_cesm.validate import (
    clip_negatives,
    format_report,
    gate_passed,
    may_be_negative,
    validate_variable,
)

# CESM source -> FishMIP name, for everything that converts directly. tob is
# derived from TEMP separately.
DIRECT_SOURCES = [
    "photoC_TOT_zint",
    "pocToSed",
    "zoo_loss_zint",
    "TEMP",
    "NO3",
    "spC",
    "diatC",
    "zooC",
]

# Depth levels each variable carries, for planning. Verified against the data
# when the file is actually written.
EXPECTED_LEVELS = {
    "intpp": 1,
    "expc-bot": 1,
    "zoo_loss": 1,
    "tob": 1,
    "thetao": 60,
    "no3": 60,
    "phyc": 15,
    "phydiat": 15,
    "zooc": 15,
}

# float32 is what the plan's size estimate assumes and what CMIP writes. The
# regrid works in float64, so without this every file is twice the planned size
# and deflate spends its effort on digits that carry no information.
COMPRESSION = {"zlib": True, "complevel": 4, "dtype": "float32"}


def _fishmip_name(cesm_name: str) -> str:
    return CONVERSIONS[cesm_name][0]


def _members(ensemble) -> list[Path]:
    found = []
    for case_dir in sorted(ensemble.root.glob(ensemble.case_glob)):
        month_1 = case_dir / "ocn" / "proc" / "tseries" / "month_1"
        if month_1.is_dir():
            found.append(month_1)
    return found


def _member_label(month_1: Path) -> str:
    """The three-digit member suffix from the case directory name."""
    return month_1.parents[3].name.rsplit(".", 1)[-1]


def _window_paths(month_1: Path, variable: str, window) -> list[Path]:
    """The timeseries chunks covering the window, without opening any of them."""
    (start_year, _), (end_year, _) = window
    paths = []
    for path in sorted(month_1.glob(f"*.pop.h.{variable}.*.nc")):
        parsed = parse_timeseries_filename(path.name)
        if parsed and parsed.start[0] <= end_year and parsed.end[0] >= start_year:
            paths.append(path)
    return paths


def _open_window(month_1: Path, variable: str, window) -> xr.DataArray | None:
    """Concatenate whichever timeseries chunks cover the analysis window."""
    paths = _window_paths(month_1, variable, window)
    if not paths:
        return None
    # Chunk along time only: the regrid needs the horizontal axes whole, and a
    # year of a 60-level field is about 700 MB.
    data = xr.open_mfdataset(
        paths, combine="by_coords", decode_timedelta=True, chunks={"time": 12}
    )[variable]
    return subset_to_window(data, window)


def _to_cells(field: xr.DataArray) -> xr.DataArray:
    """Collapse the POP horizontal dimensions into a single flat cell axis."""
    horizontal = [d for d in field.dims if d in ("nlat", "nlon")]
    stacked = field.stack(cell=horizontal)
    return stacked.transpose(*[d for d in stacked.dims if d != "cell"], "cell")


def write_variable(
    fishmip_name: str,
    native: xr.DataArray,
    cesm_source: str,
    ensemble,
    member: str,
    weights: xr.Dataset,
    n_target: int,
    ocean: xr.DataArray,
    out_dir: Path,
    write: bool,
) -> bool:
    """Regrid, gate and optionally write one variable for one member."""
    plan = plan_output(
        model=ensemble.source_id,
        scenario=ensemble.experiment_id,
        member=member,
        variable=fishmip_name,
        window=ANALYSIS_WINDOW,
        levels=EXPECTED_LEVELS.get(fishmip_name, 1),
    )
    if not write:
        # Nothing is computed on a dry run. Regridding first and then deciding
        # not to write would load ~25 GB for a full-depth variable.
        print(f"  would write {plan.filename}  (~{plan.gigabytes:.2f} GB)")
        print(f"            -> s3://{BUCKET}/{plan.key}")
        return True

    flat = _to_cells(native)
    regridded = regrid_variable(fishmip_name, flat, weights, n_target)
    regridded.attrs = dict(native.attrs)

    notes = ""
    if not may_be_negative(fishmip_name):
        attrs = dict(regridded.attrs)
        regridded, clip = clip_negatives(fishmip_name, regridded)
        regridded.attrs = attrs
        if clip.cells:
            notes = (
                f"{clip.cells} negative cell(s) clipped to zero "
                f"({clip.removed_fraction:.4%} of the field)"
            )

    # The gate sees a representative slice; checking every timestep would read
    # the whole field twice for no additional signal on range or units.
    sample = regridded.isel(
        {d: 0 for d in regridded.dims if d != "cell"}, missing_dims="ignore"
    )
    checks = validate_variable(fishmip_name, sample, ocean)
    if not gate_passed(checks):
        print(f"  {fishmip_name}: FAILED the gate, not written")
        print(format_report(checks))
        return False

    if notes:
        print(f"  {fishmip_name}: {notes}")

    field = unflatten(regridded)
    field.attrs = dict(native.attrs)
    dataset = to_fishmip_dataset(
        fishmip_name,
        field,
        # source_id and experiment_id are CMIP identifiers, not descriptions;
        # the human-readable labels go in the title.
        model=ensemble.source_id,
        scenario=ensemble.experiment_id,
        member=member,
        cesm_source=cesm_source,
        notes=notes,
        description=f"{ensemble.model} {ensemble.name}",
    )
    dataset = dataset.assign_coords(time=native["time"])
    target = out_dir / plan.filename
    target.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_netcdf(target, encoding={fishmip_name: COMPRESSION})
    print(f"  wrote {target} ({target.stat().st_size / 1e9:.2f} GB)")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    parser.add_argument("--ensemble", help="substring of an ensemble name")
    parser.add_argument("--member", help="a single member, e.g. 001")
    parser.add_argument("--variable", help="a single FishMIP variable")
    parser.add_argument(
        "--write", action="store_true", help="actually write files (default: dry run)"
    )
    args = parser.parse_args()

    if not args.weights.exists():
        print(f"weight file not found: {args.weights}")
        return 2
    weights = xr.open_dataset(args.weights)
    n_target = weights.sizes["n_b"]

    selected = [
        e
        for e in ENSEMBLES
        if not args.ensemble or args.ensemble.lower() in e.name.lower()
    ]
    if not selected:
        print(f"no ensemble matching {args.ensemble!r}")
        return 2

    if not args.write:
        print("DRY RUN -- nothing will be written. Pass --write to produce files.\n")

    total_gb = 0.0
    failures = 0
    for ensemble in selected:
        for month_1 in _members(ensemble):
            member = _member_label(month_1)
            if args.member and member != args.member:
                continue
            print(f"\n{ensemble.name} member {member}")

            work: list[tuple[str, str, xr.DataArray | None]] = []
            ocean = None

            if not args.write:
                # A dry run reads directory listings only. Nothing is opened,
                # decoded or held, so it costs neither time nor memory.
                for cesm_name in DIRECT_SOURCES:
                    if not _window_paths(month_1, cesm_name, ANALYSIS_WINDOW):
                        print(f"  {cesm_name}: not found")
                        failures += 1
                        continue
                    work.append((_fishmip_name(cesm_name), cesm_name, None))
                work.append(("tob", "TEMP", None))
            else:
                temperature = _open_window(month_1, "TEMP", ANALYSIS_WINDOW)
                if temperature is None:
                    print("  no TEMP, skipping")
                    failures += 1
                    continue
                grid = xr.open_dataset(
                    sorted(month_1.glob("*.pop.h.TEMP.*.nc"))[0], decode_timedelta=True
                )
                kmt = grid["KMT"]
                ocean = (
                    regrid_variable(
                        "thetao",
                        _to_cells(xr.ones_like(kmt).where(kmt > 0)),
                        weights,
                        n_target,
                    )
                    .notnull()
                    .compute()
                )
                for cesm_name in DIRECT_SOURCES:
                    raw = (
                        temperature
                        if cesm_name == "TEMP"
                        else _open_window(month_1, cesm_name, ANALYSIS_WINDOW)
                    )
                    if raw is None:
                        print(f"  {cesm_name}: not found, skipping")
                        failures += 1
                        continue
                    work.append(
                        (
                            _fishmip_name(cesm_name),
                            cesm_name,
                            convert_variable(cesm_name, raw),
                        )
                    )
                work.append(("tob", "TEMP", derive_tob(temperature, kmt)))

            for fishmip_name, cesm_source, field in work:
                if args.variable and fishmip_name != args.variable:
                    continue
                levels = EXPECTED_LEVELS.get(fishmip_name, 1)
                if field is not None:
                    depth = depth_dim(field)
                    if depth is not None and field.sizes[depth] != levels:
                        print(
                            f"  {fishmip_name}: expected {levels} levels, "
                            f"found {field.sizes[depth]} on {depth}"
                        )
                ok = write_variable(
                    fishmip_name,
                    field,
                    cesm_source,
                    ensemble,
                    member,
                    weights,
                    n_target,
                    ocean,
                    args.out_dir,
                    args.write,
                )
                if ok:
                    total_gb += plan_output(
                        model=ensemble.source_id,
                        scenario=ensemble.experiment_id,
                        member=member,
                        variable=fishmip_name,
                        window=ANALYSIS_WINDOW,
                        levels=levels,
                    ).gigabytes
                else:
                    failures += 1

    verb = "wrote" if args.write else "would write"
    print(f"\n{verb} approximately {total_gb:.1f} GB uncompressed")
    if failures:
        print(f"{failures} variable(s) failed or were missing.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
