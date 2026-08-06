# Eval 4 — Rung-7 adversarial review: `compute-thermal-wind`

**Date:** 2026-08-06.
**Reviewer:** independent Sonnet subagent (fresh context, different model family from the
builder — the closest available approximation to the external evals that caught the eval
1–3 errors). Instructed to *disprove* the skill against the real tutorial notebook, first
principles, and the cached Jan-2000 data; forbidden from trusting the skill's own prose.

## Verdict: **could not disprove — zero confirmed errors.**

All four physics attacks (signs, the g/(fρ) magnitude, drC-vs-drF + k-index negation, the
z0 up/down reconstruction) held. Two secondary attacks (canon/dim-order, test teeth) raised
caveats, not errors. **All five acceptance-record numbers reproduced exactly.**

## Numbers reproduced (reviewer's own run)

| Metric | acceptance.md | reviewer |
|--------|---------------|----------|
| Identity corr(du/dz) vs ∂/∂z of geostrophic vel | 0.9992 | 0.9992 ✓ |
| Identity corr(dv/dz) | 0.9991 | 0.9991 ✓ |
| Independent corr(du/dz) vs actual velocity shear | 0.635 | 0.635 ✓ |
| Independent corr(dv/dz) | 0.852 | 0.852 ✓ |
| Reconstruction median norm-diff vs actual velocity | 0.231 | 0.231 ✓ |

Point counts also matched (identity 1,397,116; independent 1,406,931; reconstruction
719,406).

## Attacks and how each held
- **Signs:** derived both thermal-wind equations from first principles (∂/∂z of geostrophic
  balance + hydrostatic) → `∂v/∂z = −(g/fρ)∂ρ/∂x`, `∂u/∂z = +(g/fρ)∂ρ/∂y`; `predicted_shear`
  matches exactly, and matches the tutorial's `therm_wind_RHS_1/2`. Held.
- **g/(fρ) magnitude:** g=9.81, Ω=2π/86164 (sidereal), rhoConst=1029 all correct; shear
  magnitude ~2.5e-5 s⁻¹ at ~105 m is internally consistent; the reconstruction check pins
  the constant (dropping g → 0.911, fails). Held.
- **drC vs drF + k-negation:** `drC[1:-1]` = 49 interior center-to-center distances,
  broadcasts correctly against the 49 `diff('k')` values; negation present; matches tutorial
  cell 17; drF correctly unused. Held.
- **z0 reconstruction (tutorial cell 21):** reviewer recomputed `delta_upper`/`delta_lower`
  both ways and confirmed `np.allclose(tutorial, skill) = True`; up/down interpolation +
  padding + the `Z < z0` combine (8 levels below −3000 m) all replicate. Held.
- **canon/dim-order handoff:** correct by inspection (`_canon` applied before all positional
  numpy indexing); reviewer couldn't run a live dim-probe (permissions) but the corr=0.9992
  over 1.4M points is strong evidence no silent transpose occurs. Held (by inference).
- **Depth labels:** the "~350 m" figure belongs to the geostrophy skill, not this one;
  thermal wind's `(-Z>100)&(-Z<1000)` band is correctly implemented (k=10 → −105 m,
  k=25 → −722 m). Held.

## Caveats raised (not errors)
- **C1** — the identity check is scale-invariant and shares `grad_to_center` with the target
  (a symmetric bug would pass). *Already documented in acceptance.md as "consistency, not
  independent correctness"; the independent-vs-actual-velocity check (test 2) is the
  independent leg. No change.*
- **C2 (ACTED ON)** — the reconstruction threshold was **0.6**, loose vs the true 0.231, so a
  subtle magnitude bug could slip through. **Fixed:** measured the sensitivity —
  correct 0.231, 1.5× shear error 0.498, 0.5× 0.568, 2× 0.917 — and **tightened the
  threshold 0.6 → 0.35**, which fails all three error cases while keeping margin above 0.231.
  Re-ran: correct code still passes (0.231 < 0.35). This is the eval-4 analogue of prior
  rounds tightening a too-loose guard (OHC's L3 band, etc.).
- **C3** — test 3 is global-off-equator, not the tutorial's Atlantic-26°N-only transect. The
  norm-diff metric is rotation-invariant so the value is equivalent; the skill runs a
  broader/stricter version. *Documented as a deliberate scope choice; no change.*
- **C4** — Coriolis uses xarray named-dim broadcasting vs the tutorial's explicit
  `expand_dims`; safe (f is (tile,j,i), dens is (time,k,tile,j,i) → correct alignment). No
  change.
- **C5** — `actual_shear` leaves k=0/k=49 as NaN (can't be interior-interpolated); matches
  the tutorial and is excluded by the `isfinite` guard. Physically correct. No change.

## Outcome
One actionable finding (C2), fixed and re-verified. No correctness errors. `compute-thermal-wind`
clears Rung 7 → status upgraded ⚠️ → ✅ DONE. Standing-adversarial-review loop continues on
`compute-curl` and `compute-steric-height` next.
