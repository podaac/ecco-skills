# Usage guide — running the ECCO Skills yourself

This is the hands-on guide for developers and analysts who want to run the skills
directly (rather than through an AI assistant). It covers setup, credentials, the exact
commands, the call sequence behind each question, running the tests, and the technical
notes worth knowing.

New here? The [README](../README.md) explains *what* the project is and what you can ask.
This document is the *how*.

---

## What a "skill" is here

These are **Agent Skills** in the Claude Code / Claude Agent SDK sense — not a plain
Python library. Each skill is a directory containing:

- **`SKILL.md`** — the guidance the agent reads: which fields to load and *why that one*,
  which grid position each quantity lives on, the correct operation sequence,
  masking/weighting rules, unit expectations, and known failure modes. This is the guardrail.
- **`scripts/`** — small, tested helper code the guidance points the agent to call rather
  than re-derive, so outputs are reproducible instead of freshly hallucinated each run.
- **`references/`** *(science skills)* — the skill's acceptance evidence: *why we trust
  this*, kept inside the skill folder so it travels with it.

A bare library makes the AI a *caller* (it can still call it wrongly); a skill makes the
AI a *guided author* that assembles the correct calculation and can fall back to the
vetted helper. You can also run the `scripts/` directly, as shown below.

---

## 1. Prerequisites

- **Python 3.11 or 3.12** (the supported band). The setup skill will tell you if your
  default `python3` is out of band — a common trap is a Homebrew `python3` that is *too
  new* (e.g. 3.14). On macOS: `brew install python@3.12`.
- A free **[NASA Earthdata Login](https://urs.earthdata.nasa.gov/)** account, with
  credentials in `~/.netrc` (needed to download ECCO data from PO.DAAC):
  ```
  machine urs.earthdata.nasa.gov
      login    YOUR_USERNAME
      password YOUR_PASSWORD
  ```

## 2. Build the environment

The `ecco-setup` skill surveys your machine's Python, builds an isolated project-local
`.venv/` (venv + pip only, **no conda**), installs the scientific stack, and verifies it
works:

```bash
python3 .claude/skills/ecco-setup/scripts/survey.py       # read-only: what Python do I have?
python3 .claude/skills/ecco-setup/scripts/setup_env.py    # build .venv and verify
```

Everything afterward runs with `.venv/bin/python` — no manual "activate" needed.

## 3. Run a calculation

```bash
# Ocean heat content, and its change between two months:
.venv/bin/python .claude/skills/compute-ocean-heat-content/scripts/run.py 2000-01 2010-01

# Geostrophic velocities for a month:
.venv/bin/python .claude/skills/compute-geostrophic-balance/scripts/run.py 2000-01

# Thermal-wind shear + velocity reconstruction for a month:
.venv/bin/python .claude/skills/compute-thermal-wind/scripts/run.py 2000-01

# Plot a global sea-surface-temperature map:
.venv/bin/python .claude/skills/plot-ecco-field/scripts/run.py \
    --collection ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4 \
    --var THETA --month 2000-01 --mode global --cmap RdYlBu_r
```

First use downloads only the granules requested (tens of MB) and caches them in
`./data/ecco/`; repeat runs reuse the cache. A size guard stops you before an accidental
multi-GB pull.

## 4. Run the tests (offline, no credentials needed)

```bash
.venv/bin/python .claude/skills/run_all_tests.py
```

---

## What actually runs when you ask a question

A user arrives with a *question*, not a skill name. Each question maps to a small chain of
skills that run **in order** — and every skill narrates what it's doing as it goes
(teach-as-you-go). The table shows the built calculations and the exact sequence each one
triggers:

| You ask… | Skills invoked, in order | What each step does |
|----------|--------------------------|---------------------|
| **"How much has ocean heat content changed between two months?"** | **1.** `load-grid` → **2.** `load-field` (THETA/SALT, month A) → **3.** *validate* → **4.** `load-field` (THETA/SALT, month B) → **5.** *validate* → **6.** *difference* | Grid gives cell volumes (`rA·drF·hFacC`); each month's temperature is volume-weighted and summed to OHC; the physical-bounds/benchmark checks run per month; the two are differenced (the change is what's physical). |
| **"Compute geostrophic velocities for a month."** | **1.** `load-grid` → **2.** `load-field` (density/pressure `RHOAnoma`,`PHIHYDcR`) → **3.** *compute* → **4.** *validate* | Grid supplies `dxC/dyC`, `YC`, and the xgcm object; the pressure gradient is differenced on the C-grid and interpolated to tracer points; `v_g = ρ⁻¹∂p/∂x / f`; runtime checks confirm grid position, units, and off-equator bounds. |
| **"Reconstruct the deep currents from density"** / **"where does density set the vertical current shear?"** (thermal wind) | **1.** `load-grid` → **2.** `load-field` (density `RHOAnoma`) → **3.** *compute shear* `∂u/∂z,∂v/∂z` → **4.** *reconstruct velocity from z0=−3000 m* → **5.** *validate* → **6.** `load-field` (UVEL/VVEL) → **7.** *cross-check vs actual velocity* | Grid supplies `dxC/dyC`, `drC`, `Z/Zl/Zu`, `YC`; the density gradient gives the thermal-wind shear `(g/fρ)∂ρ/∂x`; integrating it up/down from a level of no motion reconstructs the velocity; the reconstruction is then compared to the model's **actual** UVEL/VVEL (the currents field is loaded only for this check). |
| **"Show me a global map of sea-surface temperature."** | **1.** `load-grid` → **2.** `load-field` (THETA) → **3.** `plot-ecco-field` (`--mode global`) | Grid gives `XC/YC` for re-projection; the field is loaded for the requested month; the official `ecco_v4_py` plotter stitches the 13 tiles into a lat-lon PNG in `./plots/`. |
| **"Set up my environment"** / **"is my environment working?"** | **1.** `ecco-setup` (`survey` → build `.venv` → install) → **2.** `ecco-setup-verify` (auto-handoff) | Surveys the machine's Python, builds the isolated `.venv`, installs the stack, then proves it works (imports + a real `ecco.get_llc_grid` smoke test). Verify is also runnable on its own. |

