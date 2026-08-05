# ECCO Skills — Verification Status Dashboard

**What this is:** the current verification scorecard for every skill, scored against the
ladder in [`docs/verify.md`](verify.md). `verify.md` is the *protocol* (the rules);
this file is the *status* (where each skill actually stands today).

**Legend:** ✅ verified · ⚠️ partial / evidence-backed but not fully done · 🔴 needs Phil ·
`N/A` rung doesn't apply · `TODO` not yet done.

**Ladder rungs** (see verify.md for detail): 1 official-helper match · 2 tutorial number ·
3 conservation closure · 4 physical sanity · 5 internal cross-check · 6 regression tests
(teeth-verified) · 7 standing adversarial review.

**"Done" bar:** a science skill is *done* only when every applicable rung is satisfied
(or its N/A justified), a teeth-verified regression test exists, and it has passed a
dedicated Rung-7 adversarial pass — with evidence recorded in its `references/`.

_Last updated: 2026-07-25._

---

## Science skills

### `compute-ocean-heat-content` (Recipe 1) — ✅ DONE (all applicable rungs cleared 2026-07-25)

| Rung | Status | Evidence / gap |
|------|--------|----------------|
| 1 official helper | N/A | No OHC/volume-weighted-mean helper in `ecco_v4_py` 1.8.1 (checked `dir()`, `scalar_calc`). Cell-volume cross-checked instead (Rung 5). |
| 2 tutorial number | ✅ | Reproduces the scalar-quantities tutorial's published **total ocean surface area = 3.58E+08 km²** exactly (`(rA·maskC).isel(k=0).sum()`), now an automated test in `test_validation.py`. (Validates the grid geometry underpinning the OHC volume weighting; the tutorial publishes no OHC scalar itself.) |
| 3 conservation | N/A | Snapshot heat content, not a budget. |
| 4 physical sanity | ✅ | Volume-mean THETA 3.594 °C (≈3.5 known); THETA range [-1.97, 31.94] °C; runtime L3 guard. |
| 5 cross-check | ✅ | Ocean volume 1.335e18 m³, within 0.4% of literature; `hFacC` confirmed to zero land. |
| 6 regression | ✅ | `scripts/test_validation.py` (10) + `ecco-common/tests/` (13); teeth verified. |
| 7 adversarial | ✅ | Dedicated "disprove OHC" pass (2026-07-25, independent agent): **zero confirmed errors**; verified volume formula, no hFac/maskC double-count, constants, potential-temp handling, NaN handling, benchmarks-not-luck, change computation, and that no official helper is being skipped. Three caveats raised (not errors) — 2 documented, 1 fixed. |

**Status: DONE.** All applicable rungs cleared. The adversarial pass raised three
*caveats* (not errors): (i) fixed geometry omits z\*/SSH volume term — now documented in
SKILL.md; (ii) snapshot aliasing — documented; (iii) loose L3 volume-mean band — **fixed**
(tightened `[0,10]` → `[2,6]` °C). Record: `compute-ocean-heat-content/references/acceptance.md`.

### `compute-geostrophic-balance` (Recipe 2) — ✅ DONE (all applicable rungs cleared 2026-07-25)

| Rung | Status | Evidence / gap |
|------|--------|----------------|
| 1 official helper | ✅ | Reproduces `ecco_po_tutorials.geos_vel_compute` to <1e-9 m/s over 2,237,682 points (vendored @ `3f0fcca`). *Reproducibility* — a shared bug would pass; see Rung 5. |
| 2 tutorial number | N/A | Tutorial publishes figures/arrays, not a scalar. |
| 3 conservation | N/A | Diagnostic velocity, not a budget. |
| 4 physical sanity | ✅ | Surface geostrophic speed median ~0.029 m/s off-equator; WBC-box max ~0.32 m/s. |
| 5 cross-check | ✅ | **Independent:** matches ACTUAL model UVEL/VVEL at ~200 m (corr 0.998; median norm-diff 0.032; 45,745 pts). Different variable + code path → rules out a bug shared with the reference. **Strongest correctness evidence.** |
| 6 regression (teeth) | ✅ | `test_geostrophic.py` (Rung-1 match + independent-velocity check + 5 guards); teeth verified. |
| 7 adversarial | ✅ | Independent disprove-pass (2026-07-25): zero confirmed errors. Its one fair critique (overstated Rung-1 claim) is fixed — added the Rung-5 independent test + corrected language. |

**Status: DONE.** The adversarial pass found no correctness errors; acting on its critique
strengthened the evidence (independent velocity check added). Documented limitations
(not errors): model-axis output, coastal NaN-bleed, tile-seam `extend` — all inherited
from the official reference. Record: `compute-geostrophic-balance/references/acceptance.md`.

---

## Infrastructure skills

*(Not science calculations — the physics rungs 2–5 don't apply. Verified via official
helpers where relevant + the `ecco-common` regression suite.)*

| Skill | Status | Evidence | Gaps |
|-------|--------|----------|------|
| `ecco-setup` | ✅ | Wheels-only install, `--reset` re-resolves `xgcm<0.10`, auto-handoff, guided "no Python" stop — tested on macOS/arm64/3.12.13. | Linux/Windows testing TODO. |
| `ecco-setup-verify` | ✅ | Exercises official `ecco.get_llc_grid` on real geometry; passes from any CWD. | — |
| `load-grid` | ✅ | Builds grid via official `ecco.get_llc_grid` (Rung 1); regression-covered; runs from any CWD. | — |
| `load-field` | ✅ | CMR pagination, size-guard-by-filename, month/day midpoint selection, backfill, offline reuse, selector validation — 13-test suite, teeth-verified. | Download **checksum verification** not yet implemented (checksum captured only). |
| `plot-ecco-field` | ✅ | Wraps official `ecco_v4_py` plotters (`plot_tile`/`plot_tiles`/`plot_proj_to_latlon_grid`); verified by producing a physically-correct global SST map + model-orientation tile. Headless (Agg → PNG). | Visual output not auto-regression-tested (would need image hashing); relies on the official plotter's own correctness. |

---

## Test suites

| Suite | Count | Teeth-verified? |
|-------|-------|-----------------|
| `ecco-common/tests/test_ecco_common.py` | 13 | ✅ (reintroducing the size-guard sidecar bug fails it) |
| `compute-ocean-heat-content/scripts/test_validation.py` | 10 (+1 Rung-2 tutorial check) | ✅ (bad-input cases fail; land-NaN passes) |
| `compute-geostrophic-balance/scripts/test_geostrophic.py` | Rung-1 match + 5 guards | ✅ (breaking equatorial mask fails it) |
| Run all: `.claude/skills/run_all_tests.py` | all of the above | — |

**Not yet automated (open, per verify.md / evals):** CI wiring; exact dependency lockfile;
cached-file checksum *verification*; index locking for concurrent runs.

---

## Standing process (Rung 7)

Every new/changed science skill gets an **independent adversarial review** before it's
called done — an external AI instance instructed to *disprove* it against the tutorials
and installed helpers. Prior rounds logged in `docs/eval-issues.md`, `docs/eval2.md`,
`docs/eval3.md`. **Keep this loop running** — it has been the highest-yield check.

---

## How to keep this current

Update this dashboard **in the same step** a skill's verification status changes (new
rung satisfied, new gap found, adversarial pass completed) — same living-doc rule as
`design.md`. When a skill reaches "done", change its ⚠️ to ✅ here and in its `SKILL.md`
header.
