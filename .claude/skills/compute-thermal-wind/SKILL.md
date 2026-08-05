---
name: compute-thermal-wind
description: Compute the thermal-wind vertical shear (∂u/∂z, ∂v/∂z) of the geostrophic flow from ECCO's horizontal density structure on the native LLC90 grid, and reconstruct the velocity profile by integrating that shear from a level of no motion (z0=-3000 m). Verified against the model's own actual velocity. Use for thermal-wind questions, vertical current shear, or reconstructing deep velocity from density. Requires ecco-setup + Earthdata credentials.
---

# compute-thermal-wind (Recipe 3)

> **🔬 Verification status (per `docs/verify.md`): ✅ DONE.** No official `thermal_wind_compute`
> helper exists (Rung 1 N/A — only `geos_vel_compute` is in `ecco_po_tutorials.py`), so
> correctness rests on three automated cross-checks in `scripts/test_thermal_wind.py`,
> strongest first: **(1)** the shear reproduces ∂/∂z of the geostrophic velocity from the
> same pressure field to **corr 0.999** (analytic identity — proves the shear math);
> **(2)** predicted shear matches the model's *actual* velocity shear (corr 0.64/0.85 —
> independent of the pressure path); **(3)** velocity reconstructed from z0=-3000 m matches
> the model's *actual* velocity along 26°N to a normalized diff of ~0.23 in the 100–1000 m
> band (the tutorial's own deliverable). Guards teeth-verified (a sign flip fails checks
> 1–3; dropping `g` fails check 3). Full record: `references/acceptance.md`.

Thermal wind links the **vertical shear of the currents** to the **horizontal density
gradient**. It's what you get by taking ∂/∂z of geostrophic balance and substituting
hydrostatic balance — so density alone predicts how the flow changes with depth:

```
∂v/∂z = -(g / (f·ρ)) · ∂ρ/∂x        ∂u/∂z =  (g / (f·ρ)) · ∂ρ/∂y
```

## The science (what a learner should take away)

- **Density sets the shear, not the flow itself.** Thermal wind gives you `∂u/∂z`, `∂v/∂z`
  from `ρ`. To get an actual velocity you must **integrate** the shear from a depth where
  you assume the flow is known — a *level of no motion* `z0` (the tutorial uses -3000 m).
  Above z0 you integrate upward, below it downward.
- **Constants & fields:** `ρ = rhoConst + RHOAnoma` (rhoConst=1029), `g=9.81`,
  `f = 2Ω·sin(lat)` (Ω=2π/86164). Only the density/pressure collection is needed for the
  shear; the actual-velocity collection is loaded only for the verification comparison.
- **C-grid staggering:** the horizontal density gradient is computed with `xgcm.diff`
  (tracer→face), then `interp_2d_vector` brings it back to tracer centers — the same
  pattern as `compute-geostrophic-balance`.
- **Vertical derivative:** velocity shear differences over `k` and divides by **`drC`**
  (center-to-center distance), negated because k increases downward while z increases
  upward. (`drC` for center quantities; `drF` is for cell-thickness/face quantities.)
- **Equator is special:** `f→0` there, so `1/f` blows up and the balance breaks down.
  `|lat|<5°` is excluded from every check.

## Coordinate frame — model x/y (and why that's sufficient)

Output shear/velocity are in the **model x/y** frame (like `compute-geostrophic-balance`),
not rotated to zonal/meridional. The tutorial rotates with CS/SN for its map panels, but
its **verification metric — the normalized difference `|Δvel|/|vel|` — is invariant under
that rotation** (CS/SN rotation is orthogonal, so vector magnitudes are preserved). So the
correctness numbers are identical with or without rotation; rotation is a presentation step
for maps only. Rotate with CS/SN if you need a geographic map.

## How to run

```
.venv/bin/python scripts/run.py 2000-01     # thermal-wind shear + velocity reconstruction
```

Run with the **venv** python. Loads density/pressure (~30 MB) + geometry, both cached.
Prints the runtime validation trail (grid position, off-equator finiteness, physical
bounds on shear and reconstructed speed).

## Composition (Option A)

Imports the shared building blocks — no download/grid code of its own:

```python
from ecco_common import load_grid, load_field
ds_grid, xgcm_grid = load_grid()
ds_dp = load_field("ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4", months=["2000-01"])
```

The verification (`test_thermal_wind.py`) additionally loads
`ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4` for the actual-velocity comparisons. It
recomputes geostrophic velocity **inline** from `PHIHYDcR` for the identity check — it does
**not** import the `compute-geostrophic-balance` skill (no coupling between skills).

## Verification (per `docs/verify.md`)

| Rung | Status | Evidence |
|------|--------|----------|
| 1 official helper | **N/A** | No `thermal_wind_compute` in `ecco_po_tutorials.py` (only `geos_vel_compute`). Documented, as OHC documents its N/A rungs. |
| 2 tutorial number | ✅ (regime) | Reproduces the tutorial's 26°N reconstruction-vs-actual normalized difference (~0.23 median, 100–1000 m) — the tutorial publishes this diagnostic as a curve, not a scalar. |
| 3 conservation | N/A | Diagnostic shear, not a budget. |
| 4 physical sanity | ✅ | Off-equator |∂u/∂z|,|∂v/∂z| ~1e-4 s⁻¹ (max ≪ 1e-2); reconstructed speed max ~0.4 m/s. Runtime L3 guard. |
| 5 cross-check | ✅ | **(1) internal identity:** shear ≈ ∂/∂z of geostrophic velocity, corr **0.999**. **(2) independent:** predicted shear vs the model's *actual* velocity shear, corr 0.64/0.85 (different variable/path → rules out a bug shared with the pressure field). |
| 6 regression (teeth) | ✅ | `test_thermal_wind.py`: 3 data cross-checks + 6 offline guards. Teeth verified — a sign flip fails checks 1–3; dropping `g` fails check 3 (magnitude). |
| 7 adversarial | ⚠️ pending | A standing disprove-pass is the final gate before this is fully "done" — see acceptance.md. |

## Limits / honest caveats

- **Model coordinates** (not rotated); see the coordinate-frame note above.
- **Level of no motion is an assumption.** The reconstruction quality depends on `z0`
  (-3000 m by default). Where the real flow at z0 is not ~0, the reconstruction is offset —
  this is physics, not a bug, and is exactly what the normalized-diff diagnostic reveals.
- **Correlation checks are scale-invariant** — they'd miss a wrong constant factor. The
  reconstruction check (which depends on magnitude) is what guards that, by design.
- **Equatorial band** (`|lat|<5°`) is excluded (f→0 blowup); don't report values there.
- **Coastal/tile-seam `extend` approximation** inherited from the same `diff`/`interp`
  pattern as geostrophy.

## Files
- `scripts/run.py` — shear + reconstruction + runtime validation trail.
- `scripts/test_thermal_wind.py` — 3 cross-checks (identity, independent, tutorial) + guards.
- `references/acceptance.md` — verification evidence.
