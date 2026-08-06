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

## Phase 2 — Grid operation primitives (Level 1) *(✅ EXTRACTION PASS DONE 2026-08-05 — partial, evidence-driven)*

The reusable C-grid mechanics the physics calcs need. **These are `ecco_common` library
functions, NOT standalone skills** (same category as `load_grid`/`plots`) — they live in
the new module `ecco_common/grid_ops.py`, imported by the calc skills.

**Decision (2026-07-25): DEFER standalone extraction up front** — the logic was inlined and
Rung-1-verified inside the calc skills; extracting against a single caller bakes in the
wrong interface. **Executed as a partial pass 2026-08-05** once the Phil-free calc set was
complete (OHC, geostrophy, thermal wind, curl, steric). Key principle held: **extract only
primitives with ≥2 real callers**, verified by auditing the actual code — not the count this
roadmap originally guessed.

| Primitive (in `ecco_common.grid_ops`) | Real callers | Status |
|---|---|---|
| `OMEGA` + `coriolis(ds_grid)` (was `compute-coriolis`) | 3 — geostrophy, thermal-wind, curl | ✅ EXTRACTED |
| `canon(da)` (dim-order normalize after xgcm ops) | 3 — thermal-wind, curl, steric | ✅ EXTRACTED |
| `grad_to_center(scalar, …)` (was `spatial-difference` + `spatial-interpolation`, fused: diff/dxC + interp_2d_vector) | 2 — geostrophy, thermal-wind | ✅ EXTRACTED |
| `rotate-to-geographic` (CS/SN) | **1 — curl only** | ⏸️ NOT extracted (1 caller) |
| `vertical-difference` (∂/∂k ÷ drC) | **1 — thermal-wind only** | ⏸️ NOT extracted (1 caller) |
| volume/area weighting (`rA·drF·hFacC`, area-weighted mean) | 2 — OHC, steric | ⏸️ NOT extracted (deferred; related-but-not-identical) |

**Correction to the earlier framing:** this roadmap and design.md had listed *five* Level-1
primitives as if all were due. The real caller audit showed only **three** have ≥2 callers.
`rotate-to-geographic` and `vertical-difference` each have exactly **one** caller — so
extracting them now would violate our own "shape against several callers" rule. They stay
inlined until a genuine 2nd caller appears (that build is the natural trigger). Note curl's
rotation is bit-identical to the official `ecco_v4_py.vector_calc.UEVNfromUXVY` — when a 2nd
rotation caller arrives, **adopting the official helper** is likely better than extracting
our own.

