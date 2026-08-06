# Acceptance evidence — compute-geostrophic-balance

V&V per `docs/verify.md`. This skill is notable as the first to satisfy **Rung 1**
(match the official ECCO helper) — the strongest correctness evidence in the protocol.

## Run environment
- macOS/arm64, project `.venv`, Python 3.12.13, xgcm 0.9.0, ecco_v4_py 1.8.1.
- Data: `ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4` (2000-01) + geometry.
- Reference helper: `ecco_po_tutorials.geos_vel_compute`, vendored from
  ECCO-GROUP/ECCO-v4-Python-Tutorial @ commit `3f0fcca` (see `ecco-common/vendor/`).
- Verified 2026-07-25.

## V&V status: ✅ DONE (all applicable rungs cleared 2026-07-25)

| Rung | Status | Evidence |
|------|--------|----------|
| 1 official-helper match | ✅ | Reproduces `geos_vel_compute` to **max |Δ| < 1e-9 m/s over 2,237,682 points** (Jan 2000). This is *reproducibility* — a shared bug would pass; the real correctness check is Rung 5. |
| 2 tutorial number | N/A | Tutorial publishes figures/arrays, not a scalar. |
| 3 conservation | N/A | Diagnostic velocity, not a budget. |
| 4 physical sanity | ✅ | Surface geostrophic *speed* median ≈ 0.029 m/s off-equator; Gulf Stream / Kuroshio box max ≈ 0.32/0.31 m/s (sane for LLC90 monthly means). |
| 5 internal cross-check | ✅ | **Independent** comparison to the model's ACTUAL UVEL/VVEL at ~350 m: corr(u)=0.998, corr(v)=0.998, median normalized diff = 0.032 over 45,745 points. Different variable + code path → rules out a bug shared with the reference. Automated in `test_geostrophic.py`. **This is the strongest correctness evidence.** |
| 6 regression (teeth) | ✅ | `test_geostrophic.py` = Rung-1 match + independent-velocity check + 5 guard cases. Teeth verified: `EQ_BAND_DEG=0` (breaking equatorial masking) makes a guard case fail. |
| 7 adversarial review | ✅ | Independent disprove-pass (2026-07-25): **zero confirmed errors** after attacking signs (verified from first principles), the rhoConst factor, grid staggering, NaN handling, the test's discriminating power, and physical plausibility (incl. its own UVEL/VVEL comparison). |

## Adversarial review (Rung 7) — 2026-07-25

An independent agent instructed to *disprove* the skill could not. It verified the signs
from first principles, confirmed the vendored helper faithfully reproduces the tutorial's
own notebook cells, and independently corroborated against model velocities. Its one
substantive critique was fair and is now **fixed**: the skill had marketed the Rung-1
helper-match as "the strongest correctness evidence," but that only proves
*reproducibility* (a shared bug would pass). Action taken: added an **independent
correctness test** vs actual UVEL/VVEL (now Rung 5, automated) and corrected the language
in run.py / SKILL.md. Documented (not errors): coastal NaN-bleed and `boundary='extend'`
tile-seam approximation, both inherited from the official reference method.

## Caveats (not errors)
- Velocities are in **model x/y** coordinates (as the reference produces); geographic
  interpretation requires CS/SN rotation.
- Coastal NaN-bleed onto ~116k wet cells (inherited from the reference); `boundary='extend'`
  approximates tile-seam neighbors.
- The equatorial band (|lat|<5°) is excluded from sanity bounds (f→0 blowup).
