# CESM2 → FishMIP preprocessing

Converts raw CESM2 POP2/MARBL ocean output into FishMIP-conformant forcing for
BOATS and FEISTY, across an SSP2-4.5 baseline and two SRM scenarios (SAI, MCB).

Design: [docs/specs/2026-09-16-fishmip-cesm2-preprocessing-design.md](docs/specs/2026-09-16-fishmip-cesm2-preprocessing-design.md)

## Install

```
pip install -e .
```

On Derecho/Casper, do this inside a conda environment (`module load conda`), not
against the system Python.

## Stage 1: verify inputs

All source data is on GLADE at NCAR. Before preprocessing anything, confirm every
ensemble supplies every required variable with **contiguous** monthly coverage
across the analysis window:

```
fishmip-verify-inputs
```

It reads GLADE directly and exits non-zero on any missing variable or coverage
gap, so it can gate a job script. Without installing, `python -m
fishmip_cesm.verify_inputs` works too, but only from the repo root.

Checking variable names alone is not enough. The candidate CAM6 baseline
(`walkerl/SSP245smbb/...001_rerun`) had all eight BGC variables present but only
four years of data in two disjoint fragments. `tests/test_catalog.py` carries that
case as a regression test.

## Stage 2: transform

`fishmip_cesm/transform.py` turns raw CESM fields into FishMIP variables:
derivation (`intpp`, `tob`), unit conversion, renaming, and time subsetting.
The conversion table and its arithmetic are documented inline.

Two behaviours worth knowing:

- `extract_seafloor` masks land. POP's `KMT` is a count of active levels, so
  land is `KMT = 0`; indexing at `KMT - 1` without clipping wraps to `-1` and
  silently returns the *deepest* level instead of a mask.
- `subset_to_window` slices on year-month strings, because CESM stamps monthly
  means mid-month and both end months must be included.

## Stage 2 check: inspect real fields

Before building the regrid, confirm the conversions are right against actual
data. Run on Derecho/Casper:

```
fishmip-inspect-source                 # all four ensembles, year 2040
fishmip-inspect-source --ensemble MCB --year 2050
```

It opens one member per ensemble, applies the transforms and prints quantities
whose magnitude is known independently:

- **global NPP** should be roughly 40-60 PgC/yr. This is the real test of the
  `intpp` conversion -- a wrong power of ten shows up immediately here and
  nowhere else.
- **ocean area** should be about 3.6e14 m2, which checks the `TAREA` cm2 -> m2
  conversion.
- **thetao / tob** ranges should sit within about -2 to 32 degC, and `tob`
  should be markedly colder than `thetao`.

Nothing is written; it is read-only.

## Tests

```
python -m pytest tests/ -q
```

No network or GLADE access needed — the tests build synthetic directory trees.
