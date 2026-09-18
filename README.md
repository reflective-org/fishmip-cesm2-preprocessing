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

## Tests

```
python -m pytest tests/ -q
```

No network or GLADE access needed — the tests build synthetic directory trees.
