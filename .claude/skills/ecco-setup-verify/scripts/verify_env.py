#!/usr/bin/env python3
"""
ecco-setup-verify: prove the ECCO *environment* actually works.

Scope: the .venv toolchain ONLY. This does NOT verify any oceanographic
calculation or result — that is each calculation skill's own runtime validation.

This is a two-stage script:
  Stage A (launcher): finds the project .venv and re-executes itself with the
     venv's python, so the checks run inside the environment we're verifying.
  Stage B (checks):   runs inside the venv — imports libraries, reports versions,
     and runs the real ecco.get_llc_grid smoke test (xgcm < 0.10 API).

INTERPRETER POLICY: the actual checks ALWAYS run under `.venv/bin/python`. When you
run this standalone with a system `python3`, Stage A bootstraps and immediately
re-execs itself with the venv python. When `ecco-setup` calls it, setup already
launches it with the venv python and sets ECCO_VERIFY_INNER=1 to skip the re-exec.
Either way, imports/versions/grid checks execute in the venv — never system python3.

Run standalone with any python3:  python3 verify_env.py
Exit codes: 0 all checks passed, 1 something failed (with a plain-language reason).
"""

import json
import os
import platform
import subprocess
import sys

# Project root derived from THIS FILE's location, not CWD, so verify works no matter
# where it's launched from. File: <root>/.claude/skills/ecco-setup-verify/scripts/verify_env.py
# -> root is four parents up from this file's dir (scripts -> ecco-setup-verify ->
#    skills -> .claude -> root).
_HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv")
STATE_FILE = os.path.join(VENV_DIR, "ecco_env.json")

# Libraries that must import for the environment to be usable.
REQUIRED_LIBS = [
    "ecco_v4_py", "xgcm", "xmitgcm", "ecco_access",
    "xarray", "numpy", "netCDF4", "cartopy", "pyresample", "matplotlib", "dask",
]

FLOOR = (3, 11)
CAP = (3, 12)


