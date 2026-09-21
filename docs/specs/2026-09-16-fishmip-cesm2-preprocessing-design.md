# CESM2 → FishMIP preprocessing: design

**Date:** 2026-09-16
**Project:** FishMIP–GeoMIP SRM analysis (Cornell / Reflective / UW / UCLA / UCSD)
**Upstream spec:** [FishMIP–GeoMIP SRM analysis: design and implementation plan](https://docs.google.com/document/d/1GX704UtiXenwm-aRNXpMU2GFaoK1om9jltJSBOpZF1w/edit)

## Purpose

Convert raw CESM2 POP2/MARBL ocean output into FishMIP-conformant forcing files for
BOATS and FEISTY, covering an SSP2-4.5 baseline and two solar radiation modification
scenarios (SAI and MCB).

Scope is preprocessing only: variable derivation, unit conversion, renaming, and
regridding. Running the fish models and analysing biomass response is downstream and
out of scope here.

## Data sources

All inputs are on GLADE at NCAR, as monthly per-variable timeseries under
`ocn/proc/tseries/month_1/`. They are already extracted from history files, so no
timeseries generation is needed.

| Scenario | Model | Forcing | Members | Range | Path |
|---|---|---|---|---|---|
| SSP2-4.5 (WACCM baseline) | CESM2-WACCM6 | cmip6 | 10 | 2015–2100 ✅ | `…/gdex/data/d651045/CESM2-WACCM-SSP245/b.e21.BWSSP245cmip6.f09_g17.CMIP6-SSP2-4.5-WACCM.{001..010}/` |
| G6-1.5K-SAI | CESM2-WACCM6 | — | 3 | 2035–2084 ✅ | `…/gdex/data/d651059/ARISE-SAI-1.5/b.e21.BW.f09_g17.SSP245-G6-1p5K-SAI.{001,002,003}/` |
| G6-1.5K-MCB | CESM2.1-CAM6 | smbb | 5 | 2035–2069 ✅ | `/glade/campaign/cgd/amp/walkerl/MCB_feedback_1DOF_smbb/b.e21.BSSP245smbb.f09_g17.MCB-feedback-1DOF.{001..005}/` |
| SSP2-4.5 (CAM6 baseline) | CESM2.1-CAM6 | smbb | 16 ¹ | 2015–2100 ✅ | `…/gdex/data/d651073/b.e21.BSSP245smbb.f09_g17/b.e21.BSSP245smbb.f09_g17.{001..0NN}/` |

GLADE prefix for the GDEX collections is `/glade/campaign/collections/`. All eight MARBL
biogeochemistry variables plus `TEMP` are verified present, with continuous monthly
coverage over 2035-01–2069-12, for every member of all four ensembles. Verified on
Derecho 2026-09-18 by `fishmip-verify-inputs`; re-run it rather than trusting this table.

Note the CAM6 baseline nests one extra level: the case directories sit inside a container
directory of the same name, not directly under `d651073/`.

¹ 17 case directories, of which 16 are members with three-digit suffixes; the remaining
one is excluded by the member glob (the WACCM collection similarly contains a `.006ext`
alongside `.001`–`.010`). The baseline ensemble is comfortably larger than the 5-member
MCB ensemble, so ensemble size does not constrain the MCB comparison.

Identified by Kelsey Roberts, 2026-09-16. Correct model configuration (CAM6) and forcing
variant (`smbb`) to pair with MCB; confirmation from Haruki Hirasawa that it is the
intended control is still worth having, but is not blocking.

### Notes on source selection

- **G6-1.5K-SAI is inside the GDEX dataset labelled `ARISE-SAI-1.5`** (`d651059`).
  That collection also holds the ARISE runs proper (`SSP245-TSMLT-GAUSS-DEFAULT.001–010`)
  and ARISE extensions. ARISE and G6-1.5K-SAI are *different scenarios* — ARISE injects
  at 15°N/15°S/30°N/30°S, G6-1.5K-SAI at 30°N/30°S only. Use the `SSP245-G6-1p5K-SAI.*`
  cases.
- **Use `MCB-feedback-*`, not `MCB-feedforward-*`.** The scenario protocol
  (Hirasawa et al., GMD 19, 3257, 2026) uses a proportional-integral controller; the
  feedforward runs use a pre-computed emission trajectory and are benchmark simulations,
  not the scenario.
- **Cloudflare R2 (`reflective-data-store`) is not a source.** Its CESM2-WACCM stores
  hold POP physics only (`TEMP`, `z_w_top`, `z_w_bot`, `HT`, `KMT`) with no
  biogeochemistry. R2 is a candidate publishing target (see Outputs).

## Variable mapping

Source grid is POP2 gx1v7: 384 × 320 curvilinear, displaced pole, 60 z-levels.

| FishMIP | Model | CESM source | Derivation | Unit conversion |
|---|---|---|---|---|
| `intpp` | BOATS | `photoC_TOT_zint` | none | `mmol/m³·cm/s` → `mol m⁻² s⁻¹`: × 1e-5 |
| `thetao` | FEISTY, BOATS | `TEMP` | none (3D) | °C → °C: none |
| `tob` | FEISTY, BOATS | `TEMP` | index bottom active level via `KMT` | °C → °C: none |
| `expc-bot` | FEISTY, BOATS | `pocToSed` | none — already 2D | `nmol/cm²/s` → `mol m⁻² s⁻¹`: × 1e-5 |
| `thkcello` | FEISTY, BOATS | `dz` | none (`dz` is layer thickness directly) | cm → m: × 0.01 |
| `no3` | BOATS | `NO3` | none (3D) | `mmol/m³` → `mol m⁻³`: × 1e-3 |
| `phyc` | FEISTY | `spC` | none (3D) | `mmol/m³` → `mol m⁻³`: × 1e-3 |
| `phydiat` | FEISTY | `diatC` | none (3D) | `mmol/m³` → `mol m⁻³`: × 1e-3 |
| `zooc` | FEISTY | `zooC` | none (3D) | `mmol/m³` → `mol m⁻³`: × 1e-3 |
| `zmeso` | FEISTY | — | not available, see below | — |
| zoo total loss | FEISTY | `zoo_loss_zint` | none | `mmol/m³·cm/s` → `mol m⁻² s⁻¹`: × 1e-5 |
| `deptho` | FEISTY | `HT` | none (2D bathymetry) | cm → m: × 0.01 |

### Corrections to the upstream spec

Five items in the spec's Data Inputs table need adjusting. Flagging rather than silently
changing them:

1. **`thkcello` derivation.** The spec gives `z_w_top - z_w_bot`, which is negative —
   POP depths are positive downward, so thickness is `z_w_bot - z_w_top`. Simpler still,
   POP writes `dz` directly; use that.
2. **`no3` units.** The spec lists `molC m-3`. Nitrate is a nitrogen pool; FishMIP
   `no3` is `mol m-3`. Assumed to be a typo.
3. **Zooplankton loss is vertically integrated.** The spec asks for
   `mol m-3 s-1`, but `zoo_loss_zint` is a vertical integral and so is inherently
   `mol m-2 s-1`. Either the target units or the source variable needs to change —
   flagged for Colleen Petrik, since FEISTY's expectation governs.
4. **`Zmort2 = 0.003` does not apply.** That is the MARBL-8P4Z mesozooplankton value.
   These runs use standard CESM2 MARBL, whose defaults
   (`marbl-ecosys/MARBL`, `defaults/settings_cesm2.0.yaml`, `PFT_defaults == "CESM2"`) are:

   | Parameter | Value | Meaning |
   |---|---|---|
   | `zooplankton_cnt` | 1 | single bulk zooplankton class — no mesozooplankton |
   | `z_mort_0_per_day` | 0.1 /day | linear mortality |
   | `z_mort2_0_per_day` | 0.4 (1/day)/(mmol/m³) | nonlinear mortality coefficient |
   | `zoo_mort2_exp` | 1.5 | loss exponent — power-1.5, not quadratic |
   | `loss_thres` | 0.075 nmol/cm³ | concentration below which losses go to zero |

   The CESM2 coefficient differs from the spec's 8P4Z value by more than two orders of
   magnitude, so carrying `0.003` forward would be a substantive error.

   MARBL does not output the linear and nonlinear loss terms separately. Options:
   (a) supply `zoo_loss_zint` as total loss; or (b) reconstruct the nonlinear term offline
   as `z_mort2_0 × (zooC − loss_thres)^1.5 × f_q10(T)`, which is feasible from `zooC` and
   `TEMP` but approximates the in-code calculation. Note that `zoo_loss_poc_zint` /
   `zoo_loss_doc_zint` partition loss by destination pool, not by linear vs. nonlinear,
   so they do not help here.

   The case directories on campaign storage hold archived output and `logs/` but no
   `marbl_in` — CESM writes the resolved MARBL parameter set into `ocn.log.*` at startup,
   so confirm the values there rather than relying on repo defaults. There is no
   indication of custom BGC tuning in these runs (the MCB intervention is atmospheric),
   so the defaults above are a sound fallback. *Decision owner: Colleen Petrik.*

5. **`intpp` comes from `photoC_TOT_zint`, not `POC_PROD_zint + DOC_prod_zint`.**
   This is the most consequential correction. The spec's sum is the vertically
   integrated production of *detritus* — organic matter routed into the POC and DOC
   pools by mortality, grazing and aggregation — not photosynthesis. `photoC_TOT_zint`
   is total carbon fixation, and is what CMIP6 CMORizes to `intpp` for CESM2.

   Caught by the global-integral check in `fishmip-inspect-source`, run against real
   fields on 2026-09-21: the spec's sum integrates to **18.2 PgC/yr** across all four
   ensembles, against an expected global NPP of 40–60. Had this gone unnoticed, BOATS
   would have been forced with roughly a third of the actual primary production, and
   nothing in the output would have looked obviously wrong.

   `photoC_TOT_zint` is present in every member of all four ensembles. Switching to it
   moves global NPP from 18.2 to **49.3 PgC/yr**, consistent to within 0.5 PgC/yr across
   all four ensembles — confirming the diagnosis rather than merely the fix.

### `zmeso` fallback

`zmeso` does not exist in CESM2 under any configuration in these runs. The spec's
documented fallback applies: FEISTY uses `phyc` + `phydiat` + `zooc` in its place. No
derivation is attempted — the substitution is FEISTY's to make, and preprocessing simply
supplies the three fields.

## Pipeline

Eight stages, each independently testable. Intended to run on Casper (post-processing
queue) with direct GLADE reads — no data transfer.

1. **Catalog.** Build an intake-esm-style manifest of (scenario, member, variable, path,
   time range). Two assertions, both failing loudly rather than producing short files:
   every requested variable/member combination is present, **and** its monthly coverage
   is contiguous across the requested window with no gaps.

   The gap assertion is not hypothetical — the CAM6 baseline candidate had all eight
   variables present but only four years of coverage in two disjoint fragments. Checking
   names without checking spans is exactly how that slips through.
2. **Time subset.** Clip each scenario to the common analysis window.
3. **Derive.** `intpp` as the sum of two fields; `tob` by indexing `TEMP` at `KMT-1`
   per column; `thkcello` from `dz`; `deptho` from `HT`.
4. **Convert units.** Apply the factors above; write `units` attributes to match FishMIP.
5. **Rename.** CESM → FishMIP variable names and dimension names.
6. **Regrid.** gx1v7 → FishMIP 1° regular grid (360 × 180). **Conservative** regridding
   via `xesmf`, not bilinear — `intpp` and `expc-bot` are fluxes and must conserve
   globally. Source cell corners derived from `ULAT`/`ULONG`. Regridding weights computed
   once and reused across all variables and members.
7. **Write.** NetCDF4 with FishMIP file naming and required global attributes.
8. **Validate.** See below.

Ordering note: unit conversion precedes regridding so the conservative regridder operates
on final physical units, making global-integral conservation checks meaningful.

### Validation

- Global integral of `intpp` and `expc-bot` preserved across regridding to within
  floating-point tolerance (this is the main correctness check on step 6).
- Land/ocean mask consistency between regridded output and the FishMIP grid.
- Range sanity per variable — e.g. `thetao` within −2 to 40 °C, concentrations
  non-negative.
- Spot-check one member against the equivalent field in the R2 CESM2-WACCM store for
  `TEMP`, which is the one variable present in both, to confirm no indexing or
  orientation errors.

Validated against real fields on 2026-09-21 by `fishmip-inspect-source`, one member per
ensemble, year 2040:

| Quantity | Expected | Measured |
|---|---|---|
| Global NPP | 40–60 PgC/yr | 49.2–49.7 |
| Ocean area | ~3.6e14 m² | 3.605e14 |
| Mean SST | ~18 °C (present day) | 19.4–19.6 at 2040 |
| Mean seafloor temperature | 1–4 °C | 2.6–2.9 |

Note that min/max alone cannot validate `tob`: in a single-level shelf cell the seafloor
*is* the surface, so both fields share their extremes. The area-weighted mean is the check
that discriminates.

## Outputs

FishMIP file naming convention, one file per variable / scenario / member.

Destination is unresolved in the upstream spec, which reads "Files to levante (or
possible to give modelers access to Reflective or AWS paths??)". Two options:

