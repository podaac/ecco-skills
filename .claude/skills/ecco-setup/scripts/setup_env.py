#!/usr/bin/env python3
"""
ecco-setup: build the project-local virtual environment (steps 1-8).

Creates .venv/ using a supported interpreter (3.11-3.12), installs the pinned
dependencies with pip, and records what it built so later runs reuse it.

This is intended to be launched by any Python 3 (e.g. `python3 setup_env.py`);
it re-invokes the CORRECT interpreter internally. It will NOT touch the global
Python — everything goes into ./.venv.

INTERPRETER POLICY (which python runs what):
  * System `python3` is used ONLY before the venv exists — i.e. to run this script
    and survey.py, and to create the venv (`<python3.x> -m venv .venv`).
  * `.venv/bin/python` (`.venv/Scripts/python.exe` on Windows) is used for EVERYTHING
    that needs the ECCO libraries: pip install, the verify handoff, and every
    calculation skill thereafter.
  This keeps a single, reproducible interpreter for all real work.

Flags:
  --reset   delete an existing .venv and rebuild from scratch
  --interpreter <cmd>   force a specific interpreter (e.g. python3.11); otherwise
                        auto-picks newest supported from the survey order

Exit codes: 0 success, non-zero on any failure (with a plain-language reason).
"""

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# Project root derived from THIS FILE, not CWD, so setup targets the real project .venv
# regardless of where it's launched. File: <root>/.claude/skills/ecco-setup/scripts/setup_env.py
# -> root is four parents up from HERE (scripts -> ecco-setup -> skills -> .claude -> root).
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv")
REQUIREMENTS = os.path.join(HERE, "requirements.txt")
STATE_FILE = os.path.join(VENV_DIR, "ecco_env.json")
# The verify script is a sibling in this skill's own scripts/ dir; setup hands off to it so
# there is ONE source of verification truth (setup never re-implements the checks itself).
# It's also runnable standalone (verify mode) — see the SKILL.md. Consolidated into this
# skill 2026-08-06 (was formerly the separate ecco-setup-verify skill).
VERIFY_SCRIPT = os.path.normpath(os.path.join(HERE, "verify_env.py"))

PREFERRED_ORDER = ["3.12", "3.11"]
FLOOR = (3, 11)
CAP = (3, 12)


def log(msg):
    print(msg, flush=True)


