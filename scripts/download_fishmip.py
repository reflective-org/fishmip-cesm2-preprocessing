#!/usr/bin/env python3
"""Download the CESM2 FishMIP forcing from the public bucket.

    python3 download_fishmip.py --list
    python3 download_fishmip.py --variable intpp
    python3 download_fishmip.py --scenario g6-1p5k-mcb --out-dir ./forcing
    python3 download_fishmip.py                       # everything, ~280 GB

Standard library only -- no pip install, no credentials, no AWS tooling. Reads
are public, so each file is a plain HTTPS GET.

Interrupting is safe. A re-run skips files already complete and resumes any
that were cut off partway, so there is no need to start over.

Filenames are predictable, so nothing is listed from the bucket; the set below
is the whole published collection.
"""

import argparse
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://pub-d127229e707d485c80965ab41706e316.r2.dev/fishmip"

# Each SRM scenario must be compared against the baseline that shares its
# model. Both baselines are ssp245 and are told apart by the model token.
ENSEMBLES = [
    ("cesm2-waccm6", "ssp245", 10),  # baseline for SAI
    ("cesm2-waccm6", "g6-1p5k-sai", 3),
    ("cesm2-cam6", "ssp245", 16),  # baseline for MCB
    ("cesm2-cam6", "g6-1p5k-mcb", 5),
]

VARIABLES = [
    "intpp",  # primary production
    "thetao",  # temperature, full depth
    "tob",  # temperature at the seafloor
    "expc-bot",  # POC flux to the seafloor
    "no3",  # nitrate, full depth
    "phyc",  # small phytoplankton carbon, top 150 m
    "phydiat",  # diatom carbon, top 150 m
    "zooc",  # zooplankton carbon, top 150 m
    "zoo-loss",  # zooplankton loss, vertically integrated
]

# No time axis, identical for every member and scenario.
FIXED = ["deptho", "thkcello"]

CHUNK = 1 << 20

# Cloudflare rejects Python's default urllib User-Agent with a 403, so every
# request needs one of its own. Without this the script fails on every file and
# the reason is not visible from the error.
USER_AGENT = (
    "fishmip-download/1.0 "
    "(+https://github.com/reflective-org/fishmip-cesm2-preprocessing)"
)


def _request(url: str, **kwargs) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    return urllib.request.Request(url, headers=headers, **kwargs)


def manifest(scenario=None, variable=None, member=None):
    """Every published file, or the subset asked for. Returns (url, filename)."""
    wanted = []
    for model, experiment, members in ENSEMBLES:
        if scenario and experiment != scenario:
            continue
        for index in range(1, members + 1):
            number = f"{index:03d}"
            if member and number != member:
                continue
            for name in VARIABLES:
                if variable and name != variable:
                    continue
                filename = (
                    f"{model}_{experiment}_{number}_{name}"
                    "_onedeg_global_monthly_2035_2069.nc"
                )
                wanted.append((f"{BASE}/{experiment}/{filename}", filename))

    # The grid fields come with any request that did not name a different
    # variable: nothing else carries depth or layer thickness.
    for name in FIXED:
        if variable and variable != name:
            continue
        if scenario or member:
            continue
        filename = f"cesm2_{name}_onedeg_global_fx.nc"
        wanted.append((f"{BASE}/grid/{filename}", filename))
    return wanted


def remote_size(url: str) -> int | None:
    try:
        with urllib.request.urlopen(_request(url, method="HEAD"), timeout=30) as r:
            return int(r.headers["Content-Length"])
    except (urllib.error.URLError, TypeError, ValueError):
        return None


def fetch(url: str, target: Path) -> str:
    """Download, resuming a partial file. Returns what happened."""
    try:
        with urllib.request.urlopen(_request(url, method="HEAD"), timeout=30) as r:
            expected = int(r.headers["Content-Length"])
    except urllib.error.HTTPError as error:
        # Say what the server said. A bare "unavailable" sent me looking at the
        # bucket when the problem was here.
        return f"HTTP {error.code} {error.reason}"
    except (urllib.error.URLError, TypeError, ValueError) as error:
        return f"could not reach: {error}"

    have = target.stat().st_size if target.exists() else 0
    if have == expected:
        return "present"
    if have > expected:
        have = 0  # longer than the source: start again

    headers = {"Range": f"bytes={have}-"} if have else {}
    request = _request(url, headers=headers)
    mode = "ab" if have else "wb"
    with urllib.request.urlopen(request, timeout=60) as response:
        with open(target, mode) as handle:
            while chunk := response.read(CHUNK):
                handle.write(chunk)

    if target.stat().st_size != expected:
        return "size mismatch"
    return "resumed" if have else "downloaded"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("fishmip-forcing"))
    parser.add_argument("--scenario", choices=["ssp245", "g6-1p5k-sai", "g6-1p5k-mcb"])
    parser.add_argument("--variable", choices=VARIABLES + FIXED)
    parser.add_argument("--member", help="a single member, e.g. 001")
    parser.add_argument(
        "--list", action="store_true", help="show what would be downloaded"
    )
    args = parser.parse_args()

    wanted = manifest(args.scenario, args.variable, args.member)
    if not wanted:
        print("nothing matches those options")
        return 2

    if args.list:
        for url, _ in wanted:
            print(url)
        print(f"\n{len(wanted)} file(s)")
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    print(f"{len(wanted)} file(s) into {args.out_dir}\n")

    failed = []
    for number, (url, filename) in enumerate(wanted, start=1):
        print(f"[{number}/{len(wanted)}] {filename} ... ", end="", flush=True)
        try:
            outcome = fetch(url, args.out_dir / filename)
        except (urllib.error.URLError, OSError) as error:
            outcome = f"failed: {error}"
        print(outcome)
        if outcome not in ("present", "downloaded", "resumed"):
            failed.append(filename)

    if failed:
        print(f"\n{len(failed)} file(s) did not complete. Re-run to retry:")
        for name in failed[:10]:
            print(f"  {name}")
        return 1
    print("\nall files present")
    return 0


if __name__ == "__main__":
    sys.exit(main())
