#!/usr/bin/env python3
"""
ecco-setup: read-only Python-landscape survey (step 0).

Inspects what Python interpreters exist on this machine and prints a plain-language
verdict on whether a supported one (3.11-3.12) is available for the ECCO skills venv.

READ-ONLY: this script installs nothing, creates no venv, and modifies no files.
It only runs `--version` style probes and inspects paths.

Exit codes:
  0  a supported interpreter (3.11 or 3.12) was found
  1  no supported interpreter found (user must install one)

Run with any Python 3 (even an out-of-band one) — it only uses the stdlib.
"""

import os
import shutil
import subprocess
import sys
import platform

# Supported band for the ECCO skills environment.
# Floor is 3.11 (ecco_access 0.3.1 requires >=3.11); cap is 3.12 (newest cp-tag the
# geospatial wheels — cartopy/netCDF4/pyresample — publish at design time).
# Probed newest-first so the user gets the most current supported runtime.
PREFERRED_ORDER = ["3.12", "3.11"]
FLOOR = (3, 11)
CAP = (3, 12)


def _probe_version(cmd_args):
    """Run `<cmd> --version` and return (major, minor, raw_string) or None."""
    try:
        out = subprocess.run(
            cmd_args + ["--version"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    raw = (out.stdout + out.stderr).strip()
    # Expect "Python 3.12.5"
    for token in raw.split():
        parts = token.split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return (int(parts[0]), int(parts[1]), raw)
    return None


def _resolve_path(cmd):
    """Absolute, symlink-resolved path of a command, or None."""
    p = shutil.which(cmd)
    if not p:
        return None
    try:
        return os.path.realpath(p)
    except OSError:
        return p


def _in_band(ver):
    return ver is not None and FLOOR <= (ver[0], ver[1]) <= CAP


def _band_label(ver):
    if ver is None:
        return "not found"
    mm = (ver[0], ver[1])
    if mm < FLOOR:
        return f"{ver[0]}.{ver[1]} — too old (below {FLOOR[0]}.{FLOOR[1]} floor)"
    if mm > CAP:
        return f"{ver[0]}.{ver[1]} — too new (above {CAP[0]}.{CAP[1]} cap; no wheels yet)"
    return f"{ver[0]}.{ver[1]} — supported ✓"


def _install_hint():
    system = platform.system()
    if system == "Darwin":
        return ("macOS: install a supported Python, e.g.\n"
                "    brew install python@3.12\n"
                "  (then re-run setup; this leaves your default python3 untouched)")
    if system == "Windows":
        return ("Windows: install from https://www.python.org/downloads/ (choose 3.12),\n"
                "  or:  winget install Python.Python.3.12\n"
                "  then use the `py -3.12` launcher.")
    return ("Linux: use your distro package (e.g. `sudo apt install python3.12 python3.12-venv`)\n"
            "  or pyenv (https://github.com/pyenv/pyenv), then re-run setup.")


def main():
    print("=" * 64)
    print("ECCO skills — Python environment survey (read-only)")
    print("=" * 64)
    print(f"Platform: {platform.system()} {platform.machine()}")
    print()

    # 1. The default `python3` and its real location.
    default_ver = _probe_version(["python3"])
    default_path = _resolve_path("python3")
    print("Default `python3`:")
    if default_ver:
        origin = ""
        if default_path and "homebrew" in default_path.lower():
            origin = "  (Homebrew)"
        elif default_path and "/usr/bin" in default_path:
            origin = "  (Apple/system)"
        print(f"  version → {default_ver[2]}{origin}")
        print(f"  path    → {default_path}")
        print(f"  status  → {_band_label(default_ver)}")
    else:
        print("  not found on PATH")
    print()

    # 2. Version-suffixed interpreters, newest-first.
    print("Version-specific interpreters (what setup will actually use):")
    found = {}  # "3.12" -> (cmd_args, ver)
    for v in PREFERRED_ORDER:
        cmd = f"python{v}"
        ver = _probe_version([cmd])
        if ver:
            found[v] = ([cmd], ver)
            print(f"  {cmd:<12} → {ver[2]}   {_band_label(ver)}")
        else:
            # Windows py-launcher fallback
            py_ver = _probe_version(["py", f"-{v}"]) if platform.system() == "Windows" else None
            if py_ver:
                found[v] = (["py", f"-{v}"], py_ver)
                print(f"  py -{v:<8} → {py_ver[2]}   {_band_label(py_ver)}")
            else:
                print(f"  python{v:<6} → not found")
    print()

    # 3. macOS-specific notes (Apple stub).
    if platform.system() == "Darwin":
        apple = "/usr/bin/python3"
        if os.path.exists(apple):
            aver = _probe_version([apple])
            note = f"{aver[2]}" if aver else "present (may prompt to install Command Line Tools)"
            print(f"Note: Apple's {apple} → {note}")
            print("      (Apple's Python is for system tooling; typically 3.9 — below our floor.)")
            print()

    # 4. venv availability.
    venv_ok = False
    try:
        import venv  # noqa: F401
        venv_ok = True
    except ImportError:
        pass
    print(f"venv module available in the interpreter running this survey: "
          f"{'yes ✓' if venv_ok else 'NO ✗'}")
    print()

    # 5. Existing project venv? (project root from THIS file, not CWD:
    #    <root>/.claude/skills/ecco-setup/scripts/survey.py -> 4 parents up)
    _here = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(_here, "..", "..", "..", ".."))
    existing = os.path.join(project_root, ".venv")
    if os.path.isdir(existing):
        print(f"Existing project environment: {existing} (setup will reuse if healthy)")
        print()

    # ---- Verdict ----
    print("-" * 64)
    chosen = None
    for v in PREFERRED_ORDER:  # newest-first
        if v in found and _in_band(found[v][1]):
            chosen = (v, found[v])
            break

    if chosen:
        v, (cmd_args, ver) = chosen
        print(f"VERDICT: supported Python found → {' '.join(cmd_args)} ({ver[2]})")
        print("         Ready to build the sandbox (.venv).")
        print(f"CHOSEN_INTERPRETER={' '.join(cmd_args)}")
        return 0

    print("VERDICT: no supported Python (3.11-3.12) found.")
    print()
    print("Do this next:")
    print("  " + _install_hint().replace("\n", "\n  "))
    return 1


if __name__ == "__main__":
    sys.exit(main())