**Neutrality proven:** all four refactored skills (geostrophy, thermal-wind, curl, steric)
re-ran their full Rung-1/cross-check suites after the refactor with **identical numbers**
(geostrophy still matches `geos_vel_compute` <1e-9; thermal-wind identity corr 0.9992; curl
rotation max|Δ|=0 vs UEVNfromUXVY; steric sum-of-parts 0.0046 m). `grad_to_center` returns
**native (un-canon'd) dim order** on purpose so geostrophy's reference match stays exact;
callers needing positional numpy call `canon()` themselves. OHC was NOT refactored (it uses
none of the three). New offline test: `ecco-common/tests/test_grid_ops.py`.

**Reminder:** ECCO tutorials use the xgcm `boundary=`/`fill_value=` API and
`ecco.get_llc_grid()` — correct for our pinned xgcm 0.9.0 (do **not** use the 0.10
`padding=` API). See design.md gotcha #9.

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
✅ Rung-7 adversarial pass cleared (2026-07-25) — geostrophy is DONE. Note we built the
calculation directly against the official helper rather than first extracting the separate
Level-1 primitives (`spatial-difference`, etc.) — those were later refactored into
`ecco_common/grid_ops.py` (2026-08-05). The geostrophy-vs-model-velocity *comparison* skill
remains to build.

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
| **`compute-curl`** + **Recipe 6 (Ekman pumping)** | 4–5 | ✅ DONE 2026-08-06 (curl + Ekman pumping; Rung-7 adversarial pass clean — `docs/eval5.md`; both historical rotation bugs confirmed blocked) |
| **`compute-thermal-wind` + `reconstruct-velocity-from-thermal-wind`** (Recipe 3) | 4 | ✅ DONE 2026-08-06 (one skill; Rung-7 adversarial pass clean — `docs/eval4.md`) |
| **`compute-steric-height`** (Recipe 3-steric) | 4 | ✅ DONE 2026-08-06 (steric + thermo/halo split; Rung-7 adversarial pass clean — `docs/eval6.md`) |
| **`compute-ekman-transport`** (Q6 — transport M=τ/(ρf) vs upper-ocean velocity) | 4–5 | ⏸️ DEFERRED — gated on Phil Q5 (see below) |
| **`compute-normalized-difference`** | 5 | designed |

**🎯 The Phil-free calculation set is COMPLETE and fully verified** (OHC, geostrophy, thermal
wind, curl+Ekman pumping, steric height — **all five ✅ DONE, all cleared Rung-7 adversarial
review**; evals 4–6 on 2026-08-06 found zero confirmed errors, one test-hardening fix each).
The Level-1 primitive-extraction pass this unlocked has also been done (partial — see
Phase 2). Everything remaining is either Phil-gated (transports, budgets, decompose-flux,
**and `compute-ekman-transport`** — see below) or a small add (`compute-normalized-difference`).

**`compute-ekman-transport` DEFERRED (2026-08-05, gated on Phil Q5).** Unlike every other
Phil-free skill, Ekman transport has **no ECCO tutorial** (only 4 Intro-to-PO notebooks
exist: geostrophic, thermal wind, steric ×2) — so no Rung-1 helper and no Rung-2 number. The
formula `M = (τ_y/ρf, −τ_x/ρf)` is trivial; the entire scientific value is the comparison to
the model, which is precisely Phil's Q6 tangled with his scientific-fit question. Rather than
guess the comparison (ageostrophic residual vs raw upper-ocean velocity vs …) and ship a
skill whose verification bottoms out below the bar the other five cleared, we deferred it and
added **Q5 to `docs/questions-for-phil.md`** asking which comparison + what "upper ocean"
depth he wants. His answer unblocks it immediately; the build itself is small (reuses curl's
stress handling + geostrophy's velocities).

**Steric-height status (built 2026-08-05):** steric height anomaly (∫−V'_sp/g dp to 2000 dbar)
+ thermosteric/halosteric decomposition. **Vendored the MITgcm JMD95 EOS** (`ecco-common/
vendor/jmd95.py`, pinned 3f0fcca) since no EOS was available (gsw/TEOS-10 absent, none in
`ecco_v4_py`); base term uses the model's own RHOAnoma. No steric helper (Rung-1 N/A; EOS
check-value anchor instead). Verified: sum-of-parts (thermo+halo ≈ full) median 0.005 m /
corr 0.9998; **steric ≈ SSH** corr 0.921 (independent, different collection). Teeth: specvol
sign flip → steric-vs-SSH corr −0.92. Fixed a de-meaning/masking bug found during the build.
✅ Rung-7 adversarial pass clean (2026-08-06, `docs/eval6.md`) — one caveat fixed (added a
thermo/halo label-swap guard vs SST, which sum-of-parts couldn't catch). Steric is DONE.

**Recipe 6 status (built 2026-08-05):** `compute-curl` does wind-stress curl (the LLC
**two-rotation** sequence) + Ekman pumping vs the model's actual `WVEL`. No official curl
helper exists (Rung-1 N/A); verified by matching the official rotation helper
`vector_calc.UEVNfromUXVY` bit-for-bit and by `w_E` vs `WVEL` (corr 0.74, sign-agree 0.89
at ~30 m). Teeth: dropping the 2nd rotation shifts the curl ~30%; sign flip drops the WVEL
corr to −0.56. **Fixed two design-doc errors during the build:** oceTAUX/oceTAUY are on the
U/V *faces* (not tracer points, as the doc claimed) so they're interpolated first; and the
two rotations use the *same* formula (the "differing sign conventions" note was wrong).
✅ Rung-7 adversarial pass clean (2026-08-06, `docs/eval5.md`) — **both historical rotation
bugs confirmed blocked**; one loose-teeth-threshold caveat fixed (0.05→0.20). Curl is DONE.
`compute-ekman-transport` (Q6) is a separate skill, now DEFERRED pending Phil Q5 (see the
deferral note above).

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