- **Levante (DKRZ)** — the FishMIP convention, where modellers already work.
- **R2 / Reflective paths** — avoids a transfer, but requires granting external
  collaborators access.

These are not mutually exclusive; writing to GLADE first and mirroring is cheap. Decision
needed — see below.

## Open decisions

Three questions change what the pipeline produces and need answers from the science
leads before implementation is final. None block starting on stages 1–5.

### 1. Model mismatch: SAI is WACCM, MCB is CAM6

G6-1.5K-SAI ran in CESM2-WACCM6; G6-1.5K-MCB ran in CESM2.1-CAM6 (case prefix
`BSSP245smbb`, no `W`). This is defensible physically — SAI needs a high model top,
MCB is a boundary-layer intervention — and the protocol paper argues the two
configurations are close enough for the controller to transfer.

**Consequence for preprocessing:** each scenario needs its own matched baseline. A single
shared SSP2-4.5 baseline is not valid, so the pipeline processes **two** baselines, and
the analysis compares SAI against the WACCM baseline and MCB against the CAM6 baseline.

*Owner: Kelsey Roberts, Daniele Visioni.*

### 2. CAM6 SSP2-4.5 baseline — resolved, pending verification

**Use `/glade/campaign/collections/gdex/data/d651073/b.e21.BSSP245smbb.f09_g17/`.**
Verified: continuous 2015–2100 monthly coverage, all eight BGC variables, 17 case
directories. Correct model configuration (CAM6) and forcing variant (`smbb`) to pair with
the MCB ensemble. Confirmation from Haruki Hirasawa is a courtesy check, not a blocker.

