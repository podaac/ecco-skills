#!/usr/bin/env python3
"""
load-grid: download (if needed) and open the ECCO LLC90 geometry, and build the
xgcm grid object. Thin CLI wrapper around ecco_common.load_grid so the skill is
runnable standalone; calculation skills import ecco_common.load_grid directly
instead of shelling out to this.

Run with the venv python:  .venv/bin/python run.py
"""
import os
import sys

# Put the shared ecco_common package on the path (sibling skill dir).
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "ecco-common"))
import ecco_preflight  # noqa: E402
ecco_preflight.ensure_env("load-grid")  # clear msg if env is unhealthy
from ecco_common import load_grid  # noqa: E402


def main():
    print("=" * 60)
    print("load-grid — ECCO LLC90 geometry")
    print("=" * 60)
    ds_grid, grid = load_grid()
    # Quick, honest summary of what a caller now has available.
    key_metrics = [v for v in ["XC", "YC", "rA", "drF", "dxG", "dyG",
                               "hFacC", "hFacW", "hFacS", "maskC", "CS", "SN"]
                   if v in ds_grid]
    print(f"  tiles×j×i: {ds_grid.sizes.get('tile')}×{ds_grid.sizes.get('j')}"
          f"×{ds_grid.sizes.get('i')}, {ds_grid.sizes.get('k')} depth levels")
    print(f"  grid metrics available: {', '.join(key_metrics)}")
    print("  xgcm grid object: ready (ecco.get_llc_grid)")
    print("✓ grid loaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
