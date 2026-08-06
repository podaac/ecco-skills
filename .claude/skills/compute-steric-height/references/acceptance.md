# Acceptance evidence — compute-steric-height

V&V per `docs/verify.md`. Recipe 3-steric (steric height anomaly + thermosteric/halosteric
decomposition), built from the official `Steric_height.ipynb` tutorial (pinned 3f0fcca).

## Run environment
- macOS/arm64, project `.venv`, Python 3.12.13, xgcm 0.9.0, ecco_v4_py 1.8.1, numpy ≥2.5.
- Data: `ECCO_L4_DENS_STRAT_PRESS_…` (RHOAnoma), `ECCO_L4_TEMP_SALINITY_…` (THETA, SALT),
  `ECCO_L4_SSH_…` (SSH, ETAN), + geometry — all Jan 2000.
- Verified 2026-08-05.

## Key decisions / findings

1. **Vendored the JMD95 equation of state.** The base steric integral uses the model's own
   `RHOAnoma` (no EOS), but the reference specific-volume profile and the thermo/halo split
   need a T,S→ρ EOS. None was available (gsw/TEOS-10 not installed; no EOS in `ecco_v4_py`
   or the vendored `ecco_po_tutorials.py`). Vendored the canonical MITgcm `jmd95.py` from
   `misc/jmd95.py` @ commit 3f0fcca (same pin as `ecco_po_tutorials.py`). **Only edit:**
   `np.asfarray` → `np.asarray(..., dtype=float)` (6 sites; removed in NumPy 2.0) — no
   numerical change, published check value still reproduces. See `vendor/README.md`.

2. **Bug found & fixed during the build (masking / de-meaning).** The first run failed the
   sum-of-parts check with a 1.97 m residual — because the full steric field had its global
   mean removed while thermo/halo did not, an apples-to-oranges comparison. Fix: de-mean
   thermo and halo over the **same** valid region before comparing (as the tutorial does).
   Also switched the runtime finite/bounds checks to xarray `.where(mask)` alignment (the
   initial positional-numpy broadcast mis-counted land columns, which sum to 0 not NaN).
   After the fix, the sum-of-parts residual is 0.005 m — the physics was right; the checks
   were comparing mismatched fields.

## V&V status: ✅ DONE — all applicable rungs cleared (Rung-7 adversarial pass 2026-08-06)

| Rung | Status | Evidence |
|------|--------|----------|
| 1 official helper | N/A (integral) | **EOS anchor:** vendored `densjmd95(35.5, 3, 3000)` = **1041.83267** == published (automated in `test_steric.py`). |
| 2 tutorial number | ✅ (operator) | Pipeline transcribed from `Steric_height.ipynb`; publishes maps not scalars. |
| 3 conservation | N/A | Diagnostic, not a budget. |
| 4 physical sanity | ✅ | Global-mean-removed steric anomaly range ≈ **[-3.22, 2.18] m**; spatial pattern high in warm subtropics / tropical W. Pacific, low in Southern Ocean — matches SSH. Land + too-shallow (bathymetry < 2000 dbar) masked. Figure: `plots/gallery/steric_height_2000-01.png` (gitignored). |
| 5 internal cross-check | ✅ | **(a) sum-of-parts:** thermosteric + halosteric ≈ full steric — median residual **0.0046 m**, corr **0.9998** over 47,674 points. **(b) INDEPENDENT physical:** steric height vs the model's **actual SSH** (both global-mean-removed): corr **0.921**; std(SSH) 0.79 m, non-steric residual std 0.31 m → steric explains ~85% of SSH variance. SSH is a different variable/collection → rules out a bug confined to the density path. |
| 6 regression (teeth) | ✅ | `scripts/test_steric.py` (6 tests): EOS check-value + sum-of-parts + steric-vs-SSH + **thermo/halo label guard (vs SST)** + a specvol-sign teeth test + offline guards. Teeth verified (below). |
| 7 adversarial review | ✅ | Independent Sonnet disprove-pass (2026-08-06, `docs/eval6.md`): **could not disprove — zero confirmed errors**; all acceptance numbers reproduced exactly. One actionable caveat (thermo/halo label-swap coverage gap) fixed with a new SST-correlation guard. |

## Teeth verification (2026-08-05)

- **Flip the specific-volume-anomaly sign:** steric-vs-SSH correlation flips **0.92 → −0.92**
  (steric would anti-correlate with sea level) → the `corr>0.85 & flipped<−0.85` teeth test
  fails on the broken version, confirming the sign/weighting is load-bearing.
- **Thermo/halo label guard (added after eval-6):** thermosteric must track SST — measured
  corr(thermosteric, SST) = 0.926 vs corr(halosteric, SST) = −0.241. A label swap (which
  sum-of-parts CANNOT catch, since thermo+halo is identical either way) would flip these;
  the guard asserts `corr(thermo,SST) > 0.5` and `> corr(halo,SST)`, failing a swap decisively.
- Offline synthetic guards: wrong units, non-tracer dims, absurd magnitude, and a
  deliberately-wrong sum-of-parts all correctly FAIL `validate()`; good input passes.
- Restored code: **6/6 steric tests pass; all project suites pass.**

## Results (Jan 2000)
- Steric height anomaly (global-mean-removed): min −3.22 m, max 2.18 m.
- Sum-of-parts: median |full − (thermo+halo)| = 0.005 m, corr 0.9998.
- Steric vs SSH: corr 0.921 (std SSH 0.79 m; non-steric residual 0.31 m).
- EOS: densjmd95(35.5, 3, 3000) = 1041.83267 (== published).

## Caveats (not errors)
- Steric height is relative to the 2000 dbar reference level; shallower columns excluded.
- Steric ≈ SSH is a physical relationship, not an identity (residual = non-steric/mass part).
- Decomposition is a linearization about (S_r=35, θ_r=0); small nonzero sum-of-parts residual.
- Only the spatial anomaly (global-mean-removed) is reported; a time-change (sea-level-rise
  term) is a natural follow-on, not built here.

## Rung-7 adversarial pass — DONE 2026-08-06
Independent Sonnet disprove-pass (full record: `docs/eval6.md`): **could not disprove —
zero confirmed errors**, all acceptance numbers reproduced exactly. Attacks on the 1e-4
Pa→dbar factor (all 4 sites), the integral sign, z*+hFacC weighting, the too-shallow
bottom-clip (exactly 47,674 valid columns), the hold-S-vs-hold-θ decomposition, and
global-mean-removal consistency all held. One actionable caveat — a thermo/halo label swap
would escape the suite (sum-of-parts can't distinguish it) — was fixed with a new
SST-correlation guard (`test_thermo_halo_labels_not_swapped`). Two lesser caveats documented
as non-errors (a misleading inline comment; negligible rstarfac range). **Skill is now ✅ DONE.**
