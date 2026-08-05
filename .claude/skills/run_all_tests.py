#!/usr/bin/env python3
"""
Run all ECCO skill test suites and report a combined result. Offline — no network,
no NASA credentials. Intended as the project's single test entry point (and the basis
for a future CI step).

Run with the venv python:
    .venv/bin/python .claude/skills/run_all_tests.py

Exit 0 iff every suite passes.
"""
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# Each suite is a standalone script that exits non-zero on failure.
SUITES = [
    ("ecco_common (loader/cache/access)",
     os.path.join(_HERE, "ecco-common", "tests", "test_ecco_common.py")),
    ("compute-ocean-heat-content (validation guards)",
     os.path.join(_HERE, "compute-ocean-heat-content", "scripts", "test_validation.py")),
    ("compute-geostrophic-balance (Rung-1 match + guards)",
     os.path.join(_HERE, "compute-geostrophic-balance", "scripts", "test_geostrophic.py")),
]


def main():
    py = sys.executable  # the venv python running this
    results = []
    for name, path in SUITES:
        print("\n" + "#" * 70)
        print(f"# {name}")
        print("#" * 70)
        rc = subprocess.run([py, path]).returncode
        results.append((name, rc))

    print("\n" + "=" * 70)
    print("COMBINED TEST SUMMARY")
    print("=" * 70)
    all_ok = True
    for name, rc in results:
        print(f"  {'PASS' if rc == 0 else 'FAIL'}  {name}")
        all_ok = all_ok and (rc == 0)
    print("=" * 70)
    print("ALL SUITES PASS ✓" if all_ok else "SOME SUITES FAILED ✗")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
