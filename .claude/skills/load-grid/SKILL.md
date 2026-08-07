---
name: load-grid
description: Load the ECCO LLC90 grid geometry (cell areas, distances, hFac partial-cell fractions, land masks, CS/SN rotation, vertical coordinates) and build the xgcm grid object used for differencing and interpolation. Downloads the one geometry file on first use and caches it in ./data/ecco. Use whenever a calculation needs grid metrics or the xgcm grid — which is almost every ECCO calculation. Requires the ecco-setup environment.
---

# load-grid

> **🔬 Verification status (per `docs/verify.md`): ✅ verified (infrastructure).** Builds
> the grid via the **official `ecco.get_llc_grid`** (Rung 1), tested end-to-end incl. from
> outside the repo, and covered by the `ecco-common` regression suite. Not a science
> calculation, so the physics rungs don't apply.

Loads the ECCO **geometry** — the fixed description of the LLC90 grid — and builds the
`xgcm` grid object. Nearly every calculation needs this: volumes (`rA`, `drF`,
`hFacC`), face distances (`dxG`, `dyG`), land masks (`maskC/W/S`), axis rotation
(`CS`, `SN`), and vertical coordinates (`Z`, `Zl`, `drC`).

The geometry is a **single time-invariant file** (~8 MB) — there is no date to pick.
Downloaded once via the CMR direct-URL path (see design.md) and cached; reused forever.

## Prerequisite — ensure the environment first

The `ecco-setup` environment must exist (`.venv` with the ECCO libraries, xgcm < 0.10).
Downloading also needs Earthdata Login credentials in `~/.netrc` (a 401 = missing/invalid).
**Before running, ensure the env is ready — don't run against a missing/broken `.venv`:**

1. Check health: `python3 .claude/skills/ecco-setup/scripts/verify_env.py` (verify mode).
2. If it reports **no `.venv`** or a failed import, **run `ecco-setup` first**
   (`setup_env.py`, or `--reset` to rebuild), then re-run. A healthy `.venv` is reused
   automatically. (Invoking `run.py` on an unhealthy env trips the built-in `ecco_preflight`
   guard, which points you here; a *missing* `.venv` means `.venv/bin/python` won't exist.)

## How to use it

**From another skill (the normal case — Option A composition):** import the shared
helper; do not shell out.

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ecco-common"))
from ecco_common import load_grid

ds_grid, grid = load_grid()      # ds_grid = xarray metrics; grid = xgcm grid object
cell_volume = ds_grid.rA * ds_grid.drF * ds_grid.hFacC
```

**Standalone (to fetch/verify the grid on its own):**

```
.venv/bin/python scripts/run.py
```

Run it with the **venv** python (see design.md → Interpreter policy), so it uses the
pinned xgcm 0.9.0 that `ecco.get_llc_grid` needs.

## What it returns

- `ds_grid` — an xarray Dataset of grid metrics (XC/YC, rA, drF, drC, dxG/dyG,
  hFacC/W/S, maskC/W/S, CS, SN, Z/Zl/Zu, Depth, …).
- `grid` — the `xgcm` Grid object from `ecco.get_llc_grid(ds_grid)`, for
  staggered-grid `diff`/`interp` (use the `boundary=`/`fill_value=` API; xgcm < 0.10).

## Notes

- **Caching:** file lands in `./data/ecco/ECCO_L4_GEOMETRY_LLC0090GRID_V4R4/`. Second
  run reports `[cache] using …` and does not re-download. Override the cache location
  with the `ECCO_DATA_DIR` env var.
- **Teach-as-you-go:** the run prints which metrics are available and confirms the
  xgcm object is ready, so a learner sees what the grid provides.
