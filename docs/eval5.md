# Eval 5 — Rung-7 adversarial review: `compute-curl`

**Date:** 2026-08-06.
**Reviewer:** independent Sonnet subagent (fresh context, different model family from the
builder). Instructed to *disprove* the wind-stress-curl + Ekman-pumping skill against the
real native-grid gradient/curl tutorial, first principles, the official
`ecco_v4_py.vector_calc.UEVNfromUXVY` helper, and the cached Jan-2000 stress+velocity data.
**This is the project's highest-risk skill** — its algorithm was wrong twice before (a naive
no-rotation curl, then a version missing the second of the two mandatory LLC rotations,
caught by eval #2). So the review focused hard on the rotations.

## Verdict: **only caveats — could not disprove. Zero confirmed errors.**

Both historical bug classes are provably blocked; the rotation is bit-identical to the
official helper; physical sign patterns are correct in both hemispheres; all acceptance
numbers reproduced exactly.

## Numbers reproduced (reviewer's own run)

| Metric | acceptance.md | reviewer |
|--------|---------------|----------|
| Rotation vs `UEVNfromUXVY` max\|Δ\| | 0.0 (bit-identical) | 0.0e+00 ✓ |
| Ekman w_E vs WVEL corr | 0.738 | 0.738 ✓ |
| Ekman w_E vs WVEL sign-agree | 0.89 | 0.89 ✓ |
| WVEL comparison points | 48,383 | 48,383 ✓ |
| 2nd-rotation-drop reldiff shift | ~30% | 30% ✓ |
| Ekman sign-flip corr | ~−0.56 | −0.558 ✓ |
| w_E max off-equator | ~1.7e-5 m/s | 1.695e-5 ✓ |

## Attacks and how each held
- **The two rotations (the historical bug):** verified sign-for-sign against tutorial cells
  125/129/133/137; full pipeline `max|Δ|=0` vs the tutorial run on the same data. Held.
- **One-rotation version passes the tests?** Built the naive single-rotation curl →
  reldiff 30%, Ekman corr 0.500 / sign 0.64 — **fails** the teeth test AND the WVEL corr/sign
  gates independently. The eval-#2 bug is blocked. Held.
- **Stress grid position:** confirmed from real data — `oceTAUX` on i_g face, `oceTAUY` on
  j_g face (NOT tracer points); code correctly interpolates first (`already_at_center=False`);
  passing them as center-fields errors out. Held.
- **oceTAUX vs EXFtaux:** using EXFtaux instead → Ekman corr 0.502, fails the >0.6 gate.
  Wrong-variable would be caught. Held.
- **Units:** curl labeled `Pa m-1` (a stress curl, not s⁻¹); w_E in m/s; β term uses the
  center-interpolated zonal stress. Held.
- **Ekman sign + β term:** N. Pacific subtropical box curl −9.1e-8 Pa/m, w_E −1.1e-6 (down);
  S. Atlantic box curl +9.1e-8 (SH), w_E −1.0e-6 (down) — sign-correct both hemispheres. Held.
- **canon/dim-order:** applied correctly; broadcast unambiguous. Held.
- **WVEL interface level:** k_l=3 (−30 m); corr 0.65–0.74 across k_l 1–6, surface (k_l=0)
  correctly fails (−0.34) — level matters but the test isn't brittle. Held.
- **OMEGA:** 2π/86164 (sidereal) correct. Held.

## Caveats raised (not errors)
- **A (ACTED ON) — teeth threshold too loose.** The 2nd-rotation teeth test asserted
  `reldiff > 0.05`; the real dropped-rotation signal is ~0.30. The reviewer constructed a
  partial-error adversary: scaling the second rotation's SN to ~80–90% of correct lands at
  reldiff ≈ 0.055 and passes all four tests while being physically wrong. **Fixed:** measured
  the SN-scaling sensitivity — correct 0.000, SN×0.90 0.055, ×0.80 0.105, ×0.70 0.150,
  dropped(×0) 0.315 — and **tightened the threshold 0.05 → 0.20**, which catches the
  historical dropped-rotation bug (0.315) and a ≳30% SN error, while staying far clear of the
  correct code. Re-ran: 4/4 still pass.
- **B — near-equator w_E blowup not surfaced.** Off-equator max is 1.7e-5 m/s (as claimed),
  but the raw global max (within ±5°, where 1/f diverges) is ~8.5e-3 m/s. The acceptance
  wording should say "off-equator". *Documentation nit — the L3 guard already masks the
  equatorial band; no code change.*
- **C — `boundary='extend'` vs the tutorial's default `diff`:** numerically identical
  (`max|Δ|=0`, LLC topology handles connectivity via the grid axes, not the boundary kw).
  Harmless. No change.
- **D — WVEL level (k_l=3) choice:** physically reasonable (Ekman-layer base); corr is only
  mildly level-sensitive. No change.
- **E — EXFtaux mis-use guard is indirect:** passing the wrong-stagger stress raises a
  cryptic xgcm error rather than a clear message. Usability nit. No change.

## Outcome
One actionable finding (A), fixed and re-verified. No correctness errors — notably, both
historical rotation bugs are confirmed blocked. `compute-curl` clears Rung 7 → ⚠️ → ✅ DONE.
Standing-adversarial-review loop continues on `compute-steric-height` (the last ⚠️ skill).