**Under every `load-grid` / `load-field` step** sits the shared `ecco_common` layer: check
the local `./data/ecco` cache → on a miss, query the **NASA CMR** API for the granule's
real download URL → size-guard the request → download with `~/.netrc` auth → cache and
open as xarray. You never call that layer directly; the skills compose it.

> The rows above are the **built** calculations. Questions about transports, budgets,
> Ekman pumping, and steric height are *designed* (see [`design.md`](design.md) →
> Calculation Recipes) but not yet implemented — the table will grow as those land.

---

## Repository layout

```
.claude/skills/
├── ecco-setup/                 # build the project-local .venv (survey → install → verify)
├── ecco-setup-verify/          # prove the environment/toolchain works
├── ecco-common/                # SHARED library: loaders, cache, CMR access, plots
│   ├── ecco_common/            #   imported by every calc skill (composition backbone)
│   ├── vendor/                 #   pinned official ecco_po_tutorials.py (verification reference)
│   └── tests/                  #   offline regression suite
├── load-grid/                  # load LLC90 geometry + build the xgcm grid object
├── load-field/                 # download/cache any ECCO science field by month/day
├── plot-ecco-field/            # PNG of a field: single tile / all tiles / stitched global map
├── compute-ocean-heat-content/ # ✅ Recipe 1 — volume-weighted OHC + change between months
├── compute-geostrophic-balance/# ✅ Recipe 2 — geostrophic velocities from pressure/density
├── compute-thermal-wind/       # Recipe 3 — vertical shear from density + velocity reconstruction
└── run_all_tests.py            # single entry point for all offline test suites

docs/                           # living design + verification docs
```

---

## Key technical notes

- **`xgcm` is pinned `< 0.10`** (we use 0.9.0). `ecco_v4_py` 1.8.1's `get_llc_grid()`
  calls `xgcm.Grid(ds, periodic=False, ...)`, and `periodic=` was removed in xgcm 0.10 —
  so ECCO's own grid constructor crashes on ≥ 0.10. Do not relax this pin without
  re-testing `ecco.get_llc_grid()`.
- **Downloads use the NASA CMR API + `requests`/`.netrc` directly**, not `ecco_access`
  auto-resolution (which was unreliable in 0.3.1). The cache is project-local, on-demand,
  and size-guarded. The skills do **not** depend on any MCP server at runtime (see
  [`design.md`](design.md) → Data Access Pattern).
- **Data is never committed.** `.gitignore` excludes `/data/`, `/.venv/`, and `/plots/`.

---

## Deeper reference

- **[`design.md`](design.md)** — the detailed spec and living source of truth.
- **[`verify.md`](verify.md)** / **[`verify-status.md`](verify-status.md)** — the science
  verification protocol and per-skill scorecard.
- **[`roadmap.md`](roadmap.md)** — the build sequence, phase by phase.
