# ECCO Skills System Design

> ## 📌 Working Convention: This Document Is Living
>
> **This design doc is the single source of truth, and it must stay in sync with reality as we build.** Every change made during implementation — a decision, a discovered constraint, a version pin, a renamed skill, a workaround, an abandoned approach — must be reflected here *in the same step it happens*, not batched for later. If code and this doc disagree, that's a bug to fix.
>
> Concretely, whoever (human or AI) makes a change:
> - Updates the relevant section (skill definitions, recipes, validation, environment, etc.).
> - Moves resolved items out of "Open Questions & Working Context" into "Decisions already made."
> - Records newly discovered constraints/gotchas where they belong (e.g. Critical Gotchas, Environment).
> - Never leaves the doc describing something that is no longer true.
>
> The goal: a newcomer (or a future session) can read this doc alone and understand the current, accurate state of the project — because the user is learning as we go and relies on this doc to see everything.

> ## 🔬 Science correctness: see `docs/verify.md`
>
> The user trusts the AI on science they don't independently check — and early AI *confidence was repeatedly wrong* (caught only by external evals). **`docs/verify.md` is the binding V&V protocol:** nothing is "correct" because the AI believes it; every science skill must carry independent evidence (official-helper match → tutorial reproduction → conservation → sanity → cross-check → teeth-verified tests → standing adversarial review) before it's "done." Verify as much as possible without Phil; escalate only genuine judgment calls. Report **evidence, not confidence** (✅ verified / ⚠️ unverified / 🔴 needs Phil). The **current per-skill scorecard is `docs/verify-status.md`**. This applies to all science work in this project.

## Motivation

This project originated from a UWG (User Working Group) discussion with Phil, who proposed the idea of encoding correct ECCO science methodology into AI-executable "skills." The user (jwood) brings the AI/engineering expertise; Phil brought the science use cases. The core problem: an AI agent asked to perform an ECCO calculation can produce plausible-but-wrong results if it doesn't know the specific sequence of grid operations, masking, and physical reasoning required. These skills serve as **guardrails** — they encode the correct approach so the AI doesn't have to reason about Arakawa C-grid staggering or LLC90 tile topology from first principles every time.

The skills guide AI to:
1. Load the correct fields for a given calculation
2. Apply operations in the right order on the staggered grid
3. Use proper masking and weighting
4. Produce physically meaningful, unit-correct output

---

## What Is a "Skill" Here (Architecture)

We are building **Agent Skills** in the sense used by Claude Code / the Claude Agent SDK — not a plain Python library. Each skill is a directory containing:

- **`SKILL.md`** — the *guidance*. Prose that tells the AI which fields to load, which grid positions matter, the correct sequence of operations, the masking/weighting rules, unit expectations, and the known failure modes. This is the guardrail. It is what gets injected into context when the skill is invoked.
- **Vetted helper code** (`scripts/*.py`) — small, tested functions the skill's instructions point the AI to call rather than re-derive. This is what makes outputs *reproducible* instead of freshly-hallucinated each run.
- **`references/`** (optional) — worked examples, expected-output values, closure-test snippets, and the skill's **acceptance evidence**. Kept *inside the skill folder* (not in `docs/`) so a skill is self-contained: copy/share the folder and its "why we trust this" record travels with it.

**Anatomy of a built skill** (the calc-skill template, as realized by `compute-ocean-heat-content`):

```
.claude/skills/<skill-name>/
├── SKILL.md                    # guidance the agent reads (what/when/why)
├── scripts/
│   ├── run.py                  # the calculation (imports ecco_common helpers)
│   └── test_validation.py      # negative + positive tests that the guards fire
└── references/
    └── acceptance.md           # build-time acceptance evidence (why we trust it)
```

`docs/` holds project-wide docs (this design, the roadmap); each skill's `references/`
holds that skill's own evidence. Shared logic lives in the `ecco-common` package (see
"How skills compose"), so `run.py` stays thin.

The distinction matters for the proposal: a bare library makes the AI a *caller* (and it can still call it wrongly); a Skill makes the AI a *guided author* that assembles the correct calculation and can fall back to the vetted helper. The two compose — `SKILL.md` explains the "why and when," the helper guarantees the "how."

Skills are usable directly in **Claude Code** (and any Agent-SDK harness): a user asks "compute the Atlantic 26°N heat transport from ECCO," the relevant skills load, and the agent follows the encoded methodology instead of improvising C-grid math.

### How skills compose — shared `ecco_common` library (Option A, decided & built 2026-07-23)

