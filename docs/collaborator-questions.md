# CESM2 → FishMIP preprocessing: four questions before we build

Draft message for Kelsey, Daniele, Haruki, and Colleen.

---

Hi all,

I've finished locating the CESM2 inputs for the FishMIP–GeoMIP analysis. Short version:
both SRM scenarios and the WACCM baseline are on GLADE at NCAR with all eight MARBL
biogeochemistry variables, already as monthly timeseries — no data acquisition needed.
Kelsey pointed me at the CAM6 baseline for the MCB runs (`d651073`), so all four
ensembles are accounted for.

None of this is in our Cloudflare R2 stores, incidentally — those have the physics but no
biogeochemistry for any scenario, so this is a Derecho job.

| Scenario | Model | Members | Range | Status |
|---|---|---|---|---|
| SSP2-4.5 baseline | CESM2-WACCM6 | 10 | 2015-2100 | good |
| G6-1.5K-SAI | CESM2-WACCM6 | 3 | 2035-2084 | good |
| G6-1.5K-MCB | CESM2.1-CAM6 | 5 | 2035-2069 | good |
| SSP2-4.5 baseline | CESM2.1-CAM6 | ? | ? | `d651073`, verifying |

(Worth noting the G6-1.5K-SAI runs live inside the GDEX collection labelled
`ARISE-SAI-1.5`, `d651059`, alongside the actual ARISE runs. Easy to grab the wrong one.)

**1. Haruki - can you confirm the MCB baseline?** Kelsey pointed us at
`/glade/campaign/collections/gdex/data/d651073/b.e21.BSSP245smbb.f09_g17*`, which is the
right model configuration and forcing variant, and we're proceeding on that. Just want to
confirm it's the intended control for the MCB ensemble, and ideally that the members line
up with the branch points of `MCB-feedback-1DOF.001-005`.

For the record, two things we ruled out on the way, in case anyone suggests them:
`walkerl/SSP245smbb/...001_rerun` has all the right variables but only four years of data
in two fragments; and the CESM2 Large Ensemble is SSP3-7.0, not SSP2-4.5.

**2. SAI is WACCM, MCB is CAM6.** The two scenarios ran in different model
configurations. Physically that makes sense - SAI needs a high top, MCB doesn't - but it
means each scenario needs its own matched SSP2-4.5 baseline, which is why question 1
matters. There's also a forcing-variant difference (`cmip6` vs `smbb`) layered on top.
Does that match what you assumed?

**3. MCB ends in 2069.** SAI runs to 2084 and the protocol deployment window is
2035–2085, so our three-way comparison is capped at 2035–2069 — we lose the last ~15
years of SAI deployment. Do we cap everything at 2069, or run the three-way comparison
to 2069 and carry SAI alone through 2084?

**4. A few details in the variable table.** Minor, but worth fixing in the doc:
- `thkcello` is listed as `z_w_top - z_w_bot`, which comes out negative — should be the
  other way round, and POP gives us `dz` directly anyway.
- `no3` is listed in `molC m-3`; nitrate should be `mol m-3`.
- Colleen — two zooplankton questions:
  - `zoo_loss_zint` is a *vertical integral*, so `mol m-2 s-1`, but the spec asks for
    `mol m-3 s-1`. We assume the spec units are just wrong, but which does FEISTY want?
  - `Zmort2 = 0.003` is the MARBL-8P4Z mesozooplankton value and doesn't apply to these
    runs. Standard CESM2 MARBL has one bulk zooplankton class with
    `z_mort2_0 = 0.4 (1/day)/(mmol/m3)` and a loss exponent of 1.5 — so the coefficient is
    off by over two orders of magnitude from what's in the spec. MARBL doesn't output the
    linear and nonlinear terms separately. We can either hand you total `zoo_loss_zint`,
    or reconstruct the nonlinear part offline from `zooC` and `TEMP`. Which is more
    useful?

None of these block me now — all four ensembles are located, so I can start building and
validating the pipeline. Questions 2 and 3 are the ones that shape how we frame the
comparison, so they're worth settling before we're deep into analysis.

Thanks,
John
