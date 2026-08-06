# Acceptance evidence — compute-curl

V&V per `docs/verify.md`. Recipe 6 / Q5 (wind-stress curl + Ekman pumping), built from the
official native-grid gradient/curl tutorial (`ECCO_v4_Gradient_calc_on_native_grid.ipynb`).

## Run environment
- macOS/arm64, project `.venv`, Python 3.12.13, xgcm 0.9.0, ecco_v4_py 1.8.1.
- Data: `ECCO_L4_STRESS_LLC0090GRID_MONTHLY_V4R4` (2000-01),
  `ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4` (2000-01, for WVEL), + geometry.
- Verified 2026-08-05.

## Key findings

1. **No official curl helper** — confirmed by listing every function in the vendored
   `ecco_po_tutorials.py` (only `geos_vel_compute` + transect/plot helpers) and searching
   installed `ecco_v4_py` (`get_llc_grid`, plotters, and `vector_calc.UEVNfromUXVY` — a
   component-rotation helper, not a curl). So Rung 1 (official-helper match) is **N/A** for
   the curl itself; we match the rotation core against `UEVNfromUXVY` as a partial Rung-1.

2. **Grid-position correction (design doc was BACKWARDS):** the real data shows
   `oceTAUX` dims `(time,tile,j,i_g)` and `oceTAUY` `(time,tile,j_g,i)` — i.e. on the
   U-/V-**faces**, not tracer points. It's `EXFtaux/y` that are at tracer points. So the
   total stress must be interpolated to centers first (`already_at_center=False`), like
   velocity. design.md's claim that oceTAUX/Y are "already at tracer points" is wrong and
   is corrected in this build.

## V&V status: ⚠️ evidence-backed; Rung-7 adversarial pass PENDING before "done"

| Rung | Status | Evidence |
|------|--------|----------|
| 1 official helper | N/A | No curl helper anywhere. **Partial:** CS/SN component rotation == official `ecco_v4_py.vector_calc.UEVNfromUXVY`, **max\|Δ\|=0.0** (bit-identical) over the global field. |
| 2 tutorial number | ✅ (operator) | Two-rotation pipeline transcribed from the official gradient/curl tutorial (cells 125→137); tutorial publishes maps, not scalars. |
| 3 conservation | N/A | Diagnostic, not a budget. |
| 4 physical sanity | ✅ | Wind-stress curl median ~1.0e-7 Pa/m, max ~1.6e-6; Ekman `w_E` max ~1.7e-5 m/s. Correct sign: N. Pacific subtropical box mean curl = −1.0e-7 Pa/m (Ekman downwelling, as expected). Global map shows textbook subtropical-downwelling / subpolar-upwelling bands. |
| 5 internal cross-check | ✅ | **(a)** rotation bit-identical to `UEVNfromUXVY`. **(b) independent physical:** Ekman `w_E` vs the model's **actual WVEL** at ~30 m (k_l=3), off-equator, wet, non-zero: **corr = 0.738, sign-agreement = 0.89** over 48,383 points. WVEL is a different variable + code path → rules out a bug confined to the stress path. |
| 6 regression (teeth) | ✅ | `scripts/test_curl.py`: rotation + Ekman-vs-WVEL + a teeth test + offline guards. Teeth verified (below). |
| 7 adversarial review | ⚠️ PENDING | Dedicated independent disprove-pass not yet run — the final gate before fully DONE. |

## Teeth verification (2026-08-05)

- **Drop the second rotation** (combine model-axis derivatives directly, the eval-#2 bug):
  the curl shifts by **~30% (median)** vs the correct two-rotation curl → the test asserts
  a >5% shift, so this class of error is caught.
- **Flip the Ekman formula sign** (`curl/(ρf)` → `−curl/(ρf)`): the WVEL correlation goes
  **0.738 → −0.558**, failing the `corr > 0.6` assertion.
- Restored code: **4/4 curl tests pass; all 5 project suites pass.**

## Results (Jan 2000)
- Wind-stress curl: median ~1.0e-7 Pa/m off-equator; correct gyre sign pattern.
- Ekman pumping w_E: O(1e-6) m/s; max ~1.7e-5 m/s off-equator.
- Rotation vs official `UEVNfromUXVY`: max|Δ| = 0.
- Ekman w_E vs actual WVEL @~30 m: corr 0.738, sign-agree 0.89 (48,383 pts).
- Figure: `plots/gallery/wind_stress_curl_2000-01.png` (gitignored) — textbook pattern.

## Caveats (not errors)
- The Ekman-vs-WVEL check is a physical relationship, not an identity (WVEL ⊋ Ekman
  pumping); corr 0.74 is strong but won't approach 1.
- β term included by default; f-plane approx available via `use_beta=False`.
- Curl units are `[field]/m` (Pa/m for stress, s⁻¹ for velocity) — labeled per call.
- Equatorial band |lat|<5° excluded (f→0).

## TODO before marking fully ✅ DONE
- Run the Rung-7 adversarial disprove-pass (attack: the two rotations & their signs, the
  interp-to-centers step for face-staggered stress, the β term, the curl sign convention,
  the WVEL interface-level sampling, and whether the teeth tests truly discriminate).
