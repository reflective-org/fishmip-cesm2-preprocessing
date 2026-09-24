"""Write the target SCRIP grid and the command that generates regrid weights.

    fishmip-make-weights [--out-dir DIR]

Weights are generated once, offline, by ESMF_RegridWeightGen. This writes the
FishMIP target grid in SCRIP format (the gx1v7 source already ships as SCRIP in
CESM inputdata) and prints the command to run.

Deliberately prints rather than runs: ESMF_RegridWeightGen lives behind a module
on Casper, often wants MPI, and takes long enough that it belongs in a job the
user controls rather than buried inside a Python call.
"""

import argparse
import sys
from pathlib import Path

from fishmip_cesm.regrid import fishmip_scrip_grid

# Official gx1v7 SCRIP description shipped with CESM.
GX1V7_SCRIP = Path(
    "/glade/campaign/cesm/cesmdata/inputdata/share/scripgrids/gx1v7_151008.nc"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("grids"))
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    target = args.out_dir / "fishmip_1deg_SCRIP.nc"
    weights = args.out_dir / "gx1v7_to_fishmip_1deg_conserve.nc"

    fishmip_scrip_grid().to_netcdf(target)
    print(f"wrote {target}")

    if not GX1V7_SCRIP.exists():
        print(f"\nWARNING: source grid not found at {GX1V7_SCRIP}")

    print(
        "\nNow generate the weights (on Casper):\n"
        "\n  module load conda && conda activate npl"
        "\n  ESMF_RegridWeightGen \\"
        f"\n      --source {GX1V7_SCRIP} \\"
        f"\n      --destination {target} \\"
        f"\n      --weight {weights} \\"
        "\n      --method conserve \\"
        "\n      --src_regional=false --dst_regional=false \\"
        "\n      --netcdf4"
        "\n"
        "\nconserve, not bilinear: intpp and expc-bot are fluxes and their"
        "\nglobal integral has to survive the regrid."
        "\n"
        "\nThen check the result with:"
        "\n  fishmip-check-regrid --weights " + str(weights)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
