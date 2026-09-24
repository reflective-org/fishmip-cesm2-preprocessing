"""Write the target SCRIP grid and generate the regrid weights.

    python -m fishmip_cesm.make_weights [--run] [--out-dir DIR]

Weights are generated once, offline, by ESMF_RegridWeightGen. This writes the
FishMIP target grid in SCRIP format (the gx1v7 source already ships as SCRIP in
CESM inputdata) and either prints the command to run or, with --run, runs it.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from fishmip_cesm.regrid import fishmip_scrip_grid

# Official gx1v7 SCRIP description shipped with CESM.
GX1V7_SCRIP = Path(
    "/glade/campaign/cesm/cesmdata/inputdata/share/scripgrids/gx1v7_151008.nc"
)

TOOL = "ESMF_RegridWeightGen"


def weight_generation_command(
    source: Path,
    destination: Path,
    weight: Path,
) -> list[str]:
    """The ESMF invocation that produces conservative gx1v7 -> FishMIP weights.

    `conserve` is the load-bearing choice. `intpp` and `expc-bot` are fluxes,
    and bilinear interpolation would not preserve their global integral -- it
    would quietly change how much carbon reaches the fish models.

    `--ignore_unmapped` is required, not a workaround. gx1v7 is an *ocean* grid
    whose southern boundary follows the Antarctic coast near 79S, and its land
    cells are masked, so a global target grid necessarily contains cells with no
    source to draw from. Without this ESMF aborts on the first one. Those cells
    receive no weights and come back as NaN, which `apply_weights` preserves --
    the right answer for a point with no ocean in it.
    """
    return [
        TOOL,
        "--source", str(source),
        "--destination", str(destination),
        "--weight", str(weight),
        "--method", "conserve",
        "--ignore_unmapped",
        "--src_regional=false",
        "--dst_regional=false",
        "--netcdf4",
    ]


def _looks_like_an_interactive_session() -> bool:
    return not os.environ.get("PBS_JOBID")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("grids"))
    parser.add_argument(
        "--run",
        action="store_true",
        help=f"run {TOOL} instead of printing the command",
    )
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / "fishmip_1deg_SCRIP.nc"
    weights = args.out_dir / "gx1v7_to_fishmip_1deg_conserve.nc"

    fishmip_scrip_grid().to_netcdf(target)
    print(f"wrote {target}")

    if not GX1V7_SCRIP.exists():
        print(f"\nsource grid not found at {GX1V7_SCRIP}")
        return 2

    command = weight_generation_command(GX1V7_SCRIP, target, weights)

    if not args.run:
        print("\nNow generate the weights:\n")
        print("  " + " \\\n      ".join(command))
        print("\nOr re-run this with --run to do it here.")
        return 0

    if shutil.which(TOOL) is None:
        print(
            f"\n{TOOL} not found on PATH."
            "\nTry: module load conda && conda activate npl"
            "\n or: module avail esmf"
        )
        return 2

    if _looks_like_an_interactive_session():
        print(
            "\nnote: PBS_JOBID is unset, so this looks like a login or"
            "\ninteractive session. gx1v7 -> 1 degree is small enough to be fine"
            "\nhere, but larger grids belong in a batch job."
        )

    print(f"\nrunning {TOOL} (a few minutes)...\n")
    result = subprocess.run(command)
    if result.returncode != 0:
        print(
            f"\n{TOOL} exited {result.returncode}."
            "\nCheck PET0.RegridWeightGen.Log in the working directory."
            "\n"
            "\nIf it reports degenerate cells, add --ignore_degenerate to"
            "\nweight_generation_command. gx1v7 is a tripole grid and can have"
            "\ncollapsed cells at the northern fold. Read the log first though:"
            "\nthat flag suppresses a real category of grid problem."
        )
        return result.returncode

    print(f"\nwrote {weights}")
    print(
        "\nNow verify it conserves:"
        f"\n  python -m fishmip_cesm.check_regrid --weights {weights}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
