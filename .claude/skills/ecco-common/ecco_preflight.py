"""
ecco_preflight — a tiny, STDLIB-ONLY environment guard for ECCO skill scripts.

Why this is a standalone module, NOT part of the `ecco_common` package: importing
`ecco_common` eagerly pulls in xarray / ecco_v4_py (via `ecco_common.loaders`), so if the
environment is broken that import is exactly what blows up — with a raw traceback, before
any check can run. This module imports nothing heavy, so a skill can call `ensure_env()`
*before* `from ecco_common import ...` and turn a cryptic ImportError into a clear,
actionable message.

Usage (at the top of a skill's run.py, right after the sys.path insert that adds the
`ecco-common` dir, and BEFORE importing ecco_common):

    import ecco_preflight
    ecco_preflight.ensure_env("compute-ocean-heat-content")
    from ecco_common import load_grid, load_field

SCOPE: this checks that the venv's *libraries* import — the "environment present but
unhealthy" failure mode. It deliberately does NOT import `ecco_common` itself, so it never
masks a real bug in our own code — only a broken toolchain.

The *missing-venv* failure mode (`.venv/bin/python` absent, so the script never starts) is
handled a layer up: skills are launched with the venv python, and if it's gone you get a
shell "no such file or directory" — the documented response is to run `ecco-setup` (verify
mode confirms; a rebuild fixes). See design.md → Environment & Setup.
"""

import importlib
import sys

# The libraries a calculation/plot skill needs to import. If any of these fail, the venv is
# present but unhealthy (partial install, ABI mismatch, a Python upgrade that orphaned it).
CRITICAL_LIBS = ["numpy", "xarray", "netCDF4", "xgcm", "ecco_v4_py"]


def _check_imports(libs):
    """Try to import each name. Returns (ok, missing) where missing is a list of
    (lib, short_error) for the ones that failed. Stdlib-only; unit-testable without a
    broken venv (pass a bogus name to see it reported)."""
    missing = []
    for lib in libs:
        try:
            importlib.import_module(lib)
        except Exception as e:  # noqa: BLE001 — any import failure means "unhealthy"
            missing.append((lib, f"{type(e).__name__}: {e}"))
    return (not missing), missing


def ensure_env(skill="", libs=None, exit_on_fail=True):
    """Guard entry point: verify the ECCO libraries import before the skill proceeds.

    On success: returns True (silently).
    On failure: prints a clear, actionable message (which lib failed + what to run) and,
    by default, sys.exit(1) so the skill stops with a non-zero code instead of a raw
    traceback deep in a downstream import. Pass exit_on_fail=False to get the bool back
    instead (used by the test).
    """
    libs = libs if libs is not None else CRITICAL_LIBS
    ok, missing = _check_imports(libs)
    if ok:
        return True

    who = f" ({skill})" if skill else ""
    print("=" * 64, file=sys.stderr)
    print(f"[✗] ECCO environment problem{who}: the .venv exists but some libraries "
          "won't import.", file=sys.stderr)
    for lib, err in missing:
        print(f"      - {lib}: {err}", file=sys.stderr)
    print("", file=sys.stderr)
    print("  This means the environment is present but unhealthy (a partial install, an", file=sys.stderr)
    print("  ABI mismatch, or a Python change that orphaned the venv).", file=sys.stderr)
    print("  → Fix it with the ecco-setup skill:", file=sys.stderr)
    print("      python3 .claude/skills/ecco-setup/scripts/verify_env.py   # confirm the diagnosis", file=sys.stderr)
    print("      python3 .claude/skills/ecco-setup/scripts/setup_env.py --reset   # rebuild", file=sys.stderr)
    print("=" * 64, file=sys.stderr)
    if exit_on_fail:
        sys.exit(1)
    return False
