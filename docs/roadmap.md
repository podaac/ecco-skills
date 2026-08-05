# ECCO Skills Roadmap

The build sequence for the ECCO skills, from the proven environment foundation through
the physical-oceanography calculations. This is the *plan*; `design.md` is the detailed
source of truth for how each skill works. Keep both in sync as skills get built.

**Sequencing rule:** each phase is usable on its own and de-risks the next. We don't
build higher-level physics until the Level 0–1 primitives are proven on real data.

**Build pattern (every calculation skill):** ships as `SKILL.md` (guidance +
teach-as-you-go) + vetted `scripts/` + `references/` (closure/acceptance snippets). A
skill isn't "done" until it clears the **`docs/verify.md` V&V protocol** (official-helper
match, tutorial reproduction, conservation, teeth-verified tests, and a standing
adversarial-review pass) — reproducing "seems reasonable" is not enough; independent
evidence is required. Skills invoke `.venv/bin/python` directly (see design.md →
Interpreter policy).

---

## ✅ Built & tested — environment foundation

| Skill | Status | Purpose |
|---|---|---|
| **`ecco-setup`** | ✅ done | Survey Python → build `.venv` → install stack → auto-handoff to verify |
| **`ecco-setup-verify`** | ✅ done | Prove the environment works (imports + real `get_llc_grid` smoke test) |

---

## Phase 1 — Data + first vertical slice ✅ *(complete)*

Get real data flowing and prove the whole skill pattern end-to-end with the simplest
calculation.

| Skill | Level | Status | Notes |
|---|---|---|---|
| **`ecco-common`** (shared lib) | — | ✅ done | `load_grid()`, `load_field()`, CMR download, `./data/ecco` cache; the Option A composition backbone |
| **`load-grid`** | 0 | ✅ done | Downloads geometry via CMR direct URL, returns grid dataset + `get_llc_grid` object; cache-hit verified |
| **`load-field`** | 0 | ✅ done | Downloads any ECCO field by ShortName + `months=`; size guard + month-edge fix verified |
| **`compute-ocean-heat-content`** | 4 | ✅ done | **Recipe 1** — volume-weighted OHC + change between months; validation trail; acceptance recorded |

**Phase 1 complete.** The load skills + Recipe 1 are built and tested end-to-end. Recipe
1 established the calc-skill pattern (`SKILL.md` + shared-helper composition +
validation trail + `references/acceptance.md`) that every later skill copies. Acceptance
highlights: volume-mean THETA 3.59 degC (matches known ocean value), ocean volume within
0.4% of literature, Jan 2000→2010 warming +7.8×10²² J.

---

## External evaluation (2026-07-25) — fixes applied

**Round 3 additions:** (a) **size-guard bug** — granule size now read from the archive
entry matching the `.nc` filename (preferring `SizeInBytes`), not the "first MB entry"
which could be the tiny `.sha512` sidecar and defeat the guard; checksum captured too.
(b) **Whole-request guard** — size is checked once across ALL requested months/days
(per-key checking let a 40-day/1.2 GB request slip through 29 MB at a time — caught by
testing, now fixed). (c) **`days=` selector** — daily granules overlap at *midnight*
like monthly at month-edges; `days=['YYYY-MM-DD']` queries mid-day + filename-filters.
(d) **Daily offline backfill** — the index key regex only matched monthly `YYYY-MM`;
now handles daily `YYYY-MM-DD` (self-caught during testing). (e) transport recipe:
reduce each face on its own dims before adding (avoids xarray outer-broadcast); Recipe 4
summary lists both X and Y flux names. (f) curl pseudocode branch fixed (tracer-point
inputs skip interp cleanly). (g) OHC `SKILL.md` L2 relabeled "numeric sanity."