Skills do **not** pass live Python objects to each other (a skill isn't a running process that hands a variable to another). The composition mechanism is a **shared Python package, `ecco_common`**, that skills import:

- `.claude/skills/ecco-common/ecco_common/` holds the reused building blocks — `load_grid()`, `load_field()`, plus `access` (CMR query + `.netrc` download), `cache` (project-local `./data/ecco` cache), `plots` (headless LLC plotting), and `grid_ops` (Level-1 primitives `coriolis`/`canon`/`grad_to_center`, extracted 2026-08-05). Written **once**, imported everywhere.
- A calculation skill's script imports these helpers and runs the whole calculation in **one venv-python process**: `ds_grid, grid = load_grid(); ds = load_field(...); result = compute(...)`. The in-memory xarray objects are ordinary local variables passed between function calls — no cross-process object transfer.
- The **durable** thing shared between separate runs is the `.nc` cache on disk (so downloads aren't repeated); the **in-memory** objects only "flow" within a single script via imported functions.
- Skills put `ecco_common` on `sys.path` with a one-line bootstrap (`sys.path.insert(0, ".../ecco-common")`) — no install step, works across sibling skill dirs.

This is why each skill is *both* a `SKILL.md` (guidance the agent follows) *and* thin `scripts/` that call shared helpers: the guidance explains the science; the shared library guarantees the mechanics are identical everywhere.

Contrast with the **environment** skills (`ecco-setup` → `ecco-setup-verify`), which are deliberately **subprocess**-style (setup launches verify as a separate process) — correct there because they cross an interpreter boundary (system python vs venv python). Calculation skills all run in the one venv python, so shared imports are the cleaner fit.

---

## What is ECCO?

ECCO (Estimating the Circulation and Climate of the Ocean) Version 4 Release 4 is a global ocean state estimate covering January 1992 through December 2017 at ~1-degree horizontal resolution (13 tiles of 90x90 cells) with 50 vertical levels. Unlike conventional ocean reanalyses that nudge model state toward observations, ECCO identifies optimal initial conditions, boundary conditions, and parameters so a free-running simulation reproduces observations. This means ECCO **exactly conserves** heat, salt, volume, and momentum — making it ideal for budget and flux calculations.

## User Questions This System Must Answer

The design is organized around *skills* and *recipes* (how we build things), but the user arrives with a **question**. This is the entry point: the list below is the set of questions — drawn directly from the UWG discussion with Phil and from the tutorial learning objectives — that the system must answer correctly and *demonstrably* correctly. Every question maps to the skills/recipe that answers it and to the validation layers that let the user trust the result. If a question here has no trustworthy path to an answer, that is a gap to close.

> **⚠️ This table is a specification, not a status report.** It lists the questions the system *must* answer; it does **not** claim they are all built. **As of 2026-07-25 only Q1 (ocean heat content) is implemented and validated.** Everything else is designed but unbuilt. Do not read the "Answered by" column as "already works" — see Next Steps for actual build status.

### Quantitative calculation questions (from Phil's use cases)

| # | User question (plain language) | Answered by | Trust via (validation layers) |
|---|-------------------------------|-------------|-------------------------------|
| Q1 | "How much has global ocean heat content changed over this period?" | Recipe 1 (`compute-ocean-heat-content`) | Units (L2), physical bounds (L3), OHC-trend benchmark (L6) |
| Q2 | "What is the volume / heat / salt flux across a line between these two (possibly coastal) points in the Atlantic?" | Recipe 4 (`make-section-mask` → `compute-transport-across-section`) | Two-method cross-check (L5), MOC/RAPID benchmark (L6), units (L2) |
| Q3 | "What is the volume / heat / salt budget for this arbitrary volume?" | `compute-tracer-budget` (which terms to sum) | **Conservation closure to ~1e-10 (L4)** — the strongest oracle |
| Q4 | "Decompose a flux into mean-flow and eddy parts (Reynolds decomposition of v·T)" | Recipe 5 (`decompose-flux`) | Sum-of-parts must equal the total flux (L5, exact algebraic check) |
| Q5 | "Does the curl of the wind stress line up with vertical velocity — can I see Ekman pumping?" | Recipe 6 (`compute-curl` + Ekman pumping) | Sign/pattern agreement, normalized difference (L5), physical bounds (L3) |
| Q6 | "How does Ekman transport compare with the model's upper-ocean velocity?" | `compute-ekman-transport` | Cross-comparison with model velocity (L5), units incl. 1/ρ (L2) |

### Method / demonstration questions (from the tutorial objectives)

| # | User question | Answered by | Trust via |
|---|--------------|-------------|-----------|
| Q7 | "Plot an ECCO field on a single tile." | plotting skill (single-tile) | Input/metadata checks (L1) — right field, right units on the colorbar |
| Q8 | "Do spatial differencing / interpolation on the native model grid — correctly." | `spatial-difference`, `spatial-interpolation` | Grid-position check (L1), the guardrail is the point |
| Q9 | "Compare the two sides of the geostrophic balance equations — do they match?" | Recipe 2 | Normalized residual small away from equator/surface (L5) |
| Q10 | "Compute geostrophic velocities." | `compute-geostrophic-velocity` | Cross-check vs model velocity (L5), units (L2) |
| Q11 | "Apply masks in a 2-D spatial plot." | `apply-mask` (+ plotting) | Visual + NaN/land audit (L3) |
| Q12 | "Plot a global map of an ECCO field (all 13 tiles stitched)." | global-map plotting skill (`ecco_v4_py`) | Input/metadata checks (L1) |

**How to read this table:** the middle column is the "can we even do it" check (every row must resolve to a real skill/recipe — no gaps), and the right column is the "can the user trust it" check (every row must name at least one concrete validation layer). Keeping the questions front-and-center guards against building elegant skills that don't actually answer what a user asks, and against returning answers the user has no way to trust.

---

## Source Tutorials

The skills are extracted from the ECCO v4 Python tutorials:
https://ecco-v4-python-tutorial.readthedocs.io

These "Intro to PO" tutorials assume the **Getting Started** tutorials (what ECCOv4 is, how output is structured, tools, and how to download files) as prerequisites — the skills should either encode or link that setup. *(The current Intro-to-PO section has four calculation notebooks: Geostrophic Balance, Thermal Wind, Steric Height 3a, and Steric Height 3b — earlier drafts of this doc said "three.")*

Specifically the "Intro to PO Tutorials" section which covers:
- **Geostrophic Dynamics:** Geostrophic balance, Thermal wind, Steric height
- **Ageostrophic Dynamics:** Ekman dynamics, Equatorial waves
- **Vorticity/Quasi-Geostrophy:** Sverdrup balance, Rossby waves, Vorticity budget
- **Property Budgets:** Potential density/water masses, Potential temperature, Salinity/salt/freshwater, Sea ice
- **Climate Topics:** MOC and transports, Earth energy imbalance, Sea level rise, Hydrological cycle

---

## The Grid: LLC90 Arakawa C-Grid

Understanding the grid is prerequisite to everything else. ECCO uses the Lat-Lon-Cap 90 (LLC90) grid:

- **13 tiles**, each 90x90 horizontal cells
- Tiles 0-5 are "normal" (j increases with latitude)
- Tiles 7-12 are **rotated 90 degrees counterclockwise** (j increases with longitude)
- Tile 6 is the Arctic cap
- **50 vertical levels** with non-uniform spacing (10m near surface, hundreds of meters at depth)

### Staggered Variables (Arakawa C-Grid)

Variables live at different positions on each grid cell:

| Position | Dimensions | Examples |
|----------|-----------|----------|
| Cell center (tracer point) | `(tile, j, i)` | THETA, SALT, RHOAnoma, PHIHYDcR, SSH |
| West face (U-point) | `(tile, j, i_g)` | UVEL |
| South face (V-point) | `(tile, j_g, i)` | VVEL |
| Cell interface (vertical) | `(k_l)` or `(k_u)` or `(k_p1)` | WVEL |

This staggering means **you cannot directly compare or combine** fields at different positions without interpolation or differencing. The `xgcm` library handles this.

### Key Grid Variables

From the geometry dataset (`ECCO_L4_GEOMETRY_LLC0090GRID_V4R4`):

| Variable | Meaning |
|----------|---------|
| `XC, YC` | Longitude/latitude of cell centers |
| `XG, YG` | Longitude/latitude of cell corners |
| `dxC, dyC` | Distance between adjacent cell centers (at cell faces) |
| `dxG, dyG` | Distance between adjacent cell corners (at cell edges) |
| `rA` | Cell face area |
| `drF` | Distance between adjacent cell interfaces (cell thickness) |
| `drC` | Distance between adjacent cell centers (vertical) |
| `hFacC, hFacW, hFacS` | Fraction of cell open to fluid (partial cells near topography) |
| `maskC, maskW, maskS` | Boolean ocean mask at center/west-face/south-face |
| `Depth` | Seafloor depth |
| `CS, SN` | Cosine/sine of grid orientation angle (for rotating to geographic axes) |
| `Z, Zu, Zl, Zp1` | Vertical coordinate arrays (center, upper face, lower face, interfaces) |

### Cell Volume

Cell volume is computed as:
```
vol = rA * drF * hFacC
```
Where `hFacC` accounts for partial cells near topography.

---

## Key Python Packages

| Package | Role |
|---------|------|
| `ecco_v4_py` | ECCO-specific utilities: plotting on LLC grid, grid object creation |
| `ecco_access` | Data download/access from PO.DAAC (local or S3) |
| `xarray` | Core data structure (labeled N-dimensional arrays) |
| `xgcm` | Grid-aware differencing and interpolation on staggered grids |
| `numpy` | Numerical computation |
| `matplotlib` | Plotting |

---

## Environment & Setup (the step before everything)

**The problem:** these skills run Python code, but we cannot assume the user has Python, the libraries, or any dev experience. Users range from "software engineer who knows Python" (like the project lead) to "no dev skills and no science background." The skill system must **set up a clean, isolated environment and verify it works before running any calculation** — and narrate what it's doing so a non-developer learns rather than just watches.

### Design decisions

1. **Never touch the global/system Python.** All packages install into a **project-local virtual environment** (`.venv/` in the project dir). This avoids cluttering or breaking the user's system Python, needs no admin rights, and is trivially deletable (just remove the folder). This is non-negotiable for a tool aimed at non-developers — a botched global install is exactly the kind of mess we must not create.

2. **`venv` + `pip` only — no conda.** We use Python's built-in `venv` and install from PyPI wheels. No conda, no mamba, no separate package manager to install first. This is a deliberate choice: `venv` ships with Python itself, so there's one less thing for a new user to obtain, and the environment is a plain folder the user fully understands and can delete.

3. **A dedicated `ecco-setup` skill runs first.** It is a prerequisite of every calculation skill. Its job: check Python → create the venv → `pip install` pinned dependencies → verify the install → report a clear ✓/✗ to the user. Calculation skills check for a ready environment and, if absent, hand off to `ecco-setup` rather than failing cryptically.

4. **Setup and verify are two distinct phases, but one flow.** "Installed" ≠ "works." `ecco-setup` installs, then **automatically hands off to `ecco-setup-verify`** at the end (both fresh-build and reuse paths) — so a setup run always finishes verified, and setup's exit code reflects the verification result. `ecco-setup-verify` remains a **separate skill** you can run standalone to re-check an environment later (or as first-line diagnostic when a calc skill errors) without reinstalling. This keeps **one source of verification truth**: setup never re-implements the checks, it calls the verify script. *(Decided 2026-07-23; the alternative — merging into one skill — was rejected to preserve the standalone re-check.)*

### The compiled-dependency concern — resolved by wheels (verified)

`ecco_v4_py` pulls in `cartopy`, `pyresample`, and `netCDF4`, which have **compiled C dependencies** (GEOS, PROJ, HDF5). Historically this is why people reached for conda. **That is no longer necessary:** as of this writing all three ship **prebuilt binary wheels on PyPI** for macOS (Intel + Apple Silicon), Linux (manylinux), and Windows — the wheels bundle their C libraries (e.g. cartopy 0.25 embeds GEOS/PROJ). So a plain `pip install` into a venv **needs no system compilers, GEOS, or PROJ** on a normal machine.

*Verified by an actual build (2026-07-23, macOS/arm64, Python 3.12.13):* a plain `pip install` into a fresh venv pulled **everything as PyPI wheels — zero source builds, no compilers** — including cartopy 0.25.0, netCDF4 1.7.4, pyresample 1.35.0, pyproj 3.7.2, shapely 2.1.2. The "must use conda" assumption is confirmed obsolete for this stack. See `.claude/skills/ecco-setup/`.

The setup skill still **detects and clearly reports** if any package falls back to a source build (rare — e.g. an unusual platform or a Python version too new for published wheels) so the user gets a plain-language explanation instead of a compiler-error wall.

### Python version — supported band **3.11–3.12**, and why the system `python3` usually won't do

- **Floor: 3.11**, set by **`ecco_access` (v0.3.1 requires Python ≥3.11)** — this is the binding constraint (xgcm alone would allow 3.9, but ecco_access raises it). *Discovered during the first real build; earlier drafts said 3.10.*
- **Upper bound: 3.12 — this is our *tested policy*, not a wheel-availability limit.** `ecco_access` supports 3.13 and Cartopy 0.25 does publish 3.13 wheels, so 3.13 could well work; we simply haven't verified the *whole* stack (esp. the `xgcm<0.10` pin + `ecco_v4_py`) on it. We cap at the newest version we've actually tested and will raise it after verifying. Independently, **the system `python3` is often too *new*** (e.g. Homebrew's is 3.14) — and a brand-new Python may genuinely lack some wheels — so "too new" remains a real trap regardless.
- **The user will likely need a specific Python installed as a prerequisite.** That's expected and fine. On most systems they'll have version-suffixed commands available side by side: `python3.12`, `python3.11`. (Homebrew on macOS installs these as `python3.12` etc.; `pyenv`, the python.org installers, the Windows `py` launcher, and Linux distro packages all expose the same idea.)

### Interpreter discovery — newest-in-band wins, then fall back

### Preliminary check — survey the Python landscape *first* (read-only)

Before creating or installing anything, `ecco-setup` runs a **read-only diagnostic** that inventories what Python the machine actually has, then reports a plain-language summary and verdict. Nothing is installed, modified, or written in this phase — it only *looks*. This turns "cryptic failure halfway through an install" into "here's your situation and the one thing to do next."

What it inspects (all non-destructive):

- **Which `python3` is the default, and its real path.** `which python3` + resolve symlinks (e.g. reveals `/opt/homebrew/bin/python3 → python@3.14`). Establishes whether the default is Homebrew, pyenv, Apple, python.org, etc.
- **Its version** — and whether that's in band (3.11–3.12), too new (3.13+), or too old (≤3.10). *The common case is "too new," not "too old"* (e.g. a Homebrew `python3` is now 3.14).
- **All version-suffixed interpreters on PATH:** `python3.11`, `python3.12` (Windows: `py -0` to list). This is what determines whether a supported interpreter already exists.
- **macOS specifics:** note Apple's `/usr/bin/python3` (a stub that may trigger a Command Line Tools prompt; the CLT Python is 3.9 — below our floor) so the user isn't misled into thinking it's usable. Note that Python 2 `/usr/bin/python` is gone on modern macOS.
- **PATH ordering sanity** — informational only (e.g. Homebrew-before-system is normal and fine); not something the skill changes.
- **venv availability** (`python -m venv` importable) and **pip presence**.
- **Existing `.venv/`** for this project — is there already a built environment to reuse?

Then it prints a verdict, for example:
```
Python check:
  default `python3`      → 3.14.4  (Homebrew)   ⚠ too new for the science libraries
  python3.12             → not found
  python3.11             → not found
  Apple /usr/bin/python3 → 3.9 stub             ✗ below supported floor
  Verdict: no supported Python (3.11–3.12) found.
  → Do this:  brew install python@3.12
     then re-run setup. (macOS/Homebrew; other platforms below.)
```
or, on a ready machine:
```
  python3.12             → 3.12.5  ✓
  Verdict: python3.12 is supported. Proceeding to build the sandbox.
```

Only after this survey does the skill move to interpreter discovery (below), which reuses what the survey already found. **The survey is also runnable on its own** (a "what's my Python situation?" command) — useful for a user like the one asking "how do I find my default Python?" without committing to a full setup.

### Interpreter discovery — newest-in-band wins, then fall back

Using the survey results, the setup skill does **not** just use `python3`. It selects the best in-band interpreter, **newest first, capped at 3.12**:

```
Try, in order:  python3.12 → python3.11
  (Windows also: py -3.12 → py -3.11)
Use the first one that exists. That becomes THE interpreter for this project's venv.
If none exist:
  → check the bare `python3` — if it happens to be 3.11-3.12, use it;
    if it's out of band (e.g. ≤3.10, or 3.13+), STOP and guide the user to install
    a supported Python (brew install python@3.12 / pyenv / python.org / distro pkg),
    then re-run setup.
```

Prefer the newest in-band (3.12 over 3.11) so users get the most current supported runtime, while the 3.12 cap keeps them on a version the wheels actually cover.

### The venv is a persistent sandbox — build once, then reuse

Once `ecco-setup` creates `.venv/` with a chosen interpreter, **that venv is the environment for all subsequent skill runs.** Skills invoke `.venv`'s Python directly (no reliance on the user manually "activating" it each time — a step non-developers forget). The setup skill:
- **Detects an existing, healthy `.venv/`** and reuses it instead of rebuilding (fast path: setup becomes a no-op that just confirms readiness).
- **Records what it built** — the chosen interpreter path and resolved Python version — so later runs and `ecco-setup-verify` can confirm the same env.
- Only rebuilds when the env is missing or fails verification.

**Reset is a deliberate, separate action (implemented).** Because the venv persists, `ecco-setup --reset` deletes `.venv/` and rebuilds from scratch — for when deps get corrupted, the user wants a newer Python, or requirements change. Built and tested (a `--reset` rebuild re-resolves the `xgcm<0.10` pin to 0.9.0 and finishes verified).

### `ecco-setup` skill — flow

```
0. SURVEY    Read-only Python-landscape check (see Preliminary check). Reports the
             machine's pythons + a verdict. Modifies nothing. Can be run standalone.
1. REUSE?    Does a healthy .venv/ already exist (and not --reset)?
             → yes: skip build, go straight to VERIFY handoff (step 7).
2. DISCOVER  From the survey: pick python3.12 → 3.11 (Windows: py -3.12 …);
             else bare python3 if in band.
3. GATE      Found an in-band interpreter (3.11-3.12)?
             If not → STOP, print the exact install command for the user's OS, don't proceed.
4. ISOLATE   <chosen-python> -m venv .venv   (then upgrade pip inside .venv)
5. INSTALL   .venv's pip install pinned deps from requirements.txt
             (ecco_v4_py, xgcm<0.10, xmitgcm, ecco_access, xarray, numpy,
              matplotlib, netCDF4, cartopy, pyresample, dask, …)
6. RECORD    Save chosen interpreter path + version (ecco_env.json) so later runs
             reuse this venv and verify can confirm the same interpreter.
7. VERIFY    Hand off to ecco-setup-verify (imports + grid smoke test). Installed ≠
             working. Setup's exit code = verify's result. (One source of truth.)
8. REPORT    Clear ✓/✗ + plain-language verdict; on verify failure, say it's not ready.
```

Cross-platform note: venv layout differs (`.venv/bin/` on macOS/Linux, `.venv/Scripts/` on Windows). Skills should locate the venv Python programmatically rather than hardcoding the path, so the same skill works on all three OSes.

### Interpreter policy — which Python runs what (explicit)

A simple, strict rule so it's never ambiguous:

- **System `python3` is used ONLY before the venv exists** — to run `survey.py` (read-only inspection) and to *create* the venv (`<python3.x> -m venv .venv`). Nothing that imports an ECCO library ever runs under system `python3`.
- **`.venv/bin/python` (or `.venv/Scripts/python.exe`) is used for EVERYTHING afterward** — `pip install`, the verify handoff, `ecco-setup-verify`'s actual checks, and every calculation/plotting/data skill.

Implementation detail: when `ecco-setup` hands off to verify, it launches `verify_env.py` **with the venv python** and sets `ECCO_VERIFY_INNER=1` so verify skips its self-re-exec. When `ecco-setup-verify` is run *standalone* with a system `python3`, its launcher bootstraps and immediately re-execs itself with the venv python — so the checks still run in the venv. Either way, all library work happens under one reproducible interpreter. *(Made explicit 2026-07-23 after noticing the handoff was hopping through system `python3`.)*

### `ecco-setup-verify` — proving the *environment* actually works

**Scope: the environment/toolchain only.** This skill verifies that the `.venv` built by `ecco-setup` is healthy — it does **not** verify any oceanographic calculation or result (that is what each calculation skill's own runtime validation does; see the Validation section). The name is deliberately `ecco-setup-verify`, not `ecco-verify`, so a user is never confused into thinking it checks their science. Pair it with `ecco-setup`; it's re-runnable anytime a user wants to sanity-check the environment.

It is itself a worked example of **Validation Layer 1** applied to the toolchain:

- **Python version** is in the supported band (3.11–3.12) **and** matches the interpreter `ecco-setup` recorded for this venv.
- **Every required library imports** (catches the compiled-dep failures that "install succeeded" hides).
- **Report the resolved versions** of the key packages (reproducibility; also lets us catch a too-new/too-old combo).
- **Tiny functional smoke test:** build an `xgcm` grid on a small synthetic array and run one `diff`/`interp` — proves the staggered-grid machinery actually executes, not just imports.
- **(Optional) data-access check:** confirm the user can reach/download one small ECCO granule (this also surfaces PO.DAAC/Earthdata credential setup as its own step — see Data Access).
- **Report:** "Python 3.11 ✓ · xgcm 0.10.1 imports ✓ · grid diff smoke test ✓ · …" — the same validation-trail style as every other skill.

**Not to be confused with** (see Validation section for the full picture):
- *Runtime validation* — the 6-layer checks each **calculation** skill runs on **its own answer**, every time it computes (units, closure, benchmarks, …).
- *Build-time acceptance testing* — how **we** confirm a calculation skill is correctly implemented before shipping it (e.g. reproduces the tutorial's published number).

### Teach as we go (Design Principle #8 applied to setup)

For a non-developer, setup *is* the scariest part. The `ecco-setup` / `ecco-setup-verify` skills should explain, in plain language, what a virtual environment is and why we use one ("a sandbox for this project's tools so we don't disturb the rest of your computer"), what each step is doing, and — on failure — what went wrong and the specific next action, never a raw stack trace with no guidance. A successful setup should leave the user understanding *what was built and how to remove it*, not just that a wall of text scrolled by.

### Open items to confirm at build time
- Exact pinned versions for a known-good environment (build and freeze a working `requirements.txt`; the closure/smoke tests are the acceptance gate).
- Whether `ecco_access` is on PyPI (pip-installable) or must be vendored/installed from source, e.g. `pip install git+https://...` (confirm at build; it may not be packaged the same way as the others).
- Upper bound on Python version given the geospatial stack's wheel availability at build time.
- Earthdata Login / PO.DAAC credentials: data download needs an Earthdata account and a `.netrc` (or equivalent). This is a separate setup step from the Python env — see Data Access.

---

### xgcm Operations

`xgcm` is central to almost every calculation. Key operations:

```python
xgcm_grid = ecco.get_llc_grid(ds_grid)

# Difference along X axis (tracer→U-point)
xgcm_grid.diff(field, axis="X", boundary='extend')

# Difference along Y axis (tracer→V-point)
xgcm_grid.diff(field, axis="Y", boundary='extend')

# Interpolate scalar from center to face
xgcm_grid.interp(field, axis="X", boundary='extend')

# Interpolate vector from faces to center (handles rotation on LLC grid)
xgcm_grid.interp_2d_vector({"X": u_field, "Y": v_field}, boundary='extend')
```

> **✅ RESOLVED — the snippets above (old `boundary=` API) are CORRECT for our pinned environment.** We pin **xgcm < 0.10** (0.9.0 verified), because:
> - xgcm 0.10 *removed* the `periodic=` argument, and **`ecco_v4_py` 1.8.1's own `get_llc_grid()` calls `xgcm.Grid(ds, periodic=False, ...)`** — so ECCO's packaged grid constructor **crashes under xgcm ≥ 0.10**. This is a library bug (ecco_v4_py declares only `xgcm>=0.5.0`, no upper bound).
> - With xgcm 0.9.0, `ecco.get_llc_grid()` works and the `boundary=`/`fill_value=` diff API above is exactly right — **tutorial code runs verbatim.**
> - Verified 2026-07-23 against the real geometry file: `get_llc_grid` succeeds and a diff correctly staggers `i → i_g` (tracer→U-point). The `ecco-setup-verify` skill now tests this exact call.
> - **Do not** relax the `xgcm<0.10` pin without re-testing `ecco.get_llc_grid()`.

---

## Data Access Pattern

> **Decision: skills query the NASA CMR REST API *directly* (HTTPS) — they do NOT depend
> on any MCP server (2026-08-04).** There is an "earthdata" MCP server (formerly named
> "CMR") that exposes CMR collection/granule discovery as agent tools. It is a useful
> *build-time / interactive* discovery aid — e.g. confirming a new collection's concept-ID
> before hardcoding it — but the skills must not call it at runtime. Rationale:
> (1) **standalone execution** — calc skills run as plain `.venv` Python (Option A), incl.
> headless / CI / `run_all_tests.py` / a user with no agent session; an MCP tool is only
> reachable through an MCP client loop, which would break that. (2) **Reproducibility &
> verifiability** — the V&V protocol rests on pinned, inspectable behavior; an MCP server
> is an unversioned moving target (it was *renamed* CMR→earthdata under us — exactly the
> drift that would silently break a skill). The direct CMR REST contract is stable and is
> what the offline suite monkeypatches (`_http_json`). (3) **Layering** — both
> `ecco_common.access` and the earthdata MCP are *clients of CMR*; one client shouldn't
> depend on another. **Rule:** MCP for build-time discovery only; direct CMR API for
> everything the skills do. (All "CMR" references in this repo mean the NASA Common
> Metadata Repository API at `cmr.earthdata.nasa.gov`, never an MCP tool.)

> **Credentials prerequisite (NASA Earthdata Login).** Downloading ECCO from PO.DAAC requires a free **Earthdata Login** account and credentials stored locally (typically a `.netrc` file, or an Earthdata token). This is a *separate* setup step from the Python environment and is a common first-time stumbling block. The `ecco-setup` / `ecco-setup-verify` skills should: check for working credentials, walk a new user through creating an Earthdata account and the `.netrc` if missing, and confirm access with a single small test download **before** any real calculation attempts to pull data. Treat "no credentials" as a clear, guided stop — not a cryptic download error.

The tutorials use `ecco_access` for downloads:

```python
import ecco_access as ea

ds = ea.ecco_podaac_to_xrdataset(
    "ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4",
    StartDate="2000-01", EndDate="2000-01",
    mode='download_ifspace',
    download_root_dir='~/Documents/Projects/PO.DAAC/data/ECCO_V4r4_PODAAC'
)
```

> **⚠️ `ecco_access` 0.3.1 download is unreliable — verified 2026-07-23.** Requesting the geometry collection via `ecco_podaac_to_xrdataset(...)` estimated **75.8 GB / 9497 files** (for what is a single 8.18 MB time-invariant file) and then **404'd**, having built a wrong filename (`GRID_1992-01-01_…nc`) instead of the actual granule `GRID_GEOMETRY_ECCO_V4r4_native_llc0090.nc`. Auth was fine (the failure was a data-egress 404, not 401/403). **Robust fallback that worked:** query CMR for the granule's real `access_urls`, then download that one file directly (curl/requests with `.netrc` Earthdata auth). The `load-field`/`load-grid` skills should prefer the CMR-URL path and treat `ecco_access` auto-resolution as unproven until we pin down when it works. *(Open item: is this a bug in 0.3.1, a mode issue, or a granule-naming edge case for time-invariant collections? Investigate at build time.)*

Key datasets (all verified in NASA CMR, 1992-01 → 2017-12, PO.DAAC/POCLOUD provider). Concept IDs are the stable handle for programmatic access:

| ShortName | CMR concept_id | Contents |
|-----------|----------------|----------|
| `ECCO_L4_GEOMETRY_LLC0090GRID_V4R4` | `C2013557893-POCLOUD` | Grid geometry (no time dimension) |
| `ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4` | `C1991543732-POCLOUD` | UVEL, VVEL, WVEL |
| `ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4` | `C1991543735-POCLOUD` | RHOAnoma, DRHODR, PHIHYD, PHIHYDcR |
| `ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4` | `C1991543728-POCLOUD` | THETA, SALT |
| `ECCO_L4_SSH_LLC0090GRID_MONTHLY_V4R4` | `C1991543813-POCLOUD` | SSH, ETAN, SSHIBC, SSHNOIBC |

Flux/stress collections required by the transport, budget, and Ekman skills (also CMR-verified):

| ShortName | CMR concept_id | Key variables |
|-----------|----------------|---------------|
| `ECCO_L4_OCEAN_3D_VOLUME_FLUX_LLC0090GRID_MONTHLY_V4R4` | `C1991543739-POCLOUD` | UVELMASS, VVELMASS, WVELMASS (Eulerian, mass-weighted) |
| `ECCO_L4_BOLUS_LLC0090GRID_MONTHLY_V4R4` | `C1991543745-POCLOUD` | UVELSTAR, VVELSTAR, WVELSTAR (GM bolus velocity) |
| `ECCO_L4_OCEAN_3D_TEMPERATURE_FLUX_LLC0090GRID_MONTHLY_V4R4` | `C1991543740-POCLOUD` | ADVx_TH, ADVy_TH, ADVr_TH, DFxE_TH, DFyE_TH, DFrE_TH, DFrI_TH |
| `ECCO_L4_OCEAN_3D_SALINITY_FLUX_LLC0090GRID_MONTHLY_V4R4` | `C1991543752-POCLOUD` | ADVx_SLT, ADVy_SLT, …, DFxE_SLT, … |
| `ECCO_L4_STRESS_LLC0090GRID_MONTHLY_V4R4` | `C1991543760-POCLOUD` | oceTAUX, oceTAUY (total ocean stress); EXFtaux, EXFtauy (bulk wind stress) |

Daily variants exist (replace `MONTHLY` with `DAILY` in the ShortName). Verified daily concept IDs now in `CONCEPT_IDS`: OCEAN_VEL `C1991543808`, DENS_STRAT_PRESS `C1991543727`, TEMP_SALINITY `C1991543736`, SSH `C1991543744` (all POCLOUD). **The loader is no longer limited to hardcoded IDs** — `access.concept_id_for()` resolves any valid ECCO ShortName live via CMR (collections endpoint) on a miss, so daily/other collections work without editing the map.

### Two CMR-verified refinements to the flux/Ekman skills

1. **The 3D flux diagnostics already ARE the transport.** `ADVx_TH`/`DFxE_TH` etc. have units of `degree_C m3 s-1` — they are the full flux through a cell face (velocity × face-area × tracer, **bolus included**). A section heat transport combines the X-face and Y-face components with their respective masks — `sum((ADVx_TH+DFxE_TH)·maskW) + sum((ADVy_TH+DFyE_TH)·maskS)` — then × ρ × Cp to Watts. **Do not** additionally multiply by a face area (that's only for raw `UVEL`/`VVEL`), and **don't** use a single mask — an arbitrary LLC section crosses both face directions (see `compute-transport-across-section`). This is the preferred (and budget-closing) path.

2. **Use `oceTAUX`/`oceTAUY` for Ekman, not `EXFtaux`/`EXFtauy`.** `oceTAUX` is the *total* stress felt by the ocean surface (includes sea-ice–ocean drag) — that is what drives the Ekman response. `EXFtaux` is the bulk-formula atmospheric wind stress and ignores the sea-ice modification. Under sea ice they differ substantially.

---

## Data Storage Strategy — cache on demand

### How big is the data? (verified via CMR, 2026-07-23)

ECCO v4r4 monthly collections each have **312 granules** (26 years × 12 months, 1992–2017). Per-file sizes on the native LLC90 grid:

| Collection | MB / month | Full 26-yr archive |
|---|---|---|
| Geometry (one-time, no time dim) | 8 MB | 8 MB |
| Temp/Salinity | ~16.6 | ~5.2 GB |
| Ocean Velocity | ~29.2 | ~9.1 GB |
| Density/Strat/Pressure | ~29.6 | ~9.2 GB |
| SSH | small | ~1–2 GB |
| 3D Temperature Flux | ~61.3 | ~19 GB |
| 3D Salinity Flux | ~61 (est) | ~19 GB |
| 3D Volume Flux | ~61 (est) | ~19 GB |
| Bolus velocity | ~29 (est) | ~9 GB |
| Stress | small | ~1–2 GB |

**The scale, three ways:**
- One month of one field: **16–60 MB** (trivial).
- One month of *everything* (~10 collections): **~350 MB** (fine).
- **Full archive of everything: ~90–100 GB** (matches the 75.8 GB `ecco_access` estimate seen earlier).

The tutorials only ever use **one or two months** (Jan 2000) — a few hundred MB total. Individual analyses are tiny; only "download it all" is large.

### Decision: cache on demand, project-local

We do **not** bulk-download the archive, and we do **not** treat downloads as throwaway temp files. Instead:

1. **Cache, don't temp.** Downloaded granules are kept and reused across runs (re-downloading a 30 MB file every time is wasteful and breaks offline re-analysis).
2. **Download only what a calculation needs, when it needs it.** A skill asks for "temp/salinity, Jan 2000" → check cache → download just that granule if missing.
3. **Project-local cache dir:** `./data/ecco/<ShortName>/<granule>.nc`. Lives next to the project (like `.venv`), easy to find, easy to delete to reclaim space.

### Rules for the cache (enforced by the load skills)

- **`.gitignore` the data dir** — never commit `.nc` files (some are 60 MB). The project `.gitignore` lists `/data/`, `/.venv/`, and `/plots/` (plus `__pycache__/`, `*.pyc`). *Caveat:* the leading-slash `/data/` pattern only matches the cache at the project root — the default. If `ECCO_DATA_DIR` is overridden to point elsewhere inside the repo, that path isn't covered by this rule. *(The project is now a git repo — public at https://github.com/podaac/ecco-skills — so these ignore rules are live; verified `data/`, `.venv/`, and `plots/` are untracked.)*
- **Size-aware guard before downloading.** Estimate the download size first; if it's large (>~1 GB), **tell the user and ask** rather than silently pulling tens of GB. Implemented: `ecco_common.access.check_download_size` / `SIZE_WARN_MB = 1024`. **Two subtleties fixed after eval #3 (2026-07-25):** (a) granule size is read from the archive entry whose `Name` exactly matches the `.nc` file (preferring `SizeInBytes`) — a CMR record also lists a tiny `.sha512` sidecar, and taking the "first MB entry" could grab that (~200 bytes) and defeat the guard; (b) the guard is applied **once over the whole request** (all requested months/days), not per-file — otherwise a 100-day request slips through 29 MB at a time. A granule reporting *no* size also trips the guard (a missing size can't hide a big download). Verified: a 40-day (~1.2 GB) request is correctly blocked.
- **Cache-hit reporting (teach-as-you-go):** say "using cached file X" vs "downloading X (30 MB)…" so the user sees what's happening.
- **Configurable location, project-local default.** Default to `./data/ecco/`; override with the **`ECCO_DATA_DIR`** env var so a user who wants one shared cache across projects can point at, say, `~/ecco_data`. ECCO data is not project-specific, so a shared cache is a legitimate preference.

### Note on existing paths

Earlier testing downloaded the geometry file to `~/Downloads/ECCO_V4r4_PODAAC/` (the tutorials' default). We standardize on **project-local `./data/ecco/`** going forward; the `~/Downloads` copy is incidental. The `load-grid`/`load-field` skills own this cache logic (and the download path — see the `ecco_access` reliability note in Data Access; prefer the CMR-URL direct download).

---

## Skill Hierarchy

Skills are ordered from foundational (used by everything) to specialized (specific calculations).

### Level 0: Infrastructure

#### `load-field`
Load an ECCO dataset by ShortName and month(s). Returns an xarray Dataset.

**Inputs:** ShortName, `months=['YYYY-MM', …]` (or advanced `start`/`end`)
**Output:** xarray Dataset with proper coordinates
**As built:** downloads from PO.DAAC via CMR to the project-local `./data/ecco` cache
(HTTPS + `.netrc` auth). Three time selectors: `months=['YYYY-MM']` (monthly, queries
mid-month), `days=['YYYY-MM-DD']` (daily, queries mid-day — daily granules overlap at
*midnight* just as monthly ones do at month edges; verified 2026-07-25), or raw
`start`/`end` (advanced). Exactly one selector; violations raise `ValueError` before any
I/O. *S3/in-cloud access is not implemented* — the tutorials' `s3_open_fsspec` mode is a
future option.

#### `load-grid`
Load the ECCO grid geometry. This is needed for virtually every calculation.

**Output:** xarray Dataset with all grid metrics

### Level 1: Grid Operations

> **Status (2026-08-05): these Level-1 mechanics are `ecco_common` library functions, NOT
> standalone skills** (same category as `load_grid`). Extraction pass done — see roadmap
> Phase 2 for the caller audit. **Extracted into `ecco_common/grid_ops.py`:**
> `spatial-difference`+`spatial-interpolation` (fused as `grad_to_center`, 2 callers),
> `compute-coriolis` (as `coriolis`, 3 callers), plus `canon` (dim-order helper, 3 callers).
> **NOT extracted (only 1 caller each — left inlined until a 2nd appears):**
> `rotate-to-geographic` (curl only; and its bit match to `ecco_v4_py.vector_calc.
> UEVNfromUXVY` makes adopting the official helper the likely move) and `vertical-difference`
> (thermal-wind only). The prose below describes the operations; the implementation lives in
> `grid_ops.py`.

#### `spatial-difference` *(✅ extracted as part of `grad_to_center`)*
Compute the spatial difference of a field along X or Y axis, properly accounting for the C-grid staggering.

**Core operation:**
```python
diff_x = xgcm_grid.diff(field, axis="X", boundary='extend') / ds_grid.dxC
diff_y = xgcm_grid.diff(field, axis="Y", boundary='extend') / ds_grid.dyC
```

**Note:** The result is at a different grid position than the input (center→face or face→center).

#### `spatial-interpolation`
Interpolate a field from one grid position to another (e.g., face to center, center to face).

Scalar interpolation:
```python
xgcm_grid.interp(field, axis="X", boundary='extend')
```

Vector interpolation (handles vector *connectivity across tile edges*):
```python
xgcm_grid.interp_2d_vector({"X": u, "Y": v}, boundary='extend')
```

**Note:** `interp_2d_vector` handles the tile-edge topology (where one tile's U-face joins the next tile's V-face), *not* rotation into geographic axes. Rotation to zonal/meridional is the separate CS/SN step in `rotate-to-geographic`. You typically need both, in that order.

#### `vertical-difference`
Compute vertical derivatives. Must account for:
- k indices decrease upward (negate the difference)
- Use `drC` (distance between cell centers) for derivatives of center quantities
- Use `drF` (cell thickness) for derivatives of face quantities

```python
du_dz = -(field.diff("k")) / drC[1:-1]
```

#### `rotate-to-geographic`
Rotate vector fields from model-native axes to geographic (zonal/meridional) axes using the grid's CS (cosine) and SN (sine) arrays:

```python
u_zonal = CS * u_model - SN * v_model
v_merid = SN * u_model + CS * v_model
```

**Critical for tiles 7-12** where model axes are rotated 90 degrees from geographic.

### Level 2: Weighting and Masking

#### `volume-weight`
Multiply a 3D field by cell volumes:
```python
weighted = field * rA * drF * hFacC
```

#### `area-weight`
Multiply a 2D field by cell areas:
```python
weighted = field * rA
```

#### `apply-mask`
Apply land/ocean masks or custom spatial masks to a field. Masks come from:
- `maskC` (center points), `maskW` (west faces), `maskS` (south faces)
- Custom masks (e.g., a section mask between two points)
- Threshold masks (e.g., mask out velocities < 0.5 cm/s)

#### `global-sum`
Sum a field over all tiles and horizontal dimensions (and optionally vertical):
```python
total = (field * mask).sum(["tile", "j", "i"])       # horizontal sum at each depth
total = (field * mask).sum(["tile", "j", "i", "k"])  # full 3D sum
```

#### `global-mean`
Area- or volume-weighted global mean:
```python
mean = (field * rA * maskC).sum(["tile","j","i"]) / (rA * maskC).sum(["tile","j","i"])
```

### Level 3: Transect and Section Operations

#### `find-indices-along-latitude`
Given a target latitude and longitude bounds, find all grid cell indices that fall along that line. Handles multi-tile transects.

Uses `YC_bnds` to identify cells that straddle the target latitude, filters by longitude bounds, sorts by longitude.

**Output:** Dictionary of `{tile, j, i}` arrays plus `XC_along_lat`, `XG_along_lat` coordinate arrays.

#### `extract-transect-data`
Given the indices from `find-indices-along-latitude`, extract a data field along that transect, producing a 2D array (depth x longitude).

#### `make-section-mask`
Define a 1/0 mask along an arbitrary line between two points (e.g., for computing transport across a section). ECCO has routines for this.

### Level 4: Physical Calculations

#### `compute-coriolis` *(✅ extracted as `ecco_common.grid_ops.coriolis`, 2026-08-05)*
Compute the Coriolis parameter from latitude:
```python
Omega = 2 * np.pi / 86164  # Earth's rotation rate (sidereal day)
f = 2 * Omega * np.sin(np.radians(lat))
```

#### `compute-geostrophic-velocity`
From geostrophic balance `f·v = (1/ρ)·∂p/∂x`. Note `PHIHYDcR = p/rhoConst − gz`, so
`∂p/∂x = rhoConst · ∂(PHIHYDcR)/∂x`. The pressure term must therefore be scaled by
`rhoConst` and divided by the **actual** density `ρ = rhoConst + RHOAnoma` — **not** left
as a bare `1/f · ∂(PHIHYDcR)/∂x`. Dropping the `rhoConst/ρ` factor is a spatially-varying
error of a few percent.

```python
rhoConst = 1029.
rho      = rhoConst + RHOAnoma            # actual in-situ density (needs RHOAnoma)
dp_dx    = rhoConst * d(PHIHYDcR)/dx       # = ∂p/∂x
dp_dy    = rhoConst * d(PHIHYDcR)/dy
v_g =  dp_dx / (rho * f)
u_g = -dp_dy / (rho * f)
```

**Inputs include `RHOAnoma`** (for `ρ`) in addition to `PHIHYDcR`. Interpolate the
gradients to tracer points; keep both sides in model coordinates for like-for-like
comparison; rotate to geographic only for output. Verified against the tutorial's
formula (`v_g = (1/(ρf))·∂p/∂x`). **Cross-check note:** `geos_vel_compute` is **not** in
the installed `ecco_v4_py` 1.8.1 — it lives in the separate `ecco_po_tutorials.py`
helper (downloaded within the tutorials). Cross-check against that if available, or
against the tutorial's published figures; do not assume it's importable from `ecco_v4_py`.

Uses: `spatial-difference`, `spatial-interpolation`, `compute-coriolis`, `rotate-to-geographic`

#### ✅ `compute-thermal-wind` — BUILT 2026-08-04 (shear + reconstruction in one skill)
The thermal wind relation connects vertical shear to horizontal density gradients:
```python
dv/dz = -(g/(f*rho)) * drho/dx
du/dz = (g/(f*rho)) * drho/dy
```
Built as **one skill covering both `compute-thermal-wind` (the shear) and
`reconstruct-velocity-from-thermal-wind` (the integration below).** Output is in **model x/y**
coords (like geostrophy); the density gradient uses the same `xgcm.diff → interp_2d_vector`
pattern; the vertical derivative differences over `k` / divides by `drC` (center quantity).

**Rung-1 is N/A — there is NO official `thermal_wind_compute` helper** (confirmed: only
`geos_vel_compute` exists in `ecco_po_tutorials.py`; the tutorial spreads thermal wind across
cells). Correctness rests on three cross-checks (strongest first): **(1)** the shear
reproduces ∂/∂z of the geostrophic velocity from the same pressure field to **corr 0.999**
(analytic identity — thermal wind IS ∂/∂z of geostrophic balance); **(2)** predicted shear
vs the model's *actual* velocity shear (corr 0.64/0.85 — independent variable/path);
**(3)** velocity reconstructed from z0=-3000 m vs the model's *actual* velocity along 26°N
(normalized diff ~0.23, 100–1000 m — the tutorial's deliverable). Teeth-verified. See
`compute-thermal-wind/references/acceptance.md`. *(✅ Rung-7 adversarial pass clean
2026-08-06 — `docs/eval4.md`; skill is DONE. One caveat fixed: reconstruction test
threshold tightened 0.6→0.35.)*

Uses: `load-field` (RHOAnoma + UVEL/VVEL for the check), `load-grid`. Level-1 primitives
still inlined (extraction deferred until a 3rd caller — see roadmap).

#### `reconstruct-velocity-from-thermal-wind`
Integrate thermal wind vertically from a "level of no motion" (z_0):
```python
v_g(z) = integral from z_0 to z of: -(g/(f*rho)) * drho/dx dz
```
Requires upward integration above z_0 and downward integration below z_0, then combining.
**✅ Built as part of `compute-thermal-wind`** (2026-08-04) — the `reconstruct_velocity()`
function, `z0=-3000 m` default, upward+downward integration then combine (transcribed from
the tutorial's cell 21).

#### `compute-ocean-heat-content`
Volume-integrated ocean heat content. THETA is **potential** temperature (deg C), so this is heat content relative to 0 deg C:
```python
Cp = 3994.       # J kg-1 K-1, seawater heat capacity used by MITgcm
rhoConst = 1029. # kg m-3
OHC = (THETA * rhoConst * Cp * rA * drF * hFacC * maskC).sum(["tile","j","i","k"])
```

**"OHC change" requires a difference.** The absolute value above is relative to an arbitrary 0 deg C baseline and is not physically meaningful on its own. For a *change*, either difference two time steps (`OHC(t1) - OHC(t0)`) or integrate an anomaly `THETA - THETA_ref`. Be explicit about the baseline in the output.

Uses: `load-field` (THETA), `load-grid`, `volume-weight`, `global-sum`

#### ✅ `compute-steric-height` — BUILT 2026-08-05 (steric height + thermo/halo split)
Steric height anomaly from density:
```python
h' = integral of (-V_sp'/g) dp        # V_sp' = 1/rho - 1/rho_ref
```
Integrated from the surface (0 dbar) DOWN to a reference level (2000 dbar) — steric height
is relative to that depth. Decomposed into thermosteric (temperature) and halosteric
(salinity) contributions by recomputing density holding S or θ at reference.

**EOS decision (2026-08-05):** the base term uses the model's own `RHOAnoma` (no EOS call);
but the reference profile `1/rho_ref` and the thermo/halo split need a T,S→ρ EOS, and NONE
was available (gsw/TEOS-10 not installed; no EOS in `ecco_v4_py` or the vendored helper). So
we **vendored the canonical MITgcm JMD95** (`ecco-common/vendor/jmd95.py`, pinned to the same
commit 3f0fcca as `ecco_po_tutorials.py`; only edit: `np.asfarray`→`np.asarray(...,float)` for
NumPy 2.0). It's the same EOS ECCO uses internally, so `rho_ref` is consistent with RHOAnoma.
JMD95 wants pressure in **dbar** (Pa×1e-4). Self-tests against its published check value
`densjmd95(35.5,3,3000)=1041.83267`.

**z\* + masking:** integration thickness scaled by `rstarfac = 1 + ETAN/Depth` and gated by
`hFacC` (partial cells); land AND "too-shallow" columns (bathymetry < 2000 dbar) excluded;
global mean removed.

**Verification:** Rung-1 N/A for the integral (EOS check-value anchor instead). Sum-of-parts
(thermo+halo ≈ full) median residual 0.005 m, corr 0.9998. **Steric ≈ SSH** (independent, vs
a different collection): corr 0.921 (steric explains ~85% of SSH variance; the rest is the
non-steric/mass component). Teeth-verified (specvol sign flip → steric-vs-SSH corr −0.92).
✅ Rung-7 adversarial pass clean 2026-08-06 (`docs/eval6.md`; one caveat fixed — added a
thermo/halo label-swap guard vs SST). Skill is DONE. See
`compute-steric-height/references/acceptance.md`.

Uses: `load-field` (RHOAnoma, THETA, SALT, SSH+ETAN), `load-grid`, vendored `jmd95`.
Level-1 primitives still inlined.

#### `compute-transport-across-section`
Volume/heat/salt transport across an arbitrary section.

**⚠️ `*VELMASS` is already thickness-scaled — do NOT multiply by `hFac` again.** This corrects an earlier draft of this section. `UVELMASS`/`VVELMASS` are *mass-weighted* velocities: the partial-cell open fraction (`hFacW`/`hFacS`) is **already baked in**. The installed official helper `ecco_v4_py.calc_section_vol_trsp` computes volume transport as:
```python
x_vol = UVELMASS * drF * dyG     # NO hFacW — it's already in UVELMASS
y_vol = VVELMASS * drF * dxG     # NO hFacS
```
Multiplying by `hFacW`/`hFacS` on top of `*VELMASS` **double-counts partial cells** near topography. (The `hFac`×`drF` face-area form is only correct when building transport from a *non*-mass-weighted velocity like raw `UVEL`.)

**Volume vs. tracer transport — different rules on the bolus:**
- **Volume transport (Eulerian):** `UVELMASS·drF·dyG`. No bolus, no `hFac`. This is what `calc_section_vol_trsp` does.
- **Tracer (heat/salt) transport:** must account for the Gent-McWilliams eddy (bolus) advection. Preferred path is the **precomputed advective+diffusive flux diagnostics** (`ADVx_TH + DFxE_TH`, etc.), which already include bolus and close budgets. This is the production default and matches the official MHT tutorial.
- *(A residual-mean volume transport that adds bolus velocity is a legitimate but different quantity — answering "residual circulation," not "Eulerian volume flux." Only introduce it deliberately, not as a default.)*

**An arbitrary LLC section crosses BOTH native X and Y faces** — you must combine the
west-face (`maskW`) and south-face (`maskS`) components separately, not use one mask.
This is exactly what the official MHT tutorial does.

**⚠️ Reduce each face over its OWN dims BEFORE adding.** The U-face term lives on
`(k, tile, j, i_g)` and the V-face term on `(k, tile, j_g, i)`. Adding the two arrays
directly makes xarray **outer-broadcast** over `j/j_g/i/i_g` — a huge, wrong intermediate.
Sum each contribution to a scalar (or 1-D) first, *then* add:

```python
# Volume transport (Eulerian) — no hFac, no bolus; reduce each face on its own dims:
x_vol = (UVELMASS * drF * dyG * maskW).sum(["k", "tile", "j", "i_g"])
y_vol = (VVELMASS * drF * dxG * maskS).sum(["k", "tile", "j_g", "i"])
vol_transport = x_vol + y_vol                              # now safe to add

# Heat transport — precomputed diagnostics, BOTH faces, each on its own dims:
x_trsp = ((ADVx_TH + DFxE_TH) * maskW).sum(["k", "tile", "j", "i_g"])   # degC m3 s-1
y_trsp = ((ADVy_TH + DFyE_TH) * maskS).sum(["k", "tile", "j_g", "i"])
heat_transport = x_trsp + y_trsp
heat_transport_watts = rhoConst * Cp * heat_transport      # → W (rhoConst=1029, Cp=3994;
                                                           #    MHT tutorial uses 1000·4000)
```
The signed `maskW`/`maskS` come from `ecco_v4_py.get_section_line_masks` (per-face masks
for an arbitrary endpoint pair). Salt transport is identical with `ADVx_SLT+DFxE_SLT` /
`ADVy_SLT+DFyE_SLT`. (Never use a single `section_dims` placeholder — the X- and Y-face
dimension lists genuinely differ: `i_g` vs `i`, `j` vs `j_g`.)

**Default & rationale:** for heat/salt, use the **precomputed flux diagnostics** — one collection, no interpolation, closes budgets exactly, matches the official tutorial. For volume, use `calc_section_vol_trsp`'s `*VELMASS·drF·dyG` form. Prefer the installed `ecco_v4_py` section helpers (`get_section_line_masks`, `calc_section_vol_trsp`) over re-deriving. The `SKILL.md` should state which path it used and why, so the user isn't handed a bare number.

Uses: `load-field`, `make-section-mask`, `apply-mask`, `global-sum`

#### `decompose-flux`
Decompose a flux `v·T` into mean-flow and fluctuating components (Reynolds decomposition), where `v = v̄ + v′` and `T = T̄ + T′` (overbar = time mean, prime = deviation from it). The **full algebraic identity has four terms**:
```
v·T = v̄·T̄  +  v̄·T′  +  v′·T̄  +  v′·T′
      (mean)  (—)      (—)      (eddy)
```
Two common groupings:
- **Time-mean flux:** averaging over time kills the two cross terms (`v̄·T′` and `v′·T̄` average to zero), leaving `mean(v·T) = v̄·T̄ + mean(v′·T′)` — a *mean-advective* part plus an *eddy* (correlation) part. This is usually what's meant by "the eddy flux."
- **Instantaneous split:** all four terms retained.

> **⚠️ Verify with Phil — which decomposition.** Phil's note wrote three terms (`v̄·T′ + v′·T̄ + v′·T′`), dropping the mean-mean `v̄·T̄`. That is likely shorthand for either (a) the flux *anomaly* `v·T − v̄·T̄`, or (b) the time-mean form above. Confirm which grouping he wants before encoding — the term list and the physical interpretation depend on it.

**Built-in validation (L5):** whichever grouping is chosen, **the parts must sum back to the total** `v·T` to machine precision. This is an exact algebraic self-check the skill always runs and reports.

Uses: temporal mean computation (`v̄`, `T̄`), anomaly computation (`v′ = v − v̄`), field multiplication, `apply-mask`, `global-sum`

#### `compute-tracer-budget`
Volume, heat, or salt budget for an arbitrary control volume. The *only* new knowledge this skill encodes (per Phil) is **which terms to sum** and their signs — the mechanics reuse lower-level skills. For a tracer `C`, the budget balances the local tendency against the convergence of fluxes plus forcing:
```
∂(C·vol)/∂t  =  −∇·(advective flux)  −∇·(diffusive flux)  +  forcing/sources
```
Concretely, using ECCO's diagnostics: sum the advective (`ADVx_/ADVy_/ADVr_`) and diffusive (`DFxE_/DFyE_/DFrE_/DFrI_`) flux convergences across the control-volume faces, add surface forcing (heat flux, freshwater/salt flux) for volumes touching the surface, and compare to the stored tendency (`THETA`/`SALT` time difference × volume).

**Built-in validation (L4 — the strongest oracle):** a correctly assembled budget **closes to ~1e-10**. Non-closure is a *proof* of error. The skill reports the residual as a fraction of the largest term.

Uses: `load-field` (flux diagnostics + forcing + tracer), `load-grid`, `apply-mask` (control-volume mask), `global-sum`, sign bookkeeping across faces

**Getting the terms exactly right is the crux** — this is where a domain expert's review matters most, and where the closure oracle earns its keep. See the ECCO v4 budget tutorials (heat, salt/freshwater) for the authoritative term lists.

### Level 5: Diagnostic Comparisons

#### `compute-normalized-difference`
Quantify agreement between two fields. The PO tutorials normalize by the magnitude of the *reference* field (velocity as complex vectors):
```python
norm_diff = |u_diff + i*v_diff| / |u + i*v|      # tutorial convention
```
A symmetric alternative, `|A - B| / (|A| + |B|)`, is better-behaved when both fields can be near zero. Pick one convention per skill and state it — the two are not interchangeable.

Can be binned by latitude or depth using area-weighted averages.

#### ✅ `compute-curl` — BUILT 2026-08-05 (curl + Ekman pumping, Recipe 6 / Q5)
Vertical component of the curl of a vector field on the LLC grid (e.g. wind-stress curl
for Ekman pumping). **A bare `d(v)/dx − d(u)/dy` on native components is wrong** — and so
is a single rotation. On the LLC grid there are **TWO rotations**: rotate the components
to zonal/meridional, *and* rotate the derivative vectors afterward (a derivative "along
model X" is not "along zonal" on rotated tiles). The exact sequence from the official
*native-grid gradient/curl* tutorial (verified 2026-07-25):

```python
# 0. Get components at TRACER points as {'X':cx, 'Y':cy}:
#    - velocity (u@i_g, v@j_g): interpolate first
#         vec = grid.interp_2d_vector({'X': u_x, 'Y': v_y}, boundary='fill')
#         cx, cy = vec['X'], vec['Y']
#    - stress (oceTAUX/oceTAUY, already at i,j): use directly, NO interp
#         cx, cy = tau_x, tau_y
# 1. rotate COMPONENTS model→geographic
u_lambda = cx*CS - cy*SN         # zonal
v_phi    = cx*SN + cy*CS         # meridional
# 2. derivatives of each geographic component along BOTH model axes
du_lambda_dx = grid.diff(u_lambda,'X')/dxC ; du_lambda_dy = grid.diff(u_lambda,'Y')/dyC
dv_phi_dx    = grid.diff(v_phi,'X')/dxC     ; dv_phi_dy    = grid.diff(v_phi,'Y')/dyC
# 3. interp the derivative pairs to tracer points
gu = grid.interp_2d_vector({'X': du_lambda_dx, 'Y': du_lambda_dy}, boundary='fill')
gv = grid.interp_2d_vector({'X': dv_phi_dx,    'Y': dv_phi_dy},    boundary='fill')
# 4. SECOND rotation — derivative directions model→geographic
du_lambda_dphi   = gu['X']*SN + gu['Y']*CS
dv_phi_dlambda   = gv['X']*CS - gv['Y']*SN
# 5. curl
curl_z = dv_phi_dlambda - du_lambda_dphi
```

**Both rotations are mandatory** and must be encoded in the skill, not left to agent
inference. **Correction (2026-08-05, from the build):** the two rotations use the *same*
formula (`zonal = X·CS − Y·SN`, `merid = X·SN + Y·CS`) — it's one rotation applied twice
(to components, then to the derivative vectors); earlier "differing sign conventions"
wording was misleading. Skipping the 2nd rotation shifts the curl by ~30% (teeth-tested).

**Grid-position correction (2026-08-05 — this was BACKWARDS before):** `oceTAUX`/`oceTAUY`
are NOT at tracer points — the real data has `oceTAUX` on the U-face (`i_g`) and `oceTAUY`
on the V-face (`j_g`). So they DO need step-0 `interp_2d_vector` to centers, exactly like
`UVEL`/`VVEL`. It is `EXFtaux`/`EXFtauy` that sit at tracer points (but those are the bulk
stress we avoid for Ekman). **Units:** curl is `[field]/m` — Pa/m for a stress curl, s⁻¹
for a velocity curl (relative vorticity).

**Verification:** no official curl helper exists (Rung 1 N/A); the CS/SN rotation core is
bit-identical to `ecco_v4_py.vector_calc.UEVNfromUXVY`, and Ekman pumping `w_E` matches the
model's actual `WVEL` at ~30 m to corr 0.74 / sign-agreement 0.89 (Rung 5). ✅ Rung-7
adversarial pass clean 2026-08-06 (`docs/eval5.md`; both historical rotation bugs confirmed
blocked; one caveat fixed — teeth threshold 0.05→0.20). Skill is DONE. See
`compute-curl/references/acceptance.md`.

Uses: `load-field` (oceTAUX/oceTAUY + WVEL), `load-grid`. Level-1 primitives still inlined.

#### `compute-ekman-transport` — ⏸️ DEFERRED (2026-08-05, gated on Phil Q5)
Wind-driven Ekman transport (depth-integrated volume transport per unit length, m^2 s-1) from wind stress. **Note the `rho`** — without it the units don't close:
```python
M_x =  tau_y / (rho * f)
M_y = -tau_x / (rho * f)
```

Compare with the model's integrated upper-ocean (ageostrophic) velocity.

**Deferred pending Phil (Q5 in `questions-for-phil.md`).** Unlike every other Phil-free
skill, Ekman transport has **no ECCO tutorial** (only 4 Intro-to-PO notebooks exist) — so no
Rung-1 helper and no Rung-2 number. The formula above is trivial; the scientific value is
entirely in the model comparison, and "compare with the model's upper-ocean velocity" is
ambiguous (ageostrophic residual = total − geostrophic, vs raw upper-ocean velocity which the
geostrophic flow dominates, vs another diagnostic — and over what "upper ocean" depth). We
declined to guess and shipped nothing below the verification bar the other five cleared;
Phil's Q5 answer unblocks it. The build is small (reuses curl's stress-on-faces handling and
geostrophy's velocities). Input field: `oceTAUX`/`oceTAUY` (total stress, on U/V faces — see
the curl grid-position note above), NOT `EXFtaux`/`EXFtauy`.

### Level 6: Visualization

Plotting is a first-class tutorial objective (and how a user *sees* whether an answer is sensible). The recurring gotcha: you cannot `plot(field)` naively across the LLC grid — tiles 7–12 are rotated, so a raw multi-tile array looks scrambled. This is handled by using the official `ecco_v4_py` plotters.

#### ✅ `plot-ecco-field` — BUILT 2026-07-25 (consolidated)

**One skill, three modes** — supersedes the originally-planned separate `plot-single-tile`
/ `plot-masked-2d` / `plot-global-map` (consolidated because they share almost all logic
and all wrap the same official functions):
- `--mode tile` — one LLC tile in **model** orientation (Q7). `ecco.plot_tile`.
- `--mode alltiles` — all 13 tiles laid out. `ecco.plot_tiles`.
- `--mode global` — stitched lat-lon world map, tiles rotated/re-projected (Q12), the
  geographically-correct whole-ocean view. `ecco.plot_proj_to_latlon_grid`.

Headless by design (`Agg` backend → saves PNG to `./plots/`, gitignored). Shared helpers
in `ecco_common/plots.py` (`plot_global`/`plot_tile`/`plot_all_tiles`/`to_2d`) so any calc
skill can visualize its output. Verified by rendering a physically-correct global SST map.
Rung 1 = uses the official plotters, not a reinvention.

Uses: `load-grid`, `load-field`, `ecco_v4_py` plotting. *(The mask-overlay case Q11 —
drawing a section/region mask on a plot — is not yet a dedicated mode; add if needed.)*

---

## Calculation Recipes

### Recipe 1: Global Mean Ocean Heat Content Change

**Complexity:** Simple (2-3 skills)

1. `load-field` → THETA (temperature)
2. `load-grid` → geometry
3. `volume-weight` → THETA * rhoConst * Cp * cell_volume
4. `global-sum` → sum over all ocean cells

### Recipe 2: Geostrophic Balance Verification

**Complexity:** Medium (5-6 skills)

1. `load-field` → PHIHYDcR (pressure anomaly), **RHOAnoma** (for actual density), UVEL/VVEL
2. `load-grid` → geometry
3. Replace velocity land NaNs with 0 before vector interpolation
4. `spatial-difference` → `dp/dx = rhoConst·d(PHIHYDcR)/dx`, `dp/dy` likewise
5. `spatial-interpolation` → interpolate gradients and velocities to common (tracer) points
6. `compute-coriolis` → f at each grid cell
7. `compute-geostrophic-velocity` → `v_g = dp_dx/(ρf)`, `u_g = -dp_dy/(ρf)` with `ρ = rhoConst+RHOAnoma`
8. mask land, the equatorial singularity (f→0), and very small reference velocities
9. `compute-normalized-difference` → quantify agreement (by latitude/depth, area-weighted); keep in model coords for the balance check, rotate only for map output

### Recipe 3: Thermal Wind and Velocity Reconstruction

**Complexity:** High (7-8 skills)

1. `load-field` → density, velocity
2. `load-grid` → geometry
3. `spatial-difference` → horizontal density gradients
4. `spatial-interpolation` → to common grid positions
5. `vertical-difference` → du/dz, dv/dz
6. `compute-coriolis` → f
7. `rotate-to-geographic` → model→geographic axes
8. `reconstruct-velocity-from-thermal-wind` → integrate from level of no motion
9. `find-indices-along-latitude` + `extract-transect-data` → visualize along section

### Recipe 4: Volume/Heat/Salt Transport Across a Section

**Complexity:** High (5-6 skills)

1. `load-field` → **volume**: `UVELMASS`/`VVELMASS`; **heat**: `ADVx_TH+DFxE_TH` *and* `ADVy_TH+DFyE_TH`; **salt**: `ADVx_SLT+DFxE_SLT` *and* `ADVy_SLT+DFyE_SLT` (both X- and Y-face components — a section crosses both)
2. `load-grid` → geometry
3. `make-section-mask` → per-face masks `maskW`, `maskS` for the endpoint pair (use `ecco_v4_py.get_section_line_masks`)
4. `apply-mask` → apply `maskW` to X-face terms, `maskS` to Y-face terms
5. reduce **each face over its own dims** then add: `x=( … ·maskW).sum(['k','tile','j','i_g'])`, `y=( … ·maskS).sum(['k','tile','j_g','i'])`, `transport = x + y`
6. (heat/salt) × ρ·Cp / units as needed

See `compute-transport-across-section` for the full reasoning. **Key traps:** combine **both** X- and Y-face components with their own masks (not one mask); **reduce each face on its own dims before adding** (else xarray outer-broadcasts `i_g`×`i`, `j`×`j_g`); don't multiply `*VELMASS` by `hFac` (already mass-weighted); don't hand-add bolus to a *volume* transport. Prefer the installed `calc_section_vol_trsp` / `get_section_line_masks` helpers.

### Recipe 5: Flux Decomposition

**Complexity:** High (4-5 skills, assumes multi-time data)

1. `load-field` → velocity and tracer over multiple timesteps
2. Compute temporal means: `vel_mean`, `tracer_mean`
3. Compute anomalies: `vel' = vel - vel_mean`, `tracer' = tracer - tracer_mean`
4. `decompose-flux`:
   - Mean advection: `vel_mean * tracer'`
   - Eddy-driven: `vel' * tracer_mean`
   - Nonlinear: `vel' * tracer'`
5. `apply-mask` + `global-sum` for any of the above

### Recipe 6: Ekman Pumping Verification — ✅ BUILT 2026-08-05 (`compute-curl`)

**Complexity:** Medium (4-5 skills)

1. `load-field` → wind stress (tau_x, tau_y = `oceTAUX`, `oceTAUY`), vertical velocity (WVEL)
2. `compute-curl` → vertical curl of wind stress on the LLC grid. **`oceTAUX`/`oceTAUY` are on the U/V faces (`i_g`/`j_g`), NOT tracer points — so DO interpolate to centers first**, then: rotate components→geographic → diff each along both model axes → interp derivatives → **rotate the derivative vectors** (same rotation) → combine. **Two rotations.** Not a bare `d(tau_y)/dx − d(tau_x)/dy`. See `compute-curl`.
3. `compute-coriolis` → f
4. Ekman pumping velocity. The full form is `w_E = (1/rho) * k · curl(tau / f)`, which expands to:
   ```
   w_E = curl(tau)/(rho*f)  +  (beta * tau_zonal)/(rho * f^2)
   ```
   The second (beta) term is **not** negligible for the Sverdrup/pumping story. The `curl(tau)/(rho*f)` f-plane approximation is acceptable only if stated explicitly (`use_beta=False`). Built with the β term on by default.
5. compare w_E with WVEL at the base of the Ekman layer (~30 m). **Result:** corr 0.74, sign-agreement 0.89 off-equator — Ekman pumping is clearly visible in the model's vertical velocity. (A dedicated `compute-normalized-difference` skill is still designed-but-unbuilt; the comparison is currently done inline in the curl skill's test.)

---

## Key Design Principles

1. **Composability** — Each skill does one thing. Complex calculations chain skills together.

2. **Grid-awareness** — Every skill that touches spatial data must know about C-grid staggering. We never diff or interpolate without knowing where the input lives and where the output should live.

3. **Mask-first** — Land masking must be applied before any spatial operation to avoid contaminating ocean values with NaN or land values.

4. **Unit tracking** — Skills should document what units go in and come out. PHIHYDcR has units of m^2/s^2 (it's p/rhoConst, not pressure itself).

5. **Tile-aware** — Many operations need to work across all 13 tiles. The LLC grid's topology means tile boundaries require special treatment (handled by xgcm).

6. **Lazy computation** — Use dask/xarray lazy evaluation where possible, call `.compute()` only when needed for operations that require numpy arrays.

7. **Validation is defense in depth** — see the Validation section. Every skill stacks multiple *independent* checks (input/units/physical-bounds/closure/cross-check/benchmark) so a wrong answer must defeat all of them. Each skill states which layers apply and runs them; a skill with no stated validation is treated as unfinished.

8. **Teach, don't just compute** — The target user knows the AI/engineering side but is *learning the ocean science*. A skill that silently returns a number is a missed opportunity and a trust risk (the user can't tell a right answer from a plausible-wrong one). Each `SKILL.md` should have the agent narrate its reasoning as it works: which field it's loading and *why that one* (e.g. "using `oceTAUX`, the total ocean stress, not `EXFtaux`, because sea ice modifies the stress that drives Ekman flow"), which grid position a quantity lives on, what each masking/weighting step is for, what the units are at each stage, and what the closure/residual check came back as and whether that's good. Prefer explaining a decision over hiding it behind a helper. The skill should read like a knowledgeable colleague walking you through the calculation, not a black box.

---

## Validation: Defense in Depth

> **The binding protocol is `docs/verify.md`.** This section describes the runtime
> validation layers a skill runs on its own output; `verify.md` is the overarching
> Science V&V protocol (verification ladder, "needs Phil" register, evidence-not-
> confidence reporting, definition of "done", standing adversarial review). If the two
> ever disagree, `verify.md` wins for science-correctness policy.

**Goal: correct answers, and the ability to *know* they're correct.** No single check catches every error, so every skill stacks multiple *independent* validation layers. A wrong answer has to defeat all of them to escape — and each layer catches a different class of mistake. This is the project's core value proposition: not just "the AI can compute this," but "the AI can prove it computed it right."

### First, three different things the word "verify" means here

These are separate and must not be conflated (the naming reflects it):

| Kind | Question it answers | Scope | When it runs | Named / defined as |
|------|--------------------|-------|-------------|--------------------|
| **Environment verification** | "Is the toolchain/venv working?" | the `.venv` + libraries | on demand, anytime | the **`ecco-setup-verify`** skill (env only — nothing scientific) |
| **Runtime validation** | "Is *this answer* trustworthy?" | one calculation's output | every time a calc skill runs | the **6 layers below**, reported live to the user |
| **Acceptance testing** | "Is this skill *correctly implemented*?" | one skill's code | once, during development, by us | **build-time acceptance test** (see end of this section) |

The rest of this section is about **runtime validation** (the 6 layers) and **acceptance testing**. Environment verification is covered under Environment & Setup.

The layers, cheapest/earliest first:

### Layer 1 — Input & metadata checks (catches: wrong data, wrong grid position)
Before any math, the skill verifies its inputs:
- Field is on the grid position it expects (tracer center vs U/V face) — check the dimension names (`i` vs `i_g`, `j` vs `j_g`).
- Units match the assumption (read the `units` attribute, don't trust the variable name).
- Time range / coordinates are what was requested.
- The right collection was loaded (concept_id / ShortName), including the sea-ice-aware vs bulk distinction (`oceTAUX` vs `EXFtaux`) and Eulerian vs bolus (`UVELMASS` vs `UVELSTAR`).

### Layer 2 — Dimensional / unit analysis (catches: missing factors like ρ, wrong metric)
The skill tracks units symbolically through each step and asserts the final units match the expected physical quantity. This is what catches a dropped `1/rho` or using `rA` where a face area was needed — the units simply won't come out to m²/s or Watts.

### Layer 3 — Physical sanity bounds (catches: order-of-magnitude and sign errors)
Assert results fall in physically plausible ranges before trusting them:
- Ocean velocities O(0.01–1 m/s), not 100 m/s.
- Temperatures in the JMD95 valid range (~-2.3 to 36 °C).
- Sign checks (e.g. northward heat transport is positive in the North Atlantic; density increases with depth on average).
- NaN/inf audit: land points masked, no NaNs leaking into sums.

### Layer 4 — Conservation / closure oracle (catches: subtle assembly errors) — *the strongest layer*
Because ECCO is a free-running MITgcm solution (not a nudged reanalysis), its heat, salt, volume, and momentum budgets **close to machine precision** when assembled correctly:
- A correct **volume/heat/salt budget** for any control volume closes to ~1e-10 (tendency = convergence of advection + diffusion + forcing). If the assembled budget doesn't close, it is *provably* wrong — no expert judgement needed.
- This is a near-perfect oracle: it's derived from the model's own conservation laws, not an external estimate, so "passes closure" ≈ "correct."

### Layer 5 — Internal cross-checks (catches: method-specific bias)
Compute the same quantity two independent ways and compare:
- Heat transport via precomputed flux diagnostics (`ADVx_TH + DFxE_TH`) vs a residual-velocity reconstruction (Eulerian + bolus × tracer) — should agree.
- Geostrophic velocity vs actual model velocity (small normalized residual away from equator/surface — the tutorials show this).
- Divergence-based vs flux-based section transport.

### Layer 6 — External benchmarks (catches: right-method-wrong-reality)
Compare against published observational estimates:
- Atlantic MOC at 26°N *(placeholder ~17 Sv — confirm with Phil)*; RAPID array.
- Global mean OHC trend against published figures.
- Drake Passage transport *(placeholder ~140 Sv — confirm with Phil)*.

This is the weakest layer for *proving* correctness (observations have their own uncertainty, and ECCO may legitimately differ), but the most convincing to a domain scientist and best at catching a calculation that passed every internal check yet models the wrong thing.

### How this is packaged
Each skill's `references/` includes runnable check snippets for whichever layers apply, and the `SKILL.md` instructs the agent to **run them and report each result to the user** (Design Principle #8 — teach, don't just compute). The user sees: "units came out as W ✓; result 1.3 PW is within physical range ✓; budget closed to 3e-11 ✓; agrees with the flux-diagnostic method to 0.4% ✓." A number that arrives with its validation trail is one you can trust — and one you can learn from.

Not every skill can hit all six layers (a simple plotting skill has no conservation law to check), but **every skill states which layers it applies and why the others don't apply.** Silence about validation is treated as a bug.

> **⚠️ Verify with Phil — validation targets & tolerances.** The Layer 6 anchor values above (MOC ~17 Sv at 26°N, Drake ~140 Sv, RAPID) are placeholders inserted by the AI, **not confirmed science**. The Layer 3 sanity bounds are first-guess ranges. Before building the transport/budget skills, confirm with Phil: (1) which benchmark quantities and target values each skill validates against, (2) the acceptable tolerance/residual for each layer, (3) the preferred reference source for each number, and (4) whether any sanity bounds are too loose or too tight. Do not lock these into skill tests until confirmed.

### Build-time acceptance testing (how *we* verify a calculation skill before shipping)

Distinct from the runtime layers above: this is the **developer gate** that answers "is this skill's code correct?" — run once (and in CI/regression) during development, not on every user invocation. A calculation skill is not "done" until it passes:

1. **Reproduces the tutorial's published result.** The ECCO PO tutorials print concrete numbers/figures; a skill built from a tutorial must reproduce that value within tolerance on the same input. This is the primary acceptance criterion where a tutorial exists.
2. **Its own runtime validation layers actually fire.** Confirm the skill really runs its stated Layer checks and that they *fail* when fed deliberately bad input (a check that never fails is worthless). **Pattern (from Recipe 1):** ship a `scripts/test_validation.py` with negative *and* positive cases against the skill's `validate()` using tiny synthetic arrays (no download) — e.g. Recipe 1 tests THETA-in-Kelvin, too-warm mean, wrong units, non-tracer dims, bad volume. Every calc skill copies this.
3. **Closure/oracle holds on real data** (for budget/flux skills) — the ~1e-10 conservation residual, on an actual ECCO control volume, not a synthetic one.
4. **Runs end-to-end in the real environment** (the `.venv` from `ecco-setup`), so API drift like the xgcm `padding=` change is caught here, not by the user.

Where no tutorial number exists (novel combinations), acceptance leans on the internal cross-check (Layer 5) and Phil's review of the method. Record each skill's acceptance evidence in its `references/` so "why do we trust this skill" is auditable.

---

## Implementation Notes

### What `ecco_v4_py` provides vs. what we build

`ecco_v4_py` already provides:
- `ecco.get_llc_grid(ds_grid)` — creates the xgcm Grid object
- Global map plotting functions
- Some utility functions

We build skills on top of this — the skills encode the **sequence of operations** and the **physical reasoning** (which fields to load, which grid positions matter, which masks to apply).

### The `ecco_po_tutorials` module

The thermal wind tutorial imports `from ecco_po_tutorials import *`, which provides:
- `plot_mask()` — overlay land mask on plots
- `mean_weighted_binned()` — compute weighted means binned by latitude or depth
- `depth_two_subplots()` — split-depth plotting
- `llc_grid_idx_along_lat()` — find grid indices along a latitude line
- `data_along_lat()` — extract data along those indices

These are candidate utilities to incorporate into our skills.

### Critical gotchas from the tutorials

1. **PHIHYDcR vs. pressure — and don't drop the density factor**: `PHIHYDcR = p/rhoConst − gz`, so `∂p/∂x = rhoConst · ∂(PHIHYDcR)/∂x` (the `gz` term has zero horizontal gradient at fixed depth). Geostrophic balance is `f·v = (1/ρ)·∂p/∂x = (rhoConst/ρ)·∂(PHIHYDcR)/∂x`. **Do not** simplify to `f·v = ∂(PHIHYDcR)/∂x` — that silently sets `rhoConst/ρ = 1`, a spatially-varying error of a few percent. The tutorial scales by `rhoConst` and divides by actual density `ρ = rhoConst + RHOAnoma`. So a geostrophic calc needs `RHOAnoma`, not just `PHIHYDcR`.

2. **NaN handling**: Velocities must have NaN replaced with 0 before interpolation (the tutorials do `UVEL.values[np.isnan(UVEL.values)] = 0`).

3. **Vertical direction**: k indices increase downward but z increases upward. Vertical differences need a negation.

4. **Rotation**: Any vector quantity (velocity, gradient) on tiles 7-12 must be rotated to geographic axes before physical interpretation. Use CS/SN arrays.

5. **drC vs drF**: `drF` is cell thickness (interface to interface). `drC` is center-to-center distance. Use the right one depending on what you're differencing.

6. **GM bolus velocity (tracer transport only) & `*VELMASS` thickness scaling**: *tracer* transport in ECCO v4 is Eulerian + Gent-McWilliams bolus — prefer the precomputed `ADVx_/ADVy_/DFxE_/DFyE_` flux diagnostics (bolus already included). *Volume* transport is Eulerian only (`calc_section_vol_trsp`: `UVELMASS·drF·dyG`) — no bolus. Critically, `UVELMASS`/`VVELMASS` are **mass-weighted** (partial-cell `hFacW`/`hFacS` already baked in): do **not** multiply them by `hFac` again — that double-counts partial cells. The `hFac`×`drF` face-area form is only for raw (non-mass-weighted) velocities.

7. **Section area is a face area**: use `dyG*drF*hFacW` (U-face) or `dxG*drF*hFacS` (V-face) for vertical cross-sections — never `rA` (that's the horizontal top-face area).

8. **Wind-stress and Ekman need rho**: transport/pumping formulas carry a `1/rho`. Dropping it breaks units.

9. **Pin xgcm < 0.10** (we use 0.9.0): `ecco_v4_py` 1.8.1's `get_llc_grid()` calls `xgcm.Grid(ds, periodic=False, …)`, and `periodic=` was removed in xgcm 0.10 — so ECCO's own grid constructor crashes with xgcm ≥ 0.10 (ecco_v4_py declares only `xgcm>=0.5.0`, no ceiling, so pip pulls an incompatible version by default). With 0.9.0 the tutorials' `boundary=`/`fill_value=` diff/interp API is correct and runs verbatim. Verified 2026-07-23 against the real geometry file. Enforced in `ecco-setup/scripts/requirements.txt`.

---

## Next Steps

1. ✅ **`ecco-setup` + `ecco-setup-verify` built and tested** (`.claude/skills/`) — survey + venv builder + `requirements.txt`; verify skill checks Python band, imports all 11 libs, and runs the real `ecco.get_llc_grid` smoke test. **`ecco-setup` auto-hands off to `ecco-setup-verify`** on both reuse and fresh-build paths (one source of verification truth; setup's exit code = verify's result). Verified on macOS/arm64/Python 3.12.13: all deps install as wheels; a from-scratch `--reset` rebuild resolves the `xgcm<0.10` pin to 0.9.0 and finishes "verified"; the "no venv" guided-failure path also tested. **Remaining:** test on Linux/Windows and on a machine lacking a supported Python; freeze an exact `pip freeze` lockfile.
2. ✅ **`ecco-common` shared library + `load-grid` + `load-field` built and tested** (2026-07-23) — Option A composition (see architecture section). `ecco_common` provides `load_grid()`, `load_field()`, CMR-direct download with `.netrc` auth (bypasses the unreliable `ecco_access`), and a project-local `./data/ecco` cache. Verified end-to-end: grid downloads+builds the xgcm object, fields download by month, cache-hits work, the `months=` selector avoids the month-edge overlap gotcha, and the >1 GB size guard fires. `./data` and `.venv` gitignored.
   **Hardened 2026-07-25 (external-eval round 1):** (a) **project root derived from file location, not `os.getcwd()`** — loaders/setup/verify now work from any CWD; (b) **offline cache reuse** via a `cache_index.json`; (c) **CMR pagination** via `CMR-Search-After`; (d) verify reads the project cache, not `~/Downloads`.
   **Hardened 2026-07-25 (external-eval round 2):** (e) **daily collections** + `concept_id_for()` live CMR ShortName resolution; (f) **`load_field` selector validation**; (g) **cache index backfill** + atomic writes; (h) **OHC time-coordinate check**; (i) L2 relabeled "numeric sanity."
   **Hardened 2026-07-25 (external-eval round 3):** (j) **size-guard reads the `.nc` entry by filename** (not the first MB entry, which could be the `.sha512` sidecar → wildly under-count); checksum now captured; (k) **size guard applied once over the whole request** (per-key checking leaked a 40-day/1.2 GB request through — found by testing); (l) **`days=['YYYY-MM-DD']` selector** for daily data (midnight-edge overlap, mirrors `months=`); (m) **daily backfill fix** — index key regex now handles `YYYY-MM-DD`, not just `YYYY-MM` (daily offline reuse was silently broken).
   **Automated test suite added 2026-07-25 (eval-round-3 finding #4):** `.claude/skills/ecco-common/tests/test_ecco_common.py` — **13 offline tests** (monkeypatched CMR + fake downloads, temp-dir cache; no network/credentials) covering size-by-filename vs sidecar, CMR pagination token order, whole-request size guard (small/large/assume_yes/unknown-size), month+day midpoint ranges, daily+monthly key extraction, cache backfill, atomic index write, selector validation, live ShortName resolution, and offline reuse. Verified the suite has teeth (reintroducing the sidecar bug fails it). `.claude/skills/run_all_tests.py` runs all suites (23 tests: 13 + 10 OHC). **Remaining:** wire into CI; exact lockfile; cached-file checksum *verification* (captured, not yet checked); index locking for concurrent runs; `.netrc` credential UX.
3. Give each skill a closure/residual test that uses ECCO's exact conservation as the correctness oracle.
4. Build Level 2-3 skills on top of Level 0-1.
5. ✅ **Recipe 1 (OHC) built and tested** (`compute-ocean-heat-content`, 2026-07-23) — the reference calculation skill. Chains `load_grid`+`load_field` (Option A), volume-weights `THETA·rhoConst·Cp·rA·drF·hFacC`, prints an L1/L2/L3/L6 validation trail, and reports OHC *change* between two months. Acceptance: volume-mean THETA 3.59 degC (matches known ~3.5), ocean volume within 0.4% of literature, Jan2000→2010 change +7.8e22 J (right sign/magnitude). Established the calc-skill pattern + `references/acceptance.md`. **Negative+positive validation tests** (`scripts/test_validation.py`, now 10 cases): guards proven to *fire* on bad input and pass on good. **Hardened 2026-07-25 (external-eval fix #4):** L1 now checks for **non-finite values in wet cells** (a wet-cell NaN previously passed silently); L2 is now a real finiteness/volume>0 assertion, not an unconditional ✓. New tests cover wet-cell NaN (fails), land-cell NaN (still passes), and non-finite mean (fails). **TODO:** seasonal averaging for rigorous trends; a full end-to-end golden-value regression (not just the unit-level guard tests).
6. Implement Recipe 2 (geostrophic balance) as the medium-complexity demonstration with a residual check.
7. Build the section/transport machinery (Recipe 4) — including bolus velocity and correct face areas — for the flux calculations.
8. Dogfood in Claude Code: confirm an agent, on a **clean machine with no libraries**, runs setup → verify → reproduces the tutorial figures/numbers end to end.

**Throughout all of the above:** keep this design doc in sync per the [Working Convention](#-working-convention-this-document-is-living) at the top — every implementation decision, constraint, or change updates the doc in the same step. Treat "doc no longer matches reality" as a build failure.

---

## Open Questions & Working Context

*This section is the shared, human-visible record of what's decided, what's still open, and the working context behind this design. (It mirrors what the AI keeps in its own memory — kept here so it's visible to everyone, not just the assistant.) Update it as questions get resolved.*

### Collaboration context
- **jwood** owns the AI/engineering side (wiring up the skills, the proposal); **Phil** (physical oceanographer, UWG) owns the science use cases and is the authority on the questions flagged below.
- This work originated in a UWG meeting where Phil proposed "guiding" AI to do correct ECCO science with specified, trustworthy outputs. The design is aimed at that proposal.
- **jwood is learning the ocean science while building this**, and has stated **correctness is the top priority** — hence Design Principle #8 (teach, don't just compute) and the 6-layer validation framework.

### ⚠️ Open questions for Phil (blocking full build of some skills)

**Full, sendable text lives in `docs/questions-for-phil.md`** (the single source — phrased
for an oceanographer, with what each item unblocks). Summary here for working context:

1. **Benchmark targets & tolerances** — real-world values + acceptable deviation to
   validate against (MOC/Drake/RAPID numbers in the docs are AI placeholders); also
   confirm the Layer-3 sanity bounds. *Unblocks: transports, MOC, obs benchmarking.*
2. **Flux-decomposition grouping** (`decompose-flux`) — 3-term vs 4-term; which physical
   grouping (flux anomaly / time-mean eddy / full instantaneous split). *Unblocks: Recipe 5.*
3. **Budget term lists, signs, residual definition** (`compute-tracer-budget`) — exact
   advective/diffusive/forcing terms, z* handling, normalized residual units.
   *Unblocks: the heat/salt/volume budget skills.*
4. **Scientific-fit check** (ongoing) — is each calculation, as scoped, the one the
   science actually needs. *Applies to every skill.*
5. **Ekman-transport comparison target** (`compute-ekman-transport`) — which model
   comparison (ageostrophic residual vs raw upper-ocean velocity vs …) and over what
   "upper ocean" depth. No ECCO tutorial exists for it, so verification hinges on this.
   *Unblocks: `compute-ekman-transport` (deferred pending this answer).*

*(If you edit these, edit `questions-for-phil.md` first — it's canonical — then re-sync
this summary.)*

### Decisions already made (for the record)
- **Architecture:** Agent Skills (`SKILL.md` + vetted `scripts/` + `references/`), usable in Claude Code — not a bare Python library.
- **Environment:** project-local **`venv` + `pip` only — no conda** (jwood's explicit preference). Verified that cartopy/netCDF4/pyresample now ship PyPI wheels, so this needs no system compilers.
- **Interpreter selection:** probe `python3.12 → 3.11` (newest in-band wins, capped at 3.12), *not* the bare `python3` (often too new — e.g. Homebrew's is now 3.14). Band floor is **3.11** (ecco_access requirement). Build `.venv/` once from the chosen interpreter, then reuse it for all runs; skills call the venv Python directly rather than requiring manual activation. Cross-platform (macOS/Linux/Windows).
- **Wheels-only install works (verified 2026-07-23):** venv + pip installed the entire stack from PyPI wheels on macOS/arm64/Python 3.12 — no conda, no compilers. Known-good versions captured in `ecco-setup/scripts/requirements.txt`.
- **Reset** (`ecco-setup --reset`): *implemented & tested* — delete `.venv/` and rebuild from scratch (re-resolves the `xgcm<0.10` pin, finishes verified).
- **Transport default:** precomputed flux diagnostics (Option 2, budget-closing) as the default; residual-velocity path (Option 1) offered as the "show your work" teaching path.
- **Ekman stress field:** use `oceTAUX`/`oceTAUY` (total ocean stress, sea-ice-aware), not `EXFtaux`/`EXFtauy` (bulk wind stress).
- **Data storage (decided 2026-07-23):** cache-on-demand in project-local `./data/ecco/<ShortName>/`, gitignored, with a size-aware download guard. Never bulk-download (full archive ~90–100 GB); individual analyses are 16–350 MB. See "Data Storage Strategy" section.
- **Skill composition (decided & built 2026-07-23):** Option A — shared `ecco_common` package that skills import; calculation skills run in one venv-python process passing in-memory xarray objects between imported helpers. Env skills stay subprocess-style (interpreter boundary). See "How skills compose."
- **Downloads use CMR + requests/.netrc, not `ecco_access`** — verified working; `requests` (not urllib) is required so Earthdata's URS redirect carries auth (urllib 401'd).
- **No MCP-server dependency (decided 2026-08-04):** skills call the NASA CMR REST API directly; they do NOT depend on the "earthdata" (formerly "CMR") MCP server. MCP is fine for build-time/interactive discovery, but runtime must stay standalone, reproducible, and pinned. See the decision note at the top of the Data Access Pattern section.
- **Month selection queries mid-month** — monthly-mean granules overlap at month edges, so an edge-aligned range pulls the neighbouring month too; `load_field(months=[...])` queries the 14th–16th to get exactly the intended month.
- **All 10 CMR collections verified** (core + flux + stress + bolus) with concept IDs recorded in the Data Access section; Jan-2000 tutorial granule confirmed to exist.

### Unverified items to check at build time
- ✅ `plot_proj_to_latlon_grid` — **confirmed present** in installed `ecco_v4_py` 1.8.1 (2026-07-25).
- `geos_vel_compute` — **confirmed NOT in `ecco_v4_py` 1.8.1**; it's in the separate `ecco_po_tutorials.py` helper. Any cross-check must import from there, not `ecco_v4_py`.
- The `ecco_po_tutorials` helper module's exact contents/availability (it ships `geos_vel_compute`, `plot_mask`, `mean_weighted_binned`, transect helpers — confirm the download path when building Recipe 2/3).
