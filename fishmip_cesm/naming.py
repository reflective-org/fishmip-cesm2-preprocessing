"""Output filenames and R2 object keys.

The filename pattern below follows ISIMIP3b/FishMIP forcing conventions:

    <model>_<scenario>_<member>_<variable>_onedeg_global_monthly_<start>_<end>.nc

**This is a proposal awaiting confirmation.** The scenario tokens in particular
have no established FishMIP spelling -- G6-1.5K-SAI and G6-1.5K-MCB postdate the
protocol -- so Kelsey Roberts and Colleen Petrik should sign off before anything
is published under these names. Renaming published files is worse than naming
them right, because other people's scripts will already refer to them.

Everything about the convention lives in this one module so changing it is a
single edit.
"""

import re

BUCKET = "reflective-data-store"
PREFIX = "fishmip"

RESOLUTION = "onedeg"
REGION = "global"
FREQUENCY = "monthly"

_UNSAFE = re.compile(r"[^a-z0-9-]+")


def _token(value: str) -> str:
    """Lowercase a token and strip anything that needs escaping in a URL.

    Dots become hyphens: CESM2.1-CAM6 -> cesm2-1-cam6, G6-1.5K-SAI ->
    g6-1p5k-sai. The decimal point in a scenario name is spelled `p` because
    that is how CESM writes it in case names, and dropping it entirely would
    collide 1.5K with 15K.
    """
    value = value.lower().replace(".", "p") if _has_decimal(value) else value.lower()
    value = value.replace(".", "-")
    return _UNSAFE.sub("-", value).strip("-")


def _has_decimal(value: str) -> bool:
    """True when a dot sits between two digits, as in 1.5K but not CESM2.1."""
    return bool(re.search(r"\d\.\d", value))


def output_filename(
    model: str,
    scenario: str,
    member: str,
    variable: str,
    start_year: int,
    end_year: int,
) -> str:
    """The published filename for one variable of one member."""
    parts = [
        _token(model),
        _token(scenario),
        _token(member),
        _token(variable),
        RESOLUTION,
        REGION,
        FREQUENCY,
        str(start_year),
        str(end_year),
    ]
    return "_".join(parts) + ".nc"


def object_key(scenario: str, filename: str) -> str:
    """Where a file lives in the bucket.

    Grouped by scenario so a modeller can fetch one experiment without listing
    the whole prefix.
    """
    if "/" in filename or filename.startswith("."):
        raise ValueError(f"unsafe filename: {filename!r}")
    return f"{PREFIX}/{_token(scenario)}/{filename}"
