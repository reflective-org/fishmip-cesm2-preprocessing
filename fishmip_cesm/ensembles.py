"""The four CESM2 ensembles this project preprocesses.

Paths and coverage verified on GLADE, 2026-09-16/18. See
docs/specs/2026-09-16-fishmip-cesm2-preprocessing-design.md for provenance and
for the dead ends that are deliberately not listed here.
"""

from dataclasses import dataclass
from pathlib import Path

from fishmip_cesm.catalog import Span

GDEX = Path("/glade/campaign/collections/gdex/data")
CAMPAIGN = Path("/glade/campaign/cgd/amp/walkerl")

# MCB ends 2069 while SAI runs to 2084, so the three-way comparison caps here.
ANALYSIS_WINDOW: Span = ((2035, 1), (2069, 12))

# The eight MARBL fields the FishMIP variables derive from, plus temperature.
# Grid fields (KMT, HT, dz, z_w_top, z_w_bot) are coordinates inside each file,
# not separate timeseries, so they are not listed.
REQUIRED_VARIABLES = [
    "TEMP",
    # Primary production. The upstream spec proposed POC_PROD_zint +
    # DOC_prod_zint, which is detrital production and about a third of NPP;
    # photoC_TOT_zint is total carbon fixation and what CMIP6 maps to intpp.
    "photoC_TOT_zint",
    # Retained for comparison against photoC_TOT_zint, not used for intpp.
    "POC_PROD_zint",
    "DOC_prod_zint",
    "pocToSed",
    "NO3",
    "spC",
    "diatC",
    "zooC",
    "zoo_loss_zint",
]

# Member suffixes are matched as exactly three digits. This deliberately excludes
# extensions and variants that sit alongside the members proper -- the WACCM
# baseline has a `.006ext`, and the SAI collection has a `_2055_start.001`.
_MEMBER = "[0-9][0-9][0-9]"


@dataclass(frozen=True)
class Ensemble:
    name: str
    model: str
    root: Path
    case_glob: str


ENSEMBLES = [
    Ensemble(
        name="SSP2-4.5 (WACCM baseline)",
        model="CESM2-WACCM6",
        root=GDEX / "d651045" / "CESM2-WACCM-SSP245",
        case_glob=f"b.e21.BWSSP245cmip6.f09_g17.CMIP6-SSP2-4.5-WACCM.{_MEMBER}",
    ),
    Ensemble(
        name="G6-1.5K-SAI",
        model="CESM2-WACCM6",
        # Lives inside the GDEX dataset labelled ARISE-SAI-1.5, alongside the
        # ARISE runs proper. The glob must not pick those up.
        root=GDEX / "d651059" / "ARISE-SAI-1.5",
        case_glob=f"b.e21.BW.f09_g17.SSP245-G6-1p5K-SAI.{_MEMBER}",
    ),
    Ensemble(
        name="SSP2-4.5 (CAM6 baseline)",
        model="CESM2.1-CAM6",
        # Case directories nest inside a container directory of the same name.
        root=GDEX / "d651073" / "b.e21.BSSP245smbb.f09_g17",
        case_glob=f"b.e21.BSSP245smbb.f09_g17.{_MEMBER}",
    ),
    Ensemble(
        name="G6-1.5K-MCB",
        model="CESM2.1-CAM6",
        # feedback, not feedforward: the scenario uses a PI controller.
        root=CAMPAIGN / "MCB_feedback_1DOF_smbb",
        case_glob=f"b.e21.BSSP245smbb.f09_g17.MCB-feedback-1DOF.{_MEMBER}",
    ),
]