**Dead ends, recorded so they are not revisited:**

- `/glade/campaign/cgd/amp/walkerl/SSP245smbb/b.e21.BSSP245smbb.f09_g17.001_rerun/` —
  the obvious candidate. All eight BGC variables are present, but coverage is only
  **2035-01→2036-12 and 2063-01→2064-12**: four years in two fragments, identical across
  every variable. Almost certainly a targeted rerun, not a baseline. Unusable.
- **CESM2 Large Ensemble** — ruled out. The LE runs historical + **SSP3-7.0**, not
  SSP2-4.5 (case names `b.e21.BHISTcmip6.f09_g17.LE2-####`). It has full MARBL output
  and ~50 members, but the wrong scenario. Noted because it looks like an obvious fix
  and is not one.
- **WACCM SSP2-4.5 baseline** (`d651045`) — cannot substitute. Different model
  configuration *and* different biomass-burning forcing variant (`cmip6` vs `smbb`).

*Owner: verification is ours; confirmation from Haruki Hirasawa.*

### 2b. Forcing-variant mismatch

The WACCM baseline is `BWSSP245cmip6` while the MCB runs are `BSSP245smbb` — different
biomass-burning treatments layered on top of the model-configuration difference. Confirm
which variant the G6-1.5K-SAI cases use so the SAI/baseline pairing is at least
internally consistent.

