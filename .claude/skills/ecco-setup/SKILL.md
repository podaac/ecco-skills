---
name: ecco-setup
description: Set up AND verify the Python environment for ECCO ocean-data skills. Use this BEFORE any ECCO calculation, plotting, or data-access skill runs — it surveys the machine's Python, builds an isolated project-local venv (3.11-3.12, pip only, no conda), installs the scientific stack, and verifies it works. It also has a standalone VERIFY MODE (no rebuild) to health-check an existing environment — use that when the user asks "is my ECCO environment working?" or when a calculation skill errors and you need to rule out a broken environment. Triggers when the user wants to "set up ECCO", "install/verify the ECCO environment", asks "which Python do I have", or when another ECCO skill finds no working .venv.
---

# ecco-setup

> **🔬 Verification status (per `docs/verify.md`): ✅ verified (infrastructure).** Tested
> on macOS/arm64/Python 3.12.13: wheels-only install, `--reset` rebuild resolves the
> `xgcm<0.10` pin, build auto-runs the verify step, "no supported Python" guided-stop path,
> and standalone verify passes from any CWD. Not a science calculation. Cross-platform
> (Linux/Windows) testing is still a TODO.

Prepares — and verifies — an isolated, reproducible Python environment for the ECCO skills.
Every ECCO calculation/plotting/data skill depends on this having run successfully.

