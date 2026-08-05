#!/usr/bin/env python3
"""
load-field: download (if needed) and open an ECCO science-field collection for a
chosen month (or months). Thin CLI wrapper around ecco_common.load_field; calculation
skills import ecco_common.load_field directly instead of shelling out.

Run with the venv python, e.g.:
  .venv/bin/python run.py ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4 2000-01
  .venv/bin/python run.py ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4 2000-01 2000-02
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "ecco-common"))
from ecco_common import load_field  # noqa: E402


def main(argv):
    if len(argv) < 2:
        print("usage: run.py <ShortName> <YYYY-MM> [<YYYY-MM> ...]")
        print("  (monthly collections; each month selected safely at its midpoint)")
        return 2
    short_name = argv[0]
    months = argv[1:]
    print("=" * 60)
    print(f"load-field — {short_name}")
    print(f"  months: {', '.join(months)}")
    print("=" * 60)
    ds = load_field(short_name, months=months)
    print(f"  variables: {list(ds.data_vars)}")
    print(f"  dims: {dict(ds.sizes)}")
    for v in ds.data_vars:
        u = ds[v].attrs.get("units", "?")
        print(f"    {v}: units={u}")
    print("✓ field loaded.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
