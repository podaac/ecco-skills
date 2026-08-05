# Acceptance evidence — compute-thermal-wind

V&V per `docs/verify.md`. Recipe 3 (thermal wind + velocity reconstruction), built from the
official [Thermal Wind tutorial](https://ecco-v4-python-tutorial.readthedocs.io/Thermal_wind.html).

## Run environment
- macOS/arm64, project `.venv`, Python 3.12.13, xgcm 0.9.0, ecco_v4_py 1.8.1.
- Data: `ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4` (2000-01),
  `ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4` (2000-01), + geometry.
- Verified 2026-08-04.

## Key finding: no official helper (Rung 1 is N/A)

Unlike geostrophy, `ecco_po_tutorials.py` has **no `thermal_wind_compute` function** —
confirmed by listing every top-level function (only `geos_vel_compute` exists for
velocity). The tutorial spreads thermal wind across notebook cells rather than a helper.
So Rung 1 (official-helper match) **cannot apply**; correctness rests on the three
cross-checks below, per verify.md's guidance for a novel combination with no helper.

## V&V status: ⚠️ evidence-backed; Rung-7 adversarial pass PENDING before "done"

| Rung | Status | Evidence |
|------|--------|----------|
| 1 official helper | N/A | No `thermal_wind_compute` in the vendored tutorial module. |
| 2 tutorial number | ✅ (regime) | Reproduces the tutorial's 26°N reconstruction-vs-actual normalized-difference diagnostic: **median 0.231** over 719,406 points in the 100–1000 m band, off-equator, |vel|>0.5 cm/s. The tutorial publishes this as a curve (reference line 0.1), not a single scalar; our value sits in its plotted regime. |
| 3 conservation | N/A | Diagnostic shear, not a budget. |
| 4 physical sanity | ✅ | Off-equator |∂v/∂z| median ~2.5e-5 s⁻¹ @k=10, max ~4e-3 s⁻¹ (≪ 1e-2 cap); reconstructed speed max ~0.40 m/s. |
| 5 internal cross-check | ✅ | **(1) analytic identity:** thermal-wind shear vs ∂/∂z of the geostrophic velocity from the same pressure field — **corr(du/dz)=0.9992, corr(dv/dz)=0.9991** over 1,397,116 points. Confirms signs, the g/(fρ) factor, and the drC vertical derivative. **(2) independent:** predicted shear (from density) vs the model's ACTUAL velocity shear (∂/∂z of UVEL/VVEL) — **corr(du/dz)=0.635, corr(dv/dz)=0.852** over 1,406,931 points. Moderate by nature (real ageostrophic flow); a different variable + code path, so it rules out a bug confined to the pressure path. |
| 6 regression (teeth) | ✅ | `scripts/test_thermal_wind.py`: 3 data cross-checks (SKIP if uncached) + 6 offline synthetic guards. Teeth verified (below). |
| 7 adversarial review | ⚠️ PENDING | A dedicated independent disprove-pass is the final gate before this is marked fully DONE. Not yet run. |

## Teeth verification (2026-08-04)

Deliberately broke the physics and confirmed the suite catches it:
- **Sign flip** (`-(g/fρ)∂ρ/∂x` → `+`): identity check corr(dv/dz) → -0.999, independent
  check corr(dv/dz) → -0.852, reconstruction median norm-diff → 1.19. **All three data
  checks FAIL.**
- **Drop the `g` factor** (`g/(fρ)` → `1/(fρ)`): the two correlation checks still pass
  (correlation is scale-invariant — expected), but the **reconstruction check FAILS**
  (median 0.911 vs 0.231) because it depends on magnitude. This is why the reconstruction
  check is kept: it's the guard that pins down the constant factor, not just the pattern.
- Restored code: **4/4 pass.**

## Results (Jan 2000)

- |∂v/∂z| median off-equator @k=10: **2.5×10⁻⁵ s⁻¹** (interior shear is O(1e-4), as expected).
- Reconstructed surface speed max off-equator: **~0.40 m/s** (WBC-scale, sane).
- Identity check: corr **0.999** (shear = ∂/∂z of geostrophic velocity).
- Independent check: corr **0.64 / 0.85** (predicted vs actual velocity shear).
- Tutorial diagnostic: reconstruction-vs-actual normalized diff median **0.23** (100–1000 m).

## Caveats (not errors)
- Model x/y coordinates (rotation is presentation-only; the normalized-diff metric is
  rotation-invariant).
- Reconstruction depends on the assumed level of no motion z0 = -3000 m.
- Correlation checks are scale-invariant (magnitude guarded by the reconstruction check).
- Equatorial band |lat|<5° excluded (f→0).

## TODO before marking fully ✅ DONE
- Run the Rung-7 adversarial disprove-pass (attack: sign conventions, the g/(fρ) factor,
  drC-vs-drF, the k-index negation, the z0 up/down integration direction, dim-order in the
  interp→numpy handoff) and record the result here.