def venv_python_path():
    """Path to the python inside .venv (cross-platform)."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


# --------------------------------------------------------------------------
# Stage B: the actual checks (run inside the venv).
# --------------------------------------------------------------------------
def run_checks():
    import importlib
    import importlib.metadata as md

    passed = True
    print("=" * 64)
    print("ECCO environment verification (checks running inside .venv)")
    print("=" * 64)

    # --- Check 1: Python version in band, and matches what setup recorded ---
    v = sys.version_info
    in_band = FLOOR <= (v.major, v.minor) <= CAP
    mark = "✓" if in_band else "✗"
    print(f"[{mark}] Python {v.major}.{v.minor}.{v.micro} "
          f"(supported band {FLOOR[0]}.{FLOOR[1]}-{CAP[0]}.{CAP[1]})")
    if not in_band:
        passed = False

    recorded = None
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                recorded = json.load(f)
        except (OSError, ValueError):
            recorded = None
    if recorded:
        want = recorded.get("python_version")
        got = f"{v.major}.{v.minor}"
        if want and want != got:
            print(f"[✗] venv python ({got}) does not match what ecco-setup "
                  f"recorded ({want}) — env may be stale; consider --reset.")
            passed = False
        else:
            print(f"[✓] Matches ecco-setup's recorded interpreter ({want}).")
    else:
        print("[!] No ecco_env.json state file found — was this venv built by ecco-setup?")

    # --- Check 2: every required library imports ---
    print("-" * 64)
    print("Imports + versions:")
    for lib in REQUIRED_LIBS:
        try:
            importlib.import_module(lib)
            try:
                ver = md.version(lib)
            except md.PackageNotFoundError:
                ver = "(version unknown)"
            print(f"  [✓] {lib:<12} {ver}")
        except Exception as e:  # noqa: BLE001 - report any import failure plainly
            print(f"  [✗] {lib:<12} FAILED: {type(e).__name__}: {e}")
            passed = False

    # --- Check 3: the REAL grid machinery — ecco.get_llc_grid + a diff ---
    # This is the exact call every Level 1 grid skill relies on, and the one that
    # breaks under xgcm >= 0.10. Testing it here is the honest environment check.
    # It needs the geometry file; if that isn't downloaded yet we say so (not a
    # failure — env can still be fine), but if it IS present the test is definitive.
    print("-" * 64)
    print("ECCO grid machinery smoke test (ecco.get_llc_grid + diff):")
    # Look for the geometry file in the PROJECT cache (./data/ecco), where load-grid
    # puts it — not ~/Downloads. Resolve the path via ecco_common.cache so it honors
    # ECCO_DATA_DIR and the project-root anchoring. Fall back to the legacy ~/Downloads
    # copy only if the project cache doesn't have it.
    geom_fn = "GRID_GEOMETRY_ECCO_V4r4_native_llc0090.nc"
    geom = None
    try:
        sys.path.insert(0, os.path.join(PROJECT_ROOT, ".claude", "skills", "ecco-common"))
        from ecco_common import cache as _cache
        cand = _cache.cached_path("ECCO_L4_GEOMETRY_LLC0090GRID_V4R4", geom_fn)
        if os.path.exists(cand):
            geom = cand
    except Exception:
        pass
    if geom is None:
        legacy = os.path.join(os.path.expanduser("~"), "Downloads", "ECCO_V4r4_PODAAC",
                              "ECCO_L4_GEOMETRY_LLC0090GRID_V4R4", geom_fn)
        geom = legacy if os.path.exists(legacy) else cand
    if not os.path.exists(geom):
        print("  [!] geometry file not downloaded yet — skipping the full grid test.")
        print("      (Imports above already prove the libraries load. Download the")
        print("       geometry via the load-grid skill to enable this definitive check.)")
    else:
        try:
            import ecco_v4_py as ecco
            import xarray as xr

            ds_grid = xr.open_dataset(geom)
            xgcm_grid = ecco.get_llc_grid(ds_grid)      # crashes under xgcm >= 0.10
            d = xgcm_grid.diff(ds_grid["Depth"], "X",
                               boundary="fill", fill_value=0.0)
            # tracer point (i) should become U-point (i_g) after an X diff
            if "i_g" in d.dims and "tile" in d.dims:
                print(f"  [✓] get_llc_grid OK; diff staggered i→i_g, dims {dict(d.sizes)}")
            else:
                print(f"  [✗] diff produced unexpected dims {dict(d.sizes)}")
                passed = False
        except Exception as e:  # noqa: BLE001
            print(f"  [✗] grid machinery FAILED: {type(e).__name__}: {e}")
            print("      Most likely an xgcm/ecco_v4_py version mismatch "
                  "(need xgcm < 0.10). Rebuild with ecco-setup --reset.")
            passed = False

    # --- Verdict ---
    print("=" * 64)
    if passed:
        print("VERDICT: environment OK ✓  — ready to run ECCO calculation skills.")
        print("(Note: this verified the toolchain only, not any science result.)")
        return 0
    print("VERDICT: environment has problems ✗")
    print("Try:  python3 <ecco-setup>/scripts/setup_env.py --reset")
    print("(run the ecco-setup skill) to rebuild, then verify again.")
    return 1


# --------------------------------------------------------------------------
# Stage A: launcher — ensure we're running inside the venv, else re-exec.
# --------------------------------------------------------------------------
def main():
    if os.environ.get("ECCO_VERIFY_INNER") == "1":
        return run_checks()

    vpy = venv_python_path()
    if not os.path.exists(vpy):
        print("=" * 64)
        print("ECCO environment verification")
        print("=" * 64)
        print(f"[✗] No environment found at {VENV_DIR}")
        print("    The ECCO sandbox has not been built yet.")
        print("    → Run the `ecco-setup` skill first, then verify.")
        return 1

    # Re-execute this script using the venv's python so imports are tested there.
    env = dict(os.environ, ECCO_VERIFY_INNER="1")
    try:
        result = subprocess.run([vpy, os.path.abspath(__file__)], env=env)
        return result.returncode
    except OSError as e:
        print(f"[✗] Could not launch the venv python at {vpy}: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