def probe_version(cmd_args):
    try:
        out = subprocess.run(cmd_args + ["--version"], capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    raw = (out.stdout + out.stderr).strip()
    for token in raw.split():
        parts = token.split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return (int(parts[0]), int(parts[1]))
    return None


def in_band(ver):
    return ver is not None and FLOOR <= ver <= CAP


def find_interpreter(forced=None):
    """Return the command args for a supported interpreter, or None."""
    if forced:
        ver = probe_version([forced])
        if in_band(ver):
            return [forced]
        log(f"  ✗ forced interpreter '{forced}' is {ver} — not in supported band "
            f"{FLOOR[0]}.{FLOOR[1]}-{CAP[0]}.{CAP[1]}")
        return None
    for v in PREFERRED_ORDER:  # newest-first
        cmd = [f"python{v}"]
        if in_band(probe_version(cmd)):
            return cmd
        if platform.system() == "Windows":
            wcmd = ["py", f"-{v}"]
            if in_band(probe_version(wcmd)):
                return wcmd
    # last resort: bare python3 if it happens to be in band
    if in_band(probe_version(["python3"])):
        return ["python3"]
    return None


def venv_python_path():
    """Path to the python executable inside .venv (cross-platform)."""
    if platform.system() == "Windows":
        return os.path.join(VENV_DIR, "Scripts", "python.exe")
    return os.path.join(VENV_DIR, "bin", "python")


def venv_is_healthy():
    py = venv_python_path()
    if not os.path.exists(py):
        return False
    ver = probe_version([py])
    return in_band(ver)


def install_hint():
    system = platform.system()
    if system == "Darwin":
        return "brew install python@3.12   (then re-run setup)"
    if system == "Windows":
        return "winget install Python.Python.3.12   (or python.org installer)"
    return "sudo apt install python3.12 python3.12-venv   (or use pyenv)"


def run_verify():
    """Hand off to the verify script (verify_env.py, in this skill's scripts/ dir) so there
    is one source of verification truth. Returns the verify script's exit code, or None if
    the verify script can't be found (setup still succeeded; just report that)."""
    if not os.path.exists(VERIFY_SCRIPT):
        log("")
        log("[!] Could not locate verify_env.py at:")
        log(f"    {VERIFY_SCRIPT}")
        log("    Setup finished, but run ecco-setup in verify mode manually to "
            "confirm the environment.")
        return None
    log("")
    log("Verifying the environment works (imports + real grid smoke test) ...")
    log("-" * 64)
    # Interpreter policy: the venv now exists, so run verify with the VENV python
    # (.venv/bin/python), NOT the system python3 that launched setup. We set
    # ECCO_VERIFY_INNER=1 so verify's launcher knows it is already inside the venv
    # and does not need to re-exec itself.
    vpy = venv_python_path()
    env = dict(os.environ, ECCO_VERIFY_INNER="1")
    try:
        result = subprocess.run([vpy, VERIFY_SCRIPT], env=env)
        return result.returncode
    except OSError as e:
        log(f"[!] Could not launch verify: {e}. Run ecco-setup in verify mode "
            "manually.")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true",
                        help="delete existing .venv and rebuild")
    parser.add_argument("--interpreter", default=None,
                        help="force a specific interpreter command")
    args = parser.parse_args()

    log("=" * 64)
    log("ECCO skills — environment setup")
    log("=" * 64)

    # --- reset ---
    if args.reset and os.path.isdir(VENV_DIR):
        log(f"Reset requested — removing {VENV_DIR}")
        shutil.rmtree(VENV_DIR)

    # --- step 1: reuse healthy existing venv ---
    if not args.reset and venv_is_healthy():
        py = venv_python_path()
        ver = probe_version([py])
        log(f"✓ Existing healthy environment found: .venv (Python {ver[0]}.{ver[1]})")
        log("  Reusing it. (Use --reset to rebuild from scratch.)")
        # Confirm it still works by handing off to verify.
        rc = run_verify()
        if rc == 0:
            log("")
            log("✓ Environment present and verified — ready to run ECCO skills.")
        elif rc is not None:
            log("")
            log("✗ Existing environment FAILED verification (see above). Try --reset.")
        return rc if rc is not None else 0

    # --- step 2-3: discover + gate interpreter ---
    log("Selecting a supported Python interpreter (3.11-3.12, newest first)...")
    interp = find_interpreter(args.interpreter)
    if interp is None:
        log("✗ No supported Python (3.11 or 3.12) found.")
        log("")
        log("Do this next:")
        log("  " + install_hint())
        log("")
        log("Then re-run setup. (Run survey.py first if you want the full picture.)")
        return 1
    iver = probe_version(interp)
    log(f"✓ Using {' '.join(interp)} (Python {iver[0]}.{iver[1]})")

    # --- step 4: create venv ---
    log(f"Creating virtual environment at {VENV_DIR} ...")
    log("  (a self-contained sandbox for this project's tools — your system Python "
        "is untouched, and you can delete .venv anytime)")
    try:
        subprocess.run(interp + ["-m", "venv", VENV_DIR], check=True)
    except subprocess.CalledProcessError:
        log("✗ Failed to create the virtual environment.")
        log("  If the interpreter lacks venv, install it "
            "(e.g. Linux: sudo apt install python3.12-venv).")
        return 1

    vpy = venv_python_path()

    # --- step 4b: upgrade pip inside the venv ---
    log("Upgrading pip inside the sandbox ...")
    subprocess.run([vpy, "-m", "pip", "install", "--upgrade", "pip"], check=False)

    # --- step 5: install dependencies ---
    log("Installing ECCO dependencies (this can take a few minutes on first run) ...")
    log(f"  requirements: {REQUIREMENTS}")
    result = subprocess.run(
        [vpy, "-m", "pip", "install", "-r", REQUIREMENTS]
    )
    if result.returncode != 0:
        log("")
        log("✗ Dependency installation failed.")
        log("  Common cause: a package tried to build from source (no matching wheel).")
        log("  Check the pip output above for the failing package. If it's a geospatial")
        log("  package on an unusual platform/Python, try Python 3.12 specifically:")
        log("     python3.12 setup_env.py --reset --interpreter python3.12")
        return 1

    # --- step 7: record what we built ---
    state = {
        "python_version": f"{iver[0]}.{iver[1]}",
        "interpreter_cmd": " ".join(interp),
        "venv_python": vpy,
        "platform": f"{platform.system()} {platform.machine()}",
    }
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except OSError:
        pass  # non-fatal

    # --- step 8: report ---
    log("")
    log("=" * 64)
    log("✓ Install complete.")
    log(f"  Sandbox:     {VENV_DIR}")
    log(f"  Python:      {iver[0]}.{iver[1]}  ({' '.join(interp)})")
    log(f"  venv python: {vpy}")
    log("  Skills will use the .venv python directly — no manual 'activate' needed.")
    log("=" * 64)

    # --- step 9: hand off to verify (one source of verification truth) ---
    rc = run_verify()
    if rc is None:
        return 0          # install succeeded; verify couldn't be located/launched
    if rc == 0:
        log("")
        log("✓ Setup complete and verified — ready to run ECCO calculation skills.")
    else:
        log("")
        log("✗ Install finished but verification FAILED (see above). The environment "
            "is not ready; address the reported problem or try --reset.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