### 3. Common analysis window is 2035–2069

MCB ends 2069. SAI runs to 2084 and the spec's deployment window is 2035–2085, so the
last ~15 years of SAI deployment has no MCB counterpart.

Options: cap the three-way comparison at 2035–2069 and analyse SAI-only for 2070–2084;
or cap everything at 2069. This affects how the "amplify vs. mitigate" framing in the
research objectives is stated.

*Owner: Kelsey Roberts, Daniele Visioni.*

### 4. Output destination

Levante, Reflective/R2, or both. *Owner: Kelsey Roberts, with Colleen Petrik, Jerome
Guiet, and Ryan Heneghan as the consumers.*

## Assumptions

Stated explicitly because they were not specified upstream and were resolved by judgment:

- Monthly frequency throughout. Daily POP output exists but FishMIP forcing is monthly.
- Conservative regridding for all variables, not just fluxes — consistent treatment
  avoids mask-edge discrepancies between 2D and 3D fields.
- All available members are processed. Member selection for the analysis is a downstream
  choice, and processing all of them is cheap relative to re-running later.
- Full 60-level depth output retained for 3D variables. If FEISTY or BOATS need only
  specific levels, subsetting downstream is easier than reprocessing.

## Out of scope

- Fishing effort forcing (ISIMIP3a `histsoc`). Handled separately per the upstream spec;
  it is an input to the fish models, not to CESM2 preprocessing.
- Running BOATS or FEISTY.
- Any analysis of the resulting biomass fields.