**Automated test suite added (eval-round-3 #4):** `.claude/skills/ecco-common/tests/`
has 13 offline regression tests for the loader/cache/access layer (size-by-filename,
pagination, whole-request guard, selectors, backfill, offline reuse, live resolution);
`run_all_tests.py` runs all 23 tests (13 + 10 OHC). Verified it catches a reintroduced
size-guard regression.

Still open: wire tests into CI; exact lockfile; cached-file checksum *verification*
(captured, not yet checked); Recipe 2 acceptance contract; index locking for concurrent
runs.

Two review rounds by an external model. Round-2 additions (verified against the
tutorials): tracer-section transport now combines **both** X- and Y-face masks
(`ADVx+DFx`·maskW + `ADVy+DFy`·maskS, per the MHT tutorial); curl now has the **second
derivative-vector rotation**; **daily collections** + live CMR ShortName resolution;
`load_field` **selector validation**; cache-index **backfill + atomic writes**; OHC
**time-coordinate check**; corrected the `geos_vel_compute` reference (it's in
`ecco_po_tutorials.py`, not `ecco_v4_py`) and confirmed `plot_proj_to_latlon_grid` exists.

Round-1 issues, now **fixed**:
- **Geostrophic formula omitted density** (`design.md` had `v_g=(1/f)·∂Φ/∂x`; correct is
  `dp=rhoConst·∂Φ/∂x`, then `/(ρ·f)` with `ρ=rhoConst+RHOAnoma`). Fixed in
  `compute-geostrophic-velocity`, Recipe 2, and gotcha #1. Recipe 2 now lists `RHOAnoma`.
- **Section transport double-counted `hFac`** — `*VELMASS` is already mass-weighted;
  matches official `calc_section_vol_trsp` (`UVELMASS·drF·dyG`, no `hFac`, no bolus for
  *volume*). Fixed in `compute-transport-across-section`, Recipe 4, gotcha #6.
- **Curl too naive for LLC** — first pass added one rotation; **eval #2 caught that a
  SECOND rotation (of the derivative vectors) was still missing.** Now fully specified
  (rotate components → diff both axes → interp → rotate derivatives → combine).
- **CWD dependence** — project root now derived from file location, not `os.getcwd()`.
- **Offline cache + CMR pagination** — added a cache index (offline reuse) and
  `CMR-Search-After` paging (no silent 200-granule truncation).
- **OHC validation NaN gap** — L1 now catches wet-cell NaNs; L2 is a real assertion.
- **Doc drift** — `--reset` (built), `load-field` (no S3), tutorial count (four),
  Python-3.12 cap reframed as tested policy.

Still open (correctly gated): budget term lists / residual definitions (Phil), an
exact lockfile + CI golden-value regression, Linux/Windows testing.

## Phase 2 — Grid operation primitives (Level 1) *(DEFERRED — extract on 2nd-caller demand)*

The reusable C-grid mechanics almost every physics calc needs.

| Skill | Level |
|---|---|
| **`spatial-difference`** | 1 |
| **`spatial-interpolation`** | 1 |
| **`vertical-difference`** | 1 |
| **`rotate-to-geographic`** | 1 (CS/SN — critical for tiles 7–12) |
| **`compute-coriolis`** | 4-helper |

**Decision (2026-07-25): DEFER — do NOT build these as standalone skills up front.**
Rationale:
- This logic is **already written and Rung-1 verified**, just *inlined* inside
  `compute-geostrophic-balance` (`xgcm.diff`, `interp_2d_vector`, the Coriolis formula).
  Phase 2 is un-*extracted*, not un-built.
- Extracting a primitive against a **single** known caller tends to bake in the wrong
  interface (which grid positions? scalar vs vector? boundary handling?). A shared
  building block should be shaped by real demand from *several* callers.
- Refactoring already-verified code into primitives delivers **no new science** and
  forces a re-verification pass.

**Rule: extract each primitive when the SECOND caller appears** — i.e. when we build the
next skill that needs it (curl for Ekman, or thermal wind). At that point there are 2+
concrete callers to shape the interface; extract the primitive as part of that build and
refactor geostrophy onto it, re-running its Rung-1 test to prove the refactor is neutral.

**Reminder when they are built:** ECCO tutorials use the xgcm `boundary=`/`fill_value=`
API and `ecco.get_llc_grid()` — correct for our pinned xgcm 0.9.0 (do **not** use the
0.10 `padding=` API). See design.md gotcha #9.

---

## Phase 3 — Weighting/masking + first medium calc (Level 2)

| Skill | Level | Status |
|---|---|---|
| **`compute-geostrophic-balance` (Recipe 2)** | 4 | ✅ BUILT 2026-07-25 (Rung-1 verified) |
| **`plot-ecco-field`** — one skill, `--mode tile\|alltiles\|global`; **consolidates** the originally-planned `plot-single-tile` / `plot-masked-2d` / `plot-global-map` | 6 (visualization) | ✅ BUILT 2026-07-25 |
| **`volume-weight`, `area-weight`, `apply-mask`, `global-sum`, `global-mean`** | 2 | implicit in calc skills so far; not yet standalone building blocks |

**Recipe 2 status:** `compute-geostrophic-balance` is built and **Rung-1 verified** — its
`u_g`/`v_g` match the official `ecco_po_tutorials.geos_vel_compute` to <1e-9 m/s over 2.24M
points (first skill to satisfy Rung 1). Computed in model coordinates; equator masked.
⚠️ Rung-7 adversarial pass pending before "done". Note we built the calculation directly
against the official helper rather than first extracting the separate Level-1 primitives
(`spatial-difference`, etc.) — those can be refactored out later; the vetted result came
first. Plotting skills and the geostrophy-vs-model-velocity *comparison* remain to build.

---

## Phase 4 — Sections & transports (Level 3 + flux)

The higher-value science Phil asked about.

| Skill | Level |
|---|---|
| **`find-indices-along-latitude`, `extract-transect-data`, `make-section-mask`** | 3 |
| **`compute-transport-across-section`** + **Recipe 4** | 4 (bolus + face-area care) |
| **`compute-tracer-budget`** (volume/heat/salt budget) | 4 (closure oracle — the crown jewel) |
| **`decompose-flux`** (Recipe 5) | 4 |

**⚠️ Gated on Phil:** the 3 open questions must be answered before this phase locks —
validation benchmark targets, the flux-decomposition grouping (3 vs 4 terms), and exact
budget term lists. The *machinery* (sections, masks) can be built in parallel, but the
science shouldn't be finalized until Phil weighs in.

---

## Phase 5 — Ageostrophic & diagnostics (Level 5)

| Skill | Level | Status |
|---|---|---|
| **`compute-curl`, `compute-ekman-transport`** + **Recipe 6 (Ekman pumping)** | 4–5 | designed |
| **`compute-thermal-wind` + `reconstruct-velocity-from-thermal-wind`** (Recipe 3) | 4 | ✅ BUILT 2026-08-04 (one skill; ⚠️ Rung-7 adversarial pass pending) |
| **`compute-steric-height`** | 4 | designed |
| **`compute-normalized-difference`** | 5 | designed |

**Recipe 3 status (built ahead of the rest of Phase 5, as the safe next step):**
`compute-thermal-wind` covers both the shear and the velocity reconstruction. **No official
helper exists** (Rung 1 N/A — only `geos_vel_compute` is in `ecco_po_tutorials.py`), so it's
verified by three cross-checks: an analytic identity vs ∂/∂z of geostrophic velocity (corr
0.999), an independent comparison vs the model's actual velocity shear (corr 0.64/0.85), and
the tutorial's reconstruction-vs-actual normalized-diff diagnostic (~0.23). Teeth-verified.
**Level-1 primitives still inlined** — thermal wind reused geostrophy's diff/interp *pattern*
by re-implementing it (not by extracting shared primitives); extraction still deferred to the
next caller (curl). ⚠️ A Rung-7 adversarial pass is the remaining gate before "done".

---

## Notes on the plan

1. **Phase 4 is the value peak but also the most gated.** It's what Phil actually asked
   for (Atlantic transports, budgets), but it can't be finalized without his three
   answers. Worth a nudge to Phil before we get there.

2. **Phases 2–3 could compress.** If we want science faster, we could build only the
   Level 1 primitives that Recipe 2 specifically needs, rather than all of Level 1–2
   upfront. Trade-off: less reuse groundwork, but a faster path to the geostrophic-
   balance demo.

3. **Cross-platform / lockfile debt** carried from the environment phase: test setup on
   Linux/Windows and on a machine lacking a supported Python; freeze an exact
   `pip freeze` lockfile. Not blocking Phase 2, but shouldn't be forgotten.

4. **Carried TODOs (non-blocking):**
   - `load-field`: friendlier UX when `~/.netrc` Earthdata credentials are missing
     (currently surfaces a 401 with a pointer, could guide account/`.netrc` setup).
   - Recipe 1: seasonal-cycle averaging for a rigorous OHC *trend* (snapshot
     month-to-month differences are noisier).
   - ✅ **Git repo now set up** — public at https://github.com/podaac/ecco-skills
     (remote `origin`, branch `main`). `.gitignore` (`/data/`, `/.venv/`, `/plots/`)
     is live; `data/`, `.venv/`, `plots/` confirmed untracked. **Remaining:** add a
     README before it's useful to outside visitors; wire the test suite into CI.

5. **Every calc skill ships a `scripts/test_validation.py`** (negative + positive guard
   tests), per the pattern Recipe 1 established. A guard that only ever passes could be
   silently broken; the tests prove it fires on bad input too.

6. **Keep skills as composable BUILDING BLOCKS for now** (decided 2026-07-25). Each skill
   does one thing (load / compute / plot) with a clean CLI + importable helper. We are
   **deferring higher-level composition skills** (e.g. "plot two fields side by side",
   "geostrophy-vs-model-velocity diagnostic") until the building-block set is broad enough
   to know which compositions are actually worth wrapping. Rationale: less surface to
   verify/maintain, and premature convenience wrappers tend to bake in the wrong shape.
   Novel one-off combinations can be done as thin glue over the skill helpers in the
   meantime (like the scratch `make_gallery.py` / `plot_ssh_vs_geos.py` at repo root —
   those are demos, NOT skills). Revisit adding `plot_pair()` / comparison modes later.
