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

**Invoke the modules directly, from the repository root.** On Casper the shared
conda environments are read-only, so pip falls back to a user-site install and
the console scripts land in `~/.local/bin`, which is not on PATH. `python -m`
sidesteps that entirely:

```
python -m fishmip_cesm.verify_inputs
python -m fishmip_cesm.inspect_source
python -m fishmip_cesm.make_weights
python -m fishmip_cesm.check_regrid --weights ...
```

The equivalent console scripts (`fishmip-verify-inputs` and friends) work too,
if `~/.local/bin` is on your PATH.

## Stage 1: verify inputs

All source data is on GLADE at NCAR. Before preprocessing anything, confirm every
ensemble supplies every required variable with **contiguous** monthly coverage
across the analysis window:

```
python -m fishmip_cesm.verify_inputs
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
python -m fishmip_cesm.inspect_source                      # all four, year 2040
python -m fishmip_cesm.inspect_source --ensemble MCB --year 2050
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

## Stage 6: regrid

Conservative gx1v7 -> 1 degree, **not** bilinear: `intpp` and `expc-bot` are
fluxes whose global integral must survive the regrid.

Weights are generated once, offline, by ESMF_RegridWeightGen; applying them is a
cheap sparse matmul that runs per variable and member. On Casper:

```
module load conda && conda activate npl
python -m fishmip_cesm.make_weights --run
python -m fishmip_cesm.check_regrid --weights grids/gx1v7_to_fishmip_1deg_conserve.nc
```

Without `--run` it writes the target grid and prints the ESMF command instead of
running it, which is what you want if the weights should be generated inside a
batch job.

The check regrids one real year of `intpp` and compares the global integral
before and after. It must come back at ~49.3 PgC/yr with a conservation error at
the level of floating-point noise. Conserving relative to a source we had
already got wrong would still be wrong, so the absolute value is checked too.

## Stage 8: the validation gate

Output goes to a **public** bucket, so the checks run before upload, not after.
Publishing is not reversible the way a local write is.

```
python -m fishmip_cesm.dry_run --weights grids/gx1v7_to_fishmip_1deg_conserve.nc
```

This takes one member through transform, regrid and validation for every
variable, writing nothing. Per variable it checks:

- **range** -- catches unit slips and sign errors (a Kelvin/Celsius mix-up puts
  `thetao` at ~290)
- **units** -- the attribute survived, and matches the conversion table
- **ocean coverage** -- no cell that contains ocean is missing a value, which a
  range check cannot see because a missing value has nothing to be out of range
- **conservation**, for flux variables only, against the native-grid integral

The gate fails closed: a variable with no declared range or no classification
stops it rather than passing through.

## Stage 7: write the forcing files

```
python -m fishmip_cesm.write_output --weights grids/gx1v7_to_fishmip_1deg_conserve.nc
```

Dry run by default: reads directory listings only and prints the filenames,
object keys and sizes it would produce. To write one variable for one member:

```
python -m fishmip_cesm.write_output --weights grids/... \
    --ensemble MCB --member 001 --variable intpp --write --out-dir output
```

Memory: fields stream through the regrid in chunks sized by depth, so a
60-level variable does not ask for sixty times the memory of a surface one
(2 months per chunk rather than 60). Concurrency defaults to 2 dask threads --
dask's own default is one per core, and each concurrent chunk holds its own
intermediates, which is how a 10 GB machine runs out on `thetao`. Raise it with
`--workers` if you have the headroom.

## Running the full set

Members are independent, so the job fans out over them. On Derecho:

```
qsub -A <PROJECT> scripts/write_all.pbs
```

One node, all 34 members at once, 2 dask workers each. A member takes about 45
minutes, and they run concurrently, so the whole set is roughly that.

**Re-submitting is the recovery path.** Complete files are skipped; truncated
ones -- from a job killed mid-write -- are rewritten. Existence alone is not
treated as done, because a short file would publish a gap that nothing
downstream would notice.

The work is **CPU bound**, not I/O bound -- a member measured 32m44s user
against 35m55s wall, almost all of it zlib decompression and compression. The
regrid itself is free.

Threads do not help: HDF5 is not thread-safe, so xarray serialises every netCDF
read behind a global lock and a member uses barely one core no matter how many
dask workers it gets. `CONCURRENT_MEMBERS` is the dial that matters;
`DASK_WORKERS` is nearly inert.

Casper is arguably the better home for this, being the analysis machine and
closer to campaign storage. The same script runs there with
`-q casper -l select=1:ncpus=36:mem=100GB` and a lower `CONCURRENT_MEMBERS`.

### Without an allocation

```
nohup bash scripts/write_all_local.sh > logs/local.log 2>&1 &
tail -f logs/local.log
```

Two members at a time, one core each, `nice -n 19`, zlib level 1. Login nodes
are shared and NCAR's arbiter throttles users who take too much of one, so this
is deliberately slow -- expect most of a day. Stopping and restarting is the
normal way to use it: completed files are skipped and truncated ones are
rewritten, so kill it whenever the node is busy.

Level 1 compression is the main lever available here. The job is CPU bound on
zlib, so it roughly halves the write cost for files about 15% larger.

## Tests

```
python -m pytest tests/ -q
```

No network or GLADE access needed — the tests build synthetic directory trees.
