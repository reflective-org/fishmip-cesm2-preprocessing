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
CMIP6 = Path("/glade/campaign/collections/cmip/CMIP6/timeseries-cmip6")
# The Large Ensemble stores one directory per variable rather than per member,
# so its root is the month_1 directory itself. See sources.py.
CESM2_LE = Path(
    "/glade/campaign/cesm/collections/CESM2-LE/timeseries/ocn/proc/tseries/month_1"
)

# Historical is the CMIP6 span. piControl is a model-year control with no
# calendar: the WACCM run covers years 1-499 and the CAM6 one 1-2000, and the
# last 200 years of each were requested (Dan Visioni, 2026-10-09) -- long
# enough to be useful and far enough from spin-up to be stable.
HISTORICAL_WINDOW: Span = ((1850, 1), (2014, 12))
WACCM_PICONTROL_WINDOW: Span = ((300, 1), (499, 12))
CAM6_PICONTROL_WINDOW: Span = ((1801, 1), (2000, 12))

# MCB ends 2069 while SAI runs to 2084, so the three-way comparison caps here.
# This is the scenario window; historical and piControl carry their own.
ANALYSIS_WINDOW: Span = ((2035, 1), (2069, 12))

# The baseline is not an SRM run. SAI and MCB begin in 2035, but ssp245 begins
# when the scenario does, in 2015, and runs to 2100 as the archive holds it.
# Starting it at 2035 to match the SRM runs left a twenty-year hole between the
# end of historical and the start of the scenario -- precisely where the two
# are meant to join into one continuous record. The SRM comparison uses the
# 2035-2069 slice of this; nothing is lost by carrying the rest.
BASELINE_WINDOW: Span = ((2015, 1), (2100, 12))


def months_in(window: Span) -> int:
    (start_year, start_month), (end_year, end_month) = window
    return (end_year - start_year) * 12 + (end_month - start_month) + 1

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
    #: Human-readable label. Used in logs and reports, never in filenames.
    name: str
    #: Human-readable model description.
    model: str
    #: CMIP-style identifiers. These are what appear in published filenames and
    #: object keys, so they must be stable, lowercase and meaningful to someone
    #: who has never seen this repository. Display labels are not identifiers:
    #: "SSP2-4.5 (WACCM baseline)" would publish as ssp2-4p5-waccm-baseline.
    source_id: str
    experiment_id: str
    root: Path
    case_glob: str
    #: Every ensemble states its own span. Historical is 1850-2014 and
    #: piControl is a model-year control, so no single window covers the set.
    window: Span = ANALYSIS_WINDOW
    #: "case" -- one directory per member, holding all its variables.
    #: "variable" -- one directory per variable, holding all members, which is
    #: how the CESM2 Large Ensemble is stored. See sources.py.
    layout: str = "case"


ENSEMBLES = [
    Ensemble(
        name="SSP2-4.5 (WACCM baseline)",
        model="CESM2-WACCM6",
        source_id="cesm2-waccm6",
        experiment_id="ssp245",
        root=GDEX / "d651045" / "CESM2-WACCM-SSP245",
        # Members 001-005 only. 006 stops at 2070 and 007-010 at 2069, so they
        # cannot cover the baseline window; including them would write short
        # files. Carrying them to 2069 alongside the others would also halve
        # the ensemble at 2070, narrowing its spread for a reason that is not
        # physical. The CAM6 baseline has all 16 members to 2100 and is not
        # restricted.
        case_glob="b.e21.BWSSP245cmip6.f09_g17.CMIP6-SSP2-4.5-WACCM.00[1-5]",
        window=BASELINE_WINDOW,
    ),
    Ensemble(
        name="G6-1.5K-SAI",
        model="CESM2-WACCM6",
        source_id="cesm2-waccm6",
        experiment_id="g6-1p5k-sai",
        # Lives inside the GDEX dataset labelled ARISE-SAI-1.5, alongside the
        # ARISE runs proper. The glob must not pick those up.
        root=GDEX / "d651059" / "ARISE-SAI-1.5",
        case_glob=f"b.e21.BW.f09_g17.SSP245-G6-1p5K-SAI.{_MEMBER}",
    ),
    Ensemble(
        name="SSP2-4.5 (CAM6 baseline)",
        model="CESM2.1-CAM6",
        source_id="cesm2-cam6",
        experiment_id="ssp245",
        # Case directories nest inside a container directory of the same name.
        root=GDEX / "d651073" / "b.e21.BSSP245smbb.f09_g17",
        case_glob=f"b.e21.BSSP245smbb.f09_g17.{_MEMBER}",
        window=BASELINE_WINDOW,
    ),
    Ensemble(
        name="historical (WACCM)",
        model="CESM2-WACCM6",
        source_id="cesm2-waccm6",
        experiment_id="historical",
        root=CMIP6,
        case_glob=f"b.e21.BWHIST.f09_g17.CMIP6-historical-WACCM.{_MEMBER}",
        window=HISTORICAL_WINDOW,
    ),
    Ensemble(
        name="piControl (WACCM)",
        model="CESM2-WACCM6",
        source_id="cesm2-waccm6",
        experiment_id="picontrol",
        root=CMIP6,
        case_glob=f"b.e21.BW1850.f09_g17.CMIP6-piControl.{_MEMBER}",
        window=WACCM_PICONTROL_WINDOW,
    ),
    Ensemble(
        name="piControl (CAM6)",
        model="CESM2.1-CAM6",
        source_id="cesm2-cam6",
        experiment_id="picontrol",
        root=CMIP6,
        case_glob=f"b.e21.B1850.f09_g17.CMIP6-piControl.{_MEMBER}",
        window=CAM6_PICONTROL_WINDOW,
    ),
    Ensemble(
        name="historical (CAM6)",
        model="CESM2.1-CAM6",
        source_id="cesm2-cam6",
        experiment_id="historical",
        # smbb, not cmip6: the MCB runs and the CAM6 baseline are both
        # BSSP245smbb, and the two variants differ in biomass-burning forcing
        # from 1990. A cmip6 historical would leave a forcing discontinuity at
        # the 2014/2015 join -- small, and later indistinguishable from signal.
        #
        # One member, pinned by name (Dan Visioni, 2026-10-09: "one ensemble
        # member is fine"). Pinning rather than globbing keeps the member label
        # unambiguous: LE2-1011.001 and LE2-1031.002 would both be plausible
        # matches for a looser pattern.
        root=CESM2_LE,
        case_glob="b.e21.BHISTsmbb.f09_g17.LE2-1011.001",
        window=HISTORICAL_WINDOW,
        layout="variable",
    ),
]


# Configured but not produced. Kept here rather than deleted so the archive
# details survive, and out of ENSEMBLES so nothing iterates over them.
#
# G6-1.5K-MCB: the walkerl path below holds a different set of Walker
# simulations, not the G6 MCB runs (Dan Visioni, 2026-10-23). 45 files were
# published from it under the g6-1p5k-mcb prefix and have been withdrawn.
# Restoring this needs only the corrected root; the rest should still hold.
WITHHELD = [
    Ensemble(
        name="G6-1.5K-MCB",
        model="CESM2.1-CAM6",
        source_id="cesm2-cam6",
        experiment_id="g6-1p5k-mcb",
        # feedback, not feedforward: the scenario uses a PI controller.
        root=CAMPAIGN / "MCB_feedback_1DOF_smbb",
        case_glob=f"b.e21.BSSP245smbb.f09_g17.MCB-feedback-1DOF.{_MEMBER}",
    ),
]
