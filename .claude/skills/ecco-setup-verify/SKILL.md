---
name: ecco-setup-verify
description: Verify that the ECCO Python ENVIRONMENT (the project .venv built by ecco-setup) actually works — checks the Python version, imports every required library, reports versions, and runs a tiny xgcm grid smoke test. This checks the toolchain ONLY; it does NOT verify any oceanographic calculation or result. Use after ecco-setup, or anytime a user wants to confirm the environment is healthy, or when a calculation skill errors and you need to rule out a broken environment.
---

# ecco-setup-verify

> **🔬 Verification status (per `docs/verify.md`): ✅ verified (infrastructure).** This
> skill *is* the environment-verification tool; it exercises the **official
> `ecco.get_llc_grid`** on the real geometry as its smoke test, and passes from any CWD.
> Not a science calculation.

Confirms the ECCO environment is healthy: "installed" is not the same as "working."
A `pip install` can report success while a compiled library fails to import, or an
API mismatch lurks — this skill catches that before a calculation skill hits it.

**Scope — read this:** this verifies the **environment/toolchain only** (the `.venv`,
the libraries, the xgcm machinery). It does **not** verify any ocean-science
calculation, number, or figure. Trusting a *result* is the job of each calculation
skill's own runtime validation (see `docs/design.md` → Validation: Defense in Depth).
The name is `ecco-setup-verify` — not `ecco-verify` — precisely to avoid that confusion.

## When to use

`ecco-setup` already invokes this automatically at the end of a build, so you don't
run it as a separate step right after setup. Invoke it **on its own** when:

- A user asks "is my ECCO environment working / set up correctly?" (re-check an
  already-built env without reinstalling).
- A calculation skill throws an import/version error — run this first to rule out (or
  confirm) a broken environment before debugging the calculation.
- After anything that might have disturbed the env (a Python upgrade, manual pip
  changes, etc.).

## How to run it

```
python3 scripts/verify_env.py
```

It launches with any `python3`, then re-executes itself using the project's `.venv`
python so the checks run *inside* the environment being verified. No arguments needed.

## What it checks

1. **Python version** is in the supported band (3.11–3.12) **and** matches the
   interpreter `ecco-setup` recorded in `.venv/ecco_env.json`.
2. **Every required library imports** — ecco_v4_py, xgcm, xmitgcm, ecco_access,
   xarray, numpy, netCDF4, cartopy, pyresample, matplotlib, dask — reporting each
   resolved version.
3. **ECCO grid machinery smoke test** — calls `ecco.get_llc_grid()` on the real
   geometry file (if downloaded) and runs one `diff`, using the **xgcm < 0.10 API**
   (`boundary=`/`fill_value=`; this is what `ecco_v4_py` and the tutorials expect, and
   we pin `xgcm<0.10` because ecco_v4_py's `get_llc_grid` crashes on 0.10+). Proves the
   real grid machinery every calculation skill relies on actually executes — a diff
   should stagger a tracer field from `i` to `i_g`. If the geometry file isn't
   downloaded yet, this check is skipped with a note (not a failure — the imports above
   still prove the libraries load).

It prints a per-check ✓/✗ trail and a final verdict.

## Interpreting results for the user

- **All ✓ / "environment OK":** relay that the toolchain is ready, and remind them
  this confirmed the environment, not any science result.
- **No `.venv` found:** the environment isn't built — direct them to run `ecco-setup`
  first, then verify again.
- **An import fails:** name the specific package and error; the usual fix is
  `ecco-setup` with `--reset` (rebuild). Don't dump a raw traceback without the
  plain-language "which package, what to do" summary.
- **Version mismatch with recorded state:** the venv may be stale (e.g. Python
  changed); suggest an `ecco-setup --reset` rebuild.

## Files

- `scripts/verify_env.py` — the launcher + in-venv checks (imports, versions, xgcm
  smoke test).

## Relationship to other verification (see design doc)

- This skill = **environment verification**.
- **Runtime validation** (6 layers) = each calculation skill checking its own answer.
- **Acceptance testing** = how we confirm a calculation skill is correctly implemented
  before shipping. These are separate; this skill is only the first.