**This skill has two modes** (consolidated 2026-08-06 — verify was formerly a separate
`ecco-setup-verify` skill; it's now a mode here, same capability):
- **Set up** (`scripts/setup_env.py`) — survey → build `.venv` → install → auto-verify.
- **Verify** (`scripts/verify_env.py`) — health-check an *existing* environment without
  rebuilding. Runnable on its own; see [Verify mode](#verify-mode-health-check-no-rebuild).

**Design rules this skill enforces** (see `docs/design.md` → Environment & Setup):
- **venv + pip only — never conda.**
- **Never touch the global/system Python.** Everything goes in project-local `.venv/`.
- **Supported Python band: 3.11–3.12.** Floor is 3.11 (`ecco_access` requires it);
  cap is 3.12 (newest version the geospatial wheels cover). The common failure is a
  default `python3` that is *too new* (e.g. Homebrew 3.14), not too old.
- **Build once, reuse.** A healthy `.venv/` is reused, not rebuilt.
- **Teach as you go.** Explain each step in plain language for non-developers.

## When to use

**Set-up mode:**
- The user asks to set up / install the ECCO environment.
- The user asks what Python they have or whether their machine is ready (run the
  survey alone — it answers this without changing anything).
- Any other ECCO skill reports there is no working `.venv/`.

**Verify mode** (no rebuild — see [below](#verify-mode-health-check-no-rebuild)):
- The user asks "is my ECCO environment working / set up correctly?" — re-check an
  already-built env without reinstalling.
- A calculation skill throws an import/version error — verify first to rule out (or
  confirm) a broken environment before debugging the calculation.
- After anything that might have disturbed the env (a Python upgrade, manual pip changes).

## How to run it

The scripts live in this skill's `scripts/` directory. Run them with any available
Python 3 — they internally select the correct interpreter.

### Step 0 — Survey (always safe, read-only)

Run first to see the machine's Python landscape and get a verdict. This **installs
and changes nothing**:

```
python3 scripts/survey.py
```

Report the output to the user in plain language. Two outcomes:
- **Verdict: supported Python found** → proceed to setup.
- **Verdict: none found** → relay the exact install command it prints for the user's
  OS (e.g. macOS: `brew install python@3.12`), then STOP. Do not attempt setup until
  the user has installed a supported Python and the survey passes. Explain *why*
  (their `python3` is out of the 3.11–3.12 band the science libraries need).

### Step 1 — Build the environment

Once the survey verdict is positive:

```
python3 scripts/setup_env.py
```

This selects the newest supported interpreter, creates `.venv/`, upgrades pip, and
installs everything in `scripts/requirements.txt`. First run downloads a lot and can
take a few minutes — tell the user that up front so a slow step doesn't look hung.

**It automatically runs the verify step at the end** (hands off to `scripts/verify_env.py`)
— so a successful `setup_env.py` run finishes with the full verification (imports + grid
smoke test) already done. You do not need to run verify separately after setup; setup's exit
code reflects the verification result (non-zero if verify failed). This keeps one source of
verification truth (setup does not re-implement the checks — it calls the same verify script
the standalone verify mode uses).

If it reports a healthy existing `.venv/`, it reuses it (fast no-op) and still runs the
verify handoff to confirm the reused env is healthy.

To rebuild from scratch (corrupted env, or the user wants a fresh start):

```
python3 scripts/setup_env.py --reset
```

To force a specific interpreter:

```
python3 scripts/setup_env.py --interpreter python3.11
```

## Verify mode (health-check, no rebuild)

Setup runs verify automatically at the end of a build, so you don't run it separately right
after setup. Invoke verify **on its own** to re-check an *existing* environment without
reinstalling — the [Verify-mode triggers](#when-to-use) above (env-health questions, a calc
skill throwing import/version errors, a disturbed env).

```
python3 scripts/verify_env.py
```

It launches with any `python3`, then re-executes itself using the project's `.venv` python
so the checks run *inside* the environment being verified. No arguments needed.

**Scope — read this:** verify checks the **environment/toolchain only** (the `.venv`, the
libraries, the xgcm machinery). It does **not** verify any ocean-science calculation, number,
or figure — trusting a *result* is each calculation skill's own runtime validation (see
`docs/design.md` → Validation: Defense in Depth).

**What it checks:**
1. **Python version** in the supported band (3.11–3.12) **and** matching the interpreter
   `setup_env.py` recorded in `.venv/ecco_env.json`.
2. **Every required library imports** — ecco_v4_py, xgcm, xmitgcm, ecco_access, xarray,
   numpy, netCDF4, cartopy, pyresample, matplotlib, dask — reporting each resolved version.
3. **ECCO grid machinery smoke test** — calls `ecco.get_llc_grid()` on the real geometry
   file (if downloaded) and runs one `diff` (xgcm < 0.10 `boundary=`/`fill_value=` API),
   proving the grid machinery every calc skill relies on actually executes (a diff should
   stagger `i → i_g`). Skipped with a note if the geometry isn't downloaded yet (not a
   failure — the imports still prove the libraries load).

It prints a per-check ✓/✗ trail and a final verdict.

**Interpreting verify results:**
- **All ✓ / "environment OK":** the toolchain is ready — remind the user this confirmed the
  environment, not any science result.
- **No `.venv` found:** the environment isn't built — run set-up mode first, then verify.
- **An import fails:** name the specific package and error; usual fix is
  `setup_env.py --reset` (rebuild). Never dump a raw traceback without the plain-language
  "which package, what to do" summary.
- **Version mismatch with recorded state:** the venv may be stale (e.g. Python changed);
  suggest a `--reset` rebuild.

## Interpreting results for the user

- Always relay the survey's verdict line and the chosen interpreter.
- On success, tell the user: the sandbox is at `.venv/`, which Python version it uses,
  that their system Python was not modified, and that they can delete `.venv/` anytime
  to remove everything.
- On failure, give the *specific next action* (the install command, or which package
  failed), never a raw traceback with no guidance.

## What this skill does NOT do

- It does not modify the user's PATH, shell config, or global Python.
- It does not set up Earthdata/PO.DAAC download credentials — that is a separate
  prerequisite for data access (see `docs/design.md` → Data Access Pattern).
- It does not activate the venv in the user's shell; ECCO skills invoke the `.venv`
  python directly.

## Files

- `scripts/survey.py` — read-only Python-landscape diagnostic (step 0).
- `scripts/setup_env.py` — builds/reuses `.venv`, installs deps, records state, runs verify.
- `scripts/verify_env.py` — the verify step / standalone verify mode (launcher + in-venv
  imports, versions, xgcm grid smoke test). Called by `setup_env.py` and runnable on its own.
- `scripts/requirements.txt` — the dependency list. Uses tested `>=` floors plus one
  hard ceiling: **`xgcm<0.10`** (ecco_v4_py's `get_llc_grid` crashes on 0.10+). An
  exact `pip freeze` lockfile is still a TODO; see design doc.
