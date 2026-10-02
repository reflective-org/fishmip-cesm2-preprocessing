# Downloading the FishMIP forcing

The files are public for reading. No credentials, no account, no SDK needed — each file
is a plain HTTPS GET.

```python
BASE = "https://pub-d127229e707d485c80965ab41706e316.r2.dev/fishmip"
```

## How files are named

Nothing needs listing: every filename is predictable from what you want.

```
{BASE}/{experiment}/{model}_{experiment}_{member}_{variable}_onedeg_global_monthly_2035_2069.nc
```

| Field | Values |
|---|---|
| `model` | `cesm2-waccm6` (SAI and its baseline), `cesm2-cam6` (MCB and its baseline) |
| `experiment` | `ssp245`, `g6-1p5k-sai`, `g6-1p5k-mcb` |
| `member` | `001`–`010` (WACCM baseline), `001`–`003` (SAI), `001`–`016` (CAM6 baseline), `001`–`005` (MCB) |
| `variable` | `intpp`, `thetao`, `tob`, `expc-bot`, `no3`, `phyc`, `phydiat`, `zooc`, `zoo-loss` |

Both baselines are `ssp245` and are told apart by `model` — they are the same scenario in
two model configurations, and **each SRM scenario must be compared against the baseline
that shares its model**.

The two time-invariant fields sit together and carry no scenario or member:

```
{BASE}/grid/cesm2_deptho_onedeg_global_fx.nc
{BASE}/grid/cesm2_thkcello_onedeg_global_fx.nc
```

## Python

```python
from pathlib import Path
import requests

BASE = "https://pub-d127229e707d485c80965ab41706e316.r2.dev/fishmip"

MODEL_OF = {
    "ssp245-waccm": "cesm2-waccm6",
    "g6-1p5k-sai": "cesm2-waccm6",
    "ssp245-cam6": "cesm2-cam6",
    "g6-1p5k-mcb": "cesm2-cam6",
}


def url_for(experiment: str, member: str, variable: str, model: str) -> str:
    name = (
        f"{model}_{experiment}_{member}_{variable}"
        "_onedeg_global_monthly_2035_2069.nc"
    )
    return f"{BASE}/{experiment}/{name}"


def download(url: str, into: Path = Path(".")) -> Path:
    """Stream to disk. The 60-level files are a few GB each."""
    target = into / url.rsplit("/", 1)[-1]
    if target.exists():
        return target
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(target, "wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
    return target


# One variable, one member, matched scenario and baseline.
sai = download(url_for("g6-1p5k-sai", "001", "intpp", "cesm2-waccm6"))
ref = download(url_for("ssp245", "001", "intpp", "cesm2-waccm6"))

import xarray as xr

print(xr.open_dataset(sai))
```

Every file carries its own provenance. `history` names the CESM variable it came from and
what was done to it, which matters for `intpp` in particular — it derives from
`photoC_TOT_zint`, not from the `POC_PROD_zint + DOC_prod_zint` sum the original project
plan specified:

```python
print(xr.open_dataset(sai).attrs["history"])
```

## Shell

```bash
BASE=https://pub-d127229e707d485c80965ab41706e316.r2.dev/fishmip

curl -O "$BASE/g6-1p5k-mcb/cesm2-cam6_g6-1p5k-mcb_001_intpp_onedeg_global_monthly_2035_2069.nc"

# all five MCB members of one variable
for m in 001 002 003 004 005; do
  curl -O "$BASE/g6-1p5k-mcb/cesm2-cam6_g6-1p5k-mcb_${m}_intpp_onedeg_global_monthly_2035_2069.nc"
done
```

## What to expect in the data

- **Grid** — regular 1°, 360 × 180, cell centres on half degrees, latitude ascending.
- **Time** — 420 monthly steps, 2035-01 to 2069-12, stamped mid-month.
- **Missing values** — NaN over land and below the seafloor. `thkcello` is missing below
  the seafloor rather than zero there.
- **Depth** — `no3` and `thetao` are full depth (60 levels). `phyc`, `phydiat` and `zooc`
  are the **top 150 m only** (15 levels), because that is all MARBL writes.
- **Extremes are grid-scale averages.** The regrid is conservative, so global integrals
  are preserved exactly but peaks are damped — gx1v7 is finer than 1° near the equator.
  Read maxima as 1° averages, not as CESM2's own.

## A quick check that a file is there

Reads are public, so a `HEAD` is enough to confirm a file exists and how large it is
without downloading it:

```bash
curl -sI "$BASE/g6-1p5k-mcb/cesm2-cam6_g6-1p5k-mcb_001_intpp_onedeg_global_monthly_2035_2069.nc" \
  | grep -i '^\(HTTP\|content-length\)'
```
