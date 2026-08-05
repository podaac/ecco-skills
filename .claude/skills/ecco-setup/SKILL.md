---
name: ecco-setup
description: Set up the Python environment for ECCO ocean-data skills. Use this BEFORE any ECCO calculation, plotting, or data-access skill runs — it surveys the machine's Python, builds an isolated project-local venv (3.11-3.12, pip only, no conda), installs the scientific stack, and reports readiness. (Verifying that the built environment works is the separate ecco-setup-verify skill.) Triggers when the user wants to "set up ECCO", "install the ECCO environment", asks "which Python do I have", or when another ECCO skill finds no working .venv.
---

# ecco-setup

> **🔬 Verification status (per `docs/verify.md`): ✅ verified (infrastructure).** Tested
> on macOS/arm64/Python 3.12.13: wheels-only install, `--reset` rebuild resolves the
> `xgcm<0.10` pin, auto-handoff to verify, "no supported Python" guided-stop path. Not a
> science calculation. Cross-platform (Linux/Windows) testing is still a TODO.

Prepares an isolated, reproducible Python environment for the ECCO skills. Every
ECCO calculation/plotting/data skill depends on this having run successfully.

**Design rules this skill enforces** (see `docs/design.md` → Environment & Setup):
- **venv + pip only — never conda.**
- **Never touch the global/system Python.** Everything goes in project-local `.venv/`.
- **Supported Python band: 3.11–3.12.** Floor is 3.11 (`ecco_access` requires it);
  cap is 3.12 (newest version the geospatial wheels cover). The common failure is a
  default `python3` that is *too new* (e.g. Homebrew 3.14), not too old.
- **Build once, reuse.** A healthy `.venv/` is reused, not rebuilt.
- **Teach as you go.** Explain each step in plain language for non-developers.

## When to use

- The user asks to set up / install the ECCO environment.
- The user asks what Python they have or whether their machine is ready (run the
  survey alone — it answers this without changing anything).
- Any other ECCO skill reports there is no working `.venv/`.

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

**It automatically hands off to `ecco-setup-verify` at the end** — so a successful
`setup_env.py` run finishes with the full verification (imports + grid smoke test)
already done. You do not need to run verify separately after setup; setup's exit code
reflects the verification result (non-zero if verify failed). This keeps one source of
verification truth (setup does not re-implement the checks).

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

### Step 2 — Verify (automatic)

Setup hands off to `ecco-setup-verify` automatically at the end, so verification
already ran as part of Step 1. You only invoke `ecco-setup-verify` *separately* when
you want to re-check an environment later without reinstalling (e.g. "is my env still
OK?", or as the first diagnostic when a calculation skill errors). It checks the
*environment* only, not any calculation result.

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
- `scripts/setup_env.py` — builds/reuses `.venv`, installs deps, records state.
- `scripts/requirements.txt` — the dependency list. Uses tested `>=` floors plus one
  hard ceiling: **`xgcm<0.10`** (ecco_v4_py's `get_llc_grid` crashes on 0.10+). An
  exact `pip freeze` lockfile is still a TODO; see design doc.
