---
name: compute-geostrophic-balance
description: Compute geostrophic velocities from ECCO pressure (PHIHYDcR) and density (RHOAnoma) on the native LLC90 grid, in model x/y coordinates. Uses the corrected formula v_g = rhoConst·∂(PHIHYDcR)/∂x / (ρ·f); results are verified to match the official ecco_po_tutorials.geos_vel_compute exactly. Use for geostrophic-balance questions, geostrophic velocity, or comparing pressure-derived vs model velocities. Requires ecco-setup + Earthdata credentials.
---

# compute-geostrophic-balance (Recipe 2)

> **🔬 Verification status (per `docs/verify.md`): ✅ DONE.** Two independent checks, both
> automated (`scripts/test_geostrophic.py`): (1) **reproduces** the official
> `ecco_po_tutorials.geos_vel_compute` to <1e-9 m/s over 2.24M points; (2) **independently
> corroborated** — matches the model's *actual* UVEL/VVEL at ~200 m (corr 0.998, median
> normalized diff 0.032), which rules out a bug shared with the reference. Physical sanity
> ✅, guards teeth-verified, and a **Rung-7 adversarial pass found zero correctness errors**
> (2026-07-25). Two documented limitations: model-axis (not rotated) output, and coastal
> NaN-bleed inherited from the reference method. Full record: `references/acceptance.md`.

Geostrophic balance is the dominant force balance for large-scale ocean flow away from
the equator: the horizontal pressure-gradient force balances the Coriolis force.

```
f·v = (1/ρ)·∂p/∂x        f·u = -(1/ρ)·∂p/∂y
```

## The science (what a learner should take away)

- **ECCO stores `PHIHYDcR = p/rhoConst − gz`**, not pressure. So
  `∂p/∂x = rhoConst·∂(PHIHYDcR)/∂x` (the `gz` term has no horizontal gradient at fixed
  depth). **You must keep the `rhoConst` factor and divide by the actual density**
  `ρ = rhoConst + RHOAnoma`. Dropping `rhoConst/ρ` is a few-percent error (this was a real
  bug caught earlier — see the design-doc history).
- **C-grid staggering:** the pressure gradient is computed with `xgcm.diff` (tracer →
  face), then `interp_2d_vector` brings it back to tracer points, so `u_g`/`v_g` end up
  co-located at cell centers.
- **Model coordinates, not rotated.** `u_g`/`v_g` are in the model x/y frame — the same
  as the official helper and as the model's own `UVEL`/`VVEL`. Keep both sides in model
  coords for a like-for-like balance comparison; only rotate (CS/SN) for geographic maps.
- **Equator is special:** `f → 0` at the equator, so `1/f` blows up and geostrophy breaks
  down. Mask `|lat| < 5°` for any physical interpretation (the runtime L3 check already
  excludes that band).

## How to run

```
.venv/bin/python scripts/run.py 2000-01     # geostrophic velocities for Jan 2000
```

Run with the **venv** python. Loads density/pressure (~30 MB) + geometry, both cached.

## Composition (Option A)

Imports the shared building blocks — no download/grid code of its own:

```python
from ecco_common import load_grid, load_field
ds_grid, xgcm_grid = load_grid()
ds_dp = load_field("ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4", months=["2000-01"])
```

## Verification (per `docs/verify.md`)

| Rung | Status | Evidence |
|------|--------|----------|
| 1 official helper | ✅ | Reproduces `ecco_po_tutorials.geos_vel_compute` <1e-9 m/s over 2.24M pts. (*Reproducibility* — a shared bug would pass; see Rung 5 for the real correctness check.) |
| 2 tutorial number | N/A | Tutorial publishes figures/arrays, not a scalar. |
| 3 conservation | N/A | Not a budget. |
| 4 physical sanity | ✅ | Surface geostrophic speed median ~0.029 m/s off-equator; WBC-box max ~0.32 m/s. |
| 5 cross-check | ✅ | **Independent:** matches actual model UVEL/VVEL at ~200 m (corr 0.998, median norm-diff 0.032). Different variable + code path → rules out a bug shared with the reference. This is the strongest correctness evidence. |
| 6 regression (teeth) | ✅ | `test_geostrophic.py`: Rung-1 match + independent-velocity check + guard cases; verified to fail when equatorial mask is broken. |
| 7 adversarial | ✅ | Independent disprove-pass (2026-07-25): zero confirmed errors after attacking signs, rhoConst, staggering, NaN handling, test rigor, and physical plausibility. Its one substantive critique — overstated Rung-1 correctness claim — is now fixed (this table). |

## Limits / honest caveats

- **Model coordinates.** `u_g`/`v_g` are model-x/y, not zonal/meridional. For geographic
  interpretation/maps, rotate with `CS`/`SN` (see `rotate-to-geographic`), and rotate the
  actual velocity the same way for comparison.
- **Equatorial band** (`|lat|<5°`) is not physically meaningful (f→0) and is excluded
  from sanity checks; don't report values there.
- **Comparing to model velocity** (the "does geostrophy hold?" question) is a *further*
  step — load `UVEL`/`VVEL`, interpolate to centers, and take a normalized difference.
  This skill computes the geostrophic estimate; the comparison recipe builds on it.
  (The acceptance test *does* this comparison at 200 m as its correctness check.)
- **Coastal NaN-bleed (inherited from the official method).** PHIHYDcR is NaN on land;
  through `diff(boundary='extend')` + `interp_2d_vector`, NaNs propagate onto ~116k wet
  ocean cells adjacent to coasts/tile edges, so `u_g`/`v_g` are NaN there. The official
  `geos_vel_compute` behaves identically (it doesn't zero-fill the pressure gradient
  before interpolation). Not introduced by this skill, but real coastal data loss —
  don't treat near-coast NaNs as zeros.
- **`boundary='extend'` at tile seams** approximates cross-seam neighbors, so near-seam
  gradient values are approximate (also inherited from the reference/tutorial).

## Files
- `scripts/run.py` — the calculation + runtime validation trail.
- `scripts/test_geostrophic.py` — Rung-1 match vs official helper + negative/positive guards.
- `references/acceptance.md` — verification evidence.
