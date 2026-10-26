# Draft email to Kelsey — 2026-10-26

**Subject:** CESM2 FishMIP forcing — status, and three decisions

Hi Kelsey,

An update on the CESM2 forcing, and three things we need your call on.

## What has changed since you last downloaded

- **The SSP2-4.5 baseline now runs 2015–2100**, not 2035–2069. You were right that
  it should start in 2015 — we had windowed it to match when the SRM scenarios
  begin, which left a twenty-year hole between the end of historical (2014) and
  the start of the baseline.
- **Historical and piControl are published.** They were produced on 9 October. If
  they did not appear, your copy of the download script predates them and cannot
  request them; the current version is in the repository.
- **The G6-MCB files have been withdrawn.** The path we were given held a
  different set of Walker simulations rather than the G6 runs. We have the
  correct location from Hirasawa and are working on it now.
- **Anyone holding SAI or MCB files from before 23 October should delete and
  re-fetch them.** A time-encoding problem left them readable in Python but not
  in CDO or ncdump, which reported every timestamp as zero rather than failing.
  The published files are fixed, but the download script skips on file size, so
  re-running it will not replace a stale copy — the old files have to be deleted
  first.

## Three decisions

**1. Should the SRM window extend to 2084?**
Both G6-1.5K-SAI and G6-1.5K-MCB run 2035–2084. Our 2069 cutoff came from the
MCB archive that turned out to be the wrong simulations, so it rests on nothing.
Extending gives fifteen more years on both scenarios, and the baselines already
cover it. Six members to re-run, so it is cheap.

**2. WACCM baseline: five members to 2100, or ten to 2069?**
Only five of the ten WACCM SSP2-4.5 members reach 2100; the rest stop at
2069/2070. We have published the five, because including the others would halve
the ensemble at 2070 — the spread would visibly narrow there for no physical
reason. If spread matters more than span for the SAI comparison, we can publish
all ten at 2015–2069 instead.

**3. How many members do you actually need?**
We are producing every member of every ensemble. If FEISTY is only ever run on
one member per ensemble, most of the 530 GB is bandwidth nobody reads. Nobody
has specified this either way and we would rather ask than keep guessing.

## Two questions for Hirasawa and Dan

The correct MCB archive is missing `photoC_TOT_zint` and `zoo_loss_zint`, so
`intpp` and `zoo_loss` cannot be derived for MCB the way they are for the other
ensembles. We would rather not compute `intpp` from
`POC_PROD_zint + DOC_prod_zint`: that sum integrates to roughly 18 PgC/yr
against about 49 for `photoC_TOT_zint`, so it would put MCB's primary
production on a different definition from every other ensemble, and nothing
downstream would flag it.

- Are `photoC_TOT_zint` and `zoo_loss_zint` available for these runs anywhere?
- Are the raw POP history files kept, rather than the concatenated set? Those
  would also carry the time bounds, which the current files lack.

Unless we hear otherwise, we will publish MCB with the other seven variables and
add those two when they are available.

## Still open from earlier

- Colleen's question on `zoo_loss`: we have assumed `mol m-2 s-1`. The spec says
  `mol m-3 s-1`, which cannot be right for a vertically integrated quantity. The
  output name is also provisional, as there is no CMIP name for it.
- Whether full-depth `thetao` is needed at all. It is about 85 GB of the set, and
  if only the surface or the seafloor matters, `tob` already covers the latter.

Data: https://pub-d127229e707d485c80965ab41706e316.r2.dev/fishmip/
Code and download script: https://github.com/reflective-org/fishmip-cesm2-preprocessing

John
