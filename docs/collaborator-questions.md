# CESM2 → FishMIP preprocessing: status and open questions

Draft note for Kelsey, Daniele, Haruki and Colleen.

---

Subject: FishMIP forcing ready — four questions before I publish

Hi all,

The CESM2 preprocessing is done. All four ensembles are regridded onto the FishMIP
1° grid, unit-converted and renamed: **308 files, about 280 GB**, sitting on NCAR scratch
and verified. Nothing is published yet, because a few things need your call first.

| Ensemble | Model | Members | Window |
|---|---|---|---|
| SSP2-4.5 baseline | CESM2-WACCM6 | 10 | 2035–2069 |
| G6-1.5K-SAI | CESM2-WACCM6 | 3 | 2035–2069 |
| SSP2-4.5 baseline | CESM2.1-CAM6 | 16 | 2035–2069 |
| G6-1.5K-MCB | CESM2.1-CAM6 | 5 | 2035–2069 |

Nine variables per member — `intpp`, `thetao`, `tob`, `expc-bot`, `no3`, `phyc`,
`phydiat`, `zooc`, zooplankton loss — plus `deptho` and `thkcello` once for the set.
`zmeso` is not in CESM2 under any configuration, so the fallback in the plan applies.

The regrid is first-order conservative and preserves the global integral to 1e-16: global
NPP is 49.2–49.7 PgC/yr before and after, across all four ensembles.

## Four things I need from you

**1. Filenames — Kelsey and Colleen.** I need these signed off before anything goes to a
public bucket, because renaming afterwards is worse than waiting: other people's scripts
will already point at the old names. The pattern follows ISIMIP3b/FishMIP conventions:

```
cesm2-waccm6_g6-1p5k-sai_001_intpp_onedeg_global_monthly_2035_2069.nc
cesm2-cam6_ssp245_001_intpp_onedeg_global_monthly_2035_2069.nc
```

The scenario tokens are my invention — G6-1.5K-SAI and G6-1.5K-MCB postdate the FishMIP
protocol, so there is no established spelling. Both baselines share `ssp245` and are
distinguished by model, which seemed right since they are the same scenario in two
configurations. Say if you would rather they were something else.

**2. Haruki — is `d651073` the right CAM6 baseline?** I am using
`/glade/campaign/collections/gdex/data/d651073/b.e21.BSSP245smbb.f09_g17/` as the control
for the MCB ensemble. Right compset and forcing variant, 16 members, continuous 2015–2100.
I would like to know the members line up with the branch points of
`MCB-feedback-1DOF.001-005`. (Two things I ruled out, in case they come up:
`walkerl/SSP245smbb/...001_rerun` has only four years of data in two fragments, and the
CESM2 Large Ensemble is SSP3-7.0 rather than SSP2-4.5.)

**3. Do the fish models need full-depth `thetao` and `no3`? — Colleen and Jerome.** Those
two are 60-level fields and account for about two-thirds of the 280 GB. `tob` ships
separately, so if FEISTY and BOATS want surface and seafloor temperature rather than a
profile, dropping full-depth `thetao` would remove roughly 85 GB of data nobody reads.
Easy either way — I would just rather not put it in a bucket that charges egress if it is
not wanted.

**4. Colleen — two zooplankton questions.**

- `zoo_loss_zint` is a *vertical integral*, so its units are `mol m-2 s-1`. The plan asks
  for `mol m-3 s-1`, which cannot be right for an integral. I have gone with `mol m-2
  s-1`; tell me if FEISTY wants something else, and what you would like the variable
  called — there is no CMIP name for it, so I have used `zoo_loss` provisionally.
- `Zmort2 = 0.003` in the plan is the MARBL-8P4Z mesozooplankton value. These runs use
  standard CESM2 MARBL with a single bulk zooplankton class, where the defaults are
  `z_mort_0 = 0.1/day`, `z_mort2_0 = 0.4 (1/day)/(mmol/m³)` and a loss exponent of 1.5 —
  so the coefficient differs by more than two orders of magnitude. MARBL does not output
  the linear and nonlinear terms separately. I can hand you total `zoo_loss_zint`, or
  reconstruct the nonlinear part offline from `zooC` and `TEMP`. Which is more useful?

## Five corrections to the variable table

Flagging these rather than changing them quietly. The first one matters.

**1. `intpp` comes from `photoC_TOT_zint`, not `POC_PROD_zint + DOC_prod_zint`.** That sum
is the vertically integrated production of *detritus* — organic matter routed into the POC
and DOC pools by mortality, grazing and aggregation — not photosynthesis. Integrated
globally it comes to about **18 PgC/yr**, against an expected global NPP of 40–60.
`photoC_TOT_zint` is total carbon fixation, and what CMIP6 CMORizes to `intpp` for CESM2.
It gives **49.3 PgC/yr**, consistent across all four ensembles to within 0.5.

As specified, BOATS would have run on roughly a third of the real primary production, and
nothing in the output would have looked wrong — right shape, right per-cell magnitude, no
errors. Only the global integral exposed it. I have switched to `photoC_TOT_zint`; shout
if you disagree.

**2. `thkcello`** is given as `z_w_top - z_w_bot`, which is negative. POP depths are
positive downward, and `dz` gives layer thickness directly anyway.

**3. `no3`** is listed in `molC m-3`; nitrate is a nitrogen pool, so `mol m-3`.

**4 and 5** are the two zooplankton items above.

## Three things worth knowing

**`phyc`, `phydiat` and `zooc` are upper-ocean only.** MARBL writes the plankton tracers
over the top 150 m (15 levels), not the full column. `no3` and `thetao` are full depth.
This is a limit on the data, not a choice — but you should know it exists.

**Small negative concentrations were clipped to zero.** MARBL's advection scheme leaves
them in the raw output; they are numerical, not physical, and negative concentrations are
not usable forcing. The amounts are tiny and consistent across all 34 members: `no3`
0.002–0.003% of the field, `phyc` ~0.06%, `zooc` ~0.013%, and `phydiat` 0.28–0.34%.
`phydiat` is the outlier by an order of magnitude, which fits — diatom blooms give the
advection scheme the sharpest gradients to overshoot on. Temperature is never clipped.

**Regridding damps extremes.** gx1v7 is finer than 1° near the equator, so area-averaging
onto a regular grid smooths peaks while preserving the integral: `intpp` maxima fall from
about 1.0e-5 to 6.3e-6, `phydiat` from 0.082 to 0.062. This is correct behaviour for a
conservative regrid, but these fields are grid-scale averages rather than CESM2's own
extremes, and it is worth knowing before anyone reads a maximum off them.

## Two decisions already taken, for the record

**SAI is WACCM, MCB is CAM6**, so each scenario is compared against its own matched
baseline. This matters more than it sounds: in 2040, MCB sits 0.52 PgC/yr below the CAM6
baseline but only 0.31 below the WACCM one. At that magnitude the pairing decides the
answer.

**The common window is 2035–2069.** MCB ends in 2069 while SAI runs to 2084, so the last
~15 years of SAI deployment has no MCB counterpart. Happy to supply SAI through 2084
separately if that is useful for a two-way comparison.

Code and full write-up: https://github.com/johnorcutt/fishmip-cesm2-preprocessing

Thanks,
John
