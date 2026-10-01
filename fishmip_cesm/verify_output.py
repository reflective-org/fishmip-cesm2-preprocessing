"""Check written files on disk, before anything is published.

    python -m fishmip_cesm.verify_output [--out-dir output] [--delete-bad]

The gate in stage 8 validates data in memory on its way out. This validates what
actually landed: a file can be truncated by a killed job, or mangled by two
processes writing it at once, and neither leaves a trace in the run log.

Reports every file as ok, incomplete, or bad, and with --delete-bad removes the
ones that fail so a re-run rewrites them.
"""

import argparse
import sys
from pathlib import Path

import xarray as xr

from fishmip_cesm.ensembles import ANALYSIS_WINDOW
from fishmip_cesm.validate import (
    PLAUSIBLE_RANGES,
    check_range,
    check_time_coverage,
    check_units,
    gate_passed,
)


def _variable_of(dataset: xr.Dataset) -> str | None:
    """The one FishMIP variable a forcing file carries."""
    known = [n for n in dataset.data_vars if n in PLAUSIBLE_RANGES]
    return known[0] if len(known) == 1 else None


def verify(path: Path, deep: bool = False) -> tuple[str, str]:
    """Return (verdict, detail) for one written file.

    Shallow by default: the first timestep only, which is fast and catches a
    truncated or unreadable file. `deep` reads every chunk, which is the only
    way to see corruption or bad values later in the file -- a damaged file
    passed the shallow check and then failed on write with a decompression
    error. Slow, but it is the gate before publication.
    """
    try:
        dataset = xr.open_dataset(path)
    except (OSError, ValueError) as error:
        return "bad", f"cannot open: {type(error).__name__}"

    with dataset:
        name = _variable_of(dataset)
        if name is None:
            return "bad", f"no recognised variable in {list(dataset.data_vars)}"

        field = dataset[name]
        checks = [
            check_time_coverage(field, ANALYSIS_WINDOW),
            check_units(name, field),
        ]
        # Range is read from a single timestep: enough to catch a mangled file,
        # and reading every month of every file would cost as much as writing
        # them did.
        try:
            if deep:
                # Touches every chunk, so a decompression failure surfaces here
                # rather than in whatever reads the file next.
                sample = field
            else:
                sample = field.isel(time=0)
                depth = [d for d in sample.dims if d.startswith("z") or d == "lev"]
                if depth:
                    sample = sample.isel({d: 0 for d in depth})
            checks.append(check_range(name, sample.load()))
        except (OSError, ValueError, RuntimeError) as error:
            return "bad", f"cannot read values: {type(error).__name__}: {error}"

        if gate_passed(checks):
            return "ok", f"{name}, {field.sizes['time']} months"
        failed = [c for c in checks if not c.passed]
        verdict = "incomplete" if any("time" in c.name for c in failed) else "bad"
        return verdict, "; ".join(f"{c.name}: {c.detail}" for c in failed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--deep",
        action="store_true",
        help="read every chunk rather than the first timestep. Slow -- a full "
        "read of the whole set -- but the only way to catch corruption later "
        "in a file. Use before publishing.",
    )
    parser.add_argument(
        "--delete-bad",
        action="store_true",
        help="remove files that fail, so a re-run rewrites them",
    )
    args = parser.parse_args()

    paths = sorted(args.out_dir.glob("*.nc"))
    if not paths:
        print(f"no files in {args.out_dir}")
        return 2

    tally = {"ok": 0, "incomplete": 0, "bad": 0}
    for path in paths:
        verdict, detail = verify(path, deep=args.deep)
        tally[verdict] += 1
        if verdict != "ok":
            print(f"{verdict.upper():10s} {path.name}")
            print(f"           {detail}")
            if args.delete_bad:
                path.unlink()
                print("           deleted")

    print(
        f"\n{len(paths)} file(s): {tally['ok']} ok, "
        f"{tally['incomplete']} incomplete, {tally['bad']} bad"
    )
    if tally["incomplete"] or tally["bad"]:
        if not args.delete_bad:
            print("re-run with --delete-bad to remove them, then re-run the writer")
        return 1
    print("all files verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
