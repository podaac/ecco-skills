#!/usr/bin/env python3
"""
plot-ecco-field: make a PNG of any ECCO field — single tile, all 13 tiles, or a stitched
global map. Saves to ./plots/ (no display needed) and prints the path.

Uses the OFFICIAL ecco_v4_py plotting functions via ecco_common.plots.

Examples (run with the venv python):
  # global SST map, surface, Jan 2000
  .venv/bin/python run.py --collection ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4 \
        --var THETA --month 2000-01 --mode global --cmap RdYlBu_r

  # one tile of salinity at depth level 10
  .venv/bin/python run.py --collection ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4 \
        --var SALT --month 2000-01 --mode tile --tile 10 --k 10

  # all tiles laid out
  .venv/bin/python run.py --collection ECCO_L4_SSH_LLC0090GRID_MONTHLY_V4R4 \
        --var SSH --month 2000-01 --mode alltiles
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "ecco-common"))
import ecco_preflight  # noqa: E402
ecco_preflight.ensure_env("plot-ecco-field")  # clear msg if env is unhealthy
from ecco_common import load_grid, load_field, plots  # noqa: E402


def _log(m=""):
    print(m, flush=True)


def main(argv):
    ap = argparse.ArgumentParser(description="Plot an ECCO field to a PNG.")
    ap.add_argument("--collection", required=True, help="ECCO ShortName")
    ap.add_argument("--var", required=True, help="variable name, e.g. THETA")
    ap.add_argument("--month", help="YYYY-MM (monthly collections)")
    ap.add_argument("--day", help="YYYY-MM-DD (daily collections)")
    ap.add_argument("--mode", choices=["global", "tile", "alltiles"], default="global")
    ap.add_argument("--tile", type=int, default=10, help="tile index for --mode tile")
    ap.add_argument("--k", type=int, default=0, help="depth level index (0=surface)")
    ap.add_argument("--cmap", default="RdYlBu_r")
    ap.add_argument("--cmin", type=float, default=None)
    ap.add_argument("--cmax", type=float, default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--out", default=None, help="output PNG path (default ./plots/…)")
    args = ap.parse_args(argv)

    if not (args.month or args.day):
        ap.error("give --month YYYY-MM or --day YYYY-MM-DD")

    _log("=" * 60)
    _log(f"plot-ecco-field: {args.var} from {args.collection}")
    _log("=" * 60)
    ds_grid, _ = load_grid(log=_log)
    sel = {"months": [args.month]} if args.month else {"days": [args.day]}
    ds = load_field(args.collection, log=_log, **sel)
    if args.var not in ds.data_vars:
        ap.error(f"'{args.var}' not in {args.collection}. Available: {list(ds.data_vars)}")
    field = ds[args.var]
    field.name = args.var
    when = args.month or args.day
    title = args.title or f"{args.var}  {when}  (k={args.k})"

    if args.mode == "global":
        out = plots.plot_global(field, ds_grid, k=args.k, cmap=args.cmap,
                                cmin=args.cmin, cmax=args.cmax, title=title,
                                out=args.out, log=_log)
    elif args.mode == "tile":
        out = plots.plot_tile(field, tile=args.tile, k=args.k, cmap=args.cmap,
                              title=title, out=args.out, log=_log)
    else:
        out = plots.plot_all_tiles(field, k=args.k, cmap=args.cmap, title=title,
                                   out=args.out, log=_log)

    _log("")
    _log(f"✓ Wrote {out}")
    _log("  Open it to view the field. (Global mode is the geographically-correct view;")
    _log("   a single tile is in model orientation — tiles 7–12 are not north-up.)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
