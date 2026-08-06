# Eval 6 — Rung-7 adversarial review: `compute-steric-height`

**Date:** 2026-08-06.
**Reviewer:** independent Sonnet subagent (fresh context, different model family from the
builder). Instructed to *disprove* the steric-height + thermo/halo-decomposition skill
against the real Steric Height tutorial, first principles, the vendored JMD95 EOS, and the
cached Jan-2000 data. This skill has the richest attack surface of the set (vendored EOS,
z*/hFacC weighting, too-shallow masking, the Pa↔dbar conversion, the T/S decomposition).

## Verdict: **only caveats — could not disprove. Zero confirmed errors.**

Every attack held. All acceptance numbers reproduced exactly on real data.

## Numbers reproduced (reviewer's own run)

| Metric | acceptance.md | reviewer |
|--------|---------------|----------|
| EOS check value densjmd95(35.5,3,3000) | 1041.83267 | 1041.83267 (err 3.6e-7) ✓ |
| Sum-of-parts median residual | 0.005 m | 0.0046 m ✓ |
| Sum-of-parts corr | 0.9998 | 0.9998 ✓ |
| Steric-vs-SSH corr | 0.921 | 0.9214 ✓ |
| Valid points | 47,674 | 47,674 ✓ |
| Steric range | [−3.22, 2.18] m | [−3.220, 2.184] m ✓ |
| Teeth (specvol sign flip) | 0.92 → −0.92 | 0.92 → −0.92 ✓ |

## Attacks and how each held
- **Pa↔dbar 1e-4 factor:** applied in all required places (specvol_standard AND the
  thermo/halo decomposition); k=0 → 5.05 dbar (≈5 m ✓), 2000 m → ~2019 dbar. Held.
- **Integral sign:** the tutorial's `Zl`(top,0 m)/`Zu`(bottom,−10 m) naming makes `dp<0`;
  combined with the explicit −V'/g, warm/light columns get higher steric height. Warm pool
  +0.231 m (de-meaned), Southern Ocean −1.60 m; steric-SSH corr +0.921. Held.
- **z*(rstarfac) + hFacC weighting:** both present, match tutorial cell 18; hFacC applied
  to dp only (no double-count); removing rstarfac changes corr by <3e-5. Held.
- **Reference bounds + bottom clip + too-shallow mask:** the clip uses the *clipped* face
  pressure — without it all 60,646 ocean cells would look deep (0 too-shallow, catastrophic);
  with it, 12,972 shallow columns are correctly excluded → exactly 47,674 valid. Held.
- **thermo/halo hold-which-variable:** `densjmd95(S_r, THETA, p)` for thermo,
  `densjmd95(SALT, θ_r, p)` for halo — argument order `(s,θ,p)` matches the tutorial exactly;
  thermosteric correlates 0.926 with SST. Not swapped. Held.
- **Global-mean-removal consistency:** all three (h, thermo, halo) de-meaned over the same
  valid mask; post-de-mean means all machine-precision zero. Held.
- **canon/dim-order:** applied before positional numpy; matches the tutorial transpose. Held.

## Caveats raised (not errors)
- **B (ACTED ON) — thermo/halo LABEL SWAP escapes all tests.** Because thermo+halo sums
  identically either way, sum-of-parts can't distinguish a swap; the reviewer confirmed a
  swapped version passes every test. The code is correct (thermosteric-vs-SST corr 0.926),
  but nothing *guarded* against a future regression. **Fixed:** added
  `test_thermo_halo_labels_not_swapped` — thermosteric must track SST (measured corr 0.926;
  halosteric is −0.241), asserting `corr(thermo,SST) > 0.5` and `> corr(halo,SST)`. A label
  swap flips these and fails decisively. Suite now 6 tests, all pass.
- **A — misleading inline comment.** `press_ref_k_u`/`press_ref_k_l` comments say
  "upper/lower faces" but `Zl` is physically the *top* face (0 m) and `Zu` the *bottom*
  (−10 m) in the ECCO convention — the code is correct (matches the tutorial's own naming
  and the double-negative delivers the right sign), but the comment can mislead a future
  maintainer. *Left as-is to stay faithful to the tutorial's naming; noted here.*
- **C — rstarfac range.** Reaches 0.76 in shallow coastal water but is 0.998–1.0005 in the
  valid region; negligible impact. Correct to include. No change.

## Outcome
One actionable finding (B — label-swap coverage gap), fixed with a new SST-correlation
guard and re-verified. No correctness errors. `compute-steric-height` clears Rung 7 →
⚠️ → ✅ DONE.

**This completes the Phil-free science set** — all five calculation skills (OHC, geostrophy,
thermal wind, curl+Ekman pumping, steric height) now have clean Rung-7 adversarial passes.
Across evals 4–6, every pass found zero correctness errors and one test-coverage/threshold
gap each (reconstruction threshold, curl teeth threshold, thermo/halo label guard) — all
fixed. The standing adversarial-review loop did its job: no science bugs, but three real
test-hardening improvements.
