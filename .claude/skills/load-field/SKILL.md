---
name: load-field
description: Load an ECCO science field (temperature, salinity, velocity, density/pressure, SSH, fluxes, stress, bolus velocity) for a chosen month or months. Downloads only what's requested from PO.DAAC via CMR, caches it in ./data/ecco, and returns an xarray Dataset. Use to get the actual data variables a calculation operates on. Requires the ecco-setup environment and Earthdata credentials.
---

# load-field

> **🔬 Verification status (per `docs/verify.md`): ✅ verified (infrastructure).** Data
> access (CMR query, pagination, size guard by `.nc` filename, month/day midpoint
> selection, cache backfill, offline reuse, selector validation) is locked by the
> `ecco-common` regression suite (13 tests, teeth-verified). Not a science calculation.
> *Note:* it does not yet verify downloads against the captured checksum — a known TODO.

Loads an ECCO **science variable** for a chosen time — the measurements a calculation
actually operates on (THETA, SALT, UVEL/VVEL, RHOAnoma/PHIHYDcR, SSH, the 3D flux
diagnostics, stress, bolus velocity). Downloads only the granules requested, caches
them, and returns an xarray Dataset.

Pair with `load-grid`: grid = the map (where/how big the cells are); field = the
values on that map at a point in time.

## Prerequisite — ensure the environment first

Runs in the project `.venv` built by **`ecco-setup`** + needs Earthdata Login credentials in
`~/.netrc` (a 401 on download means credentials are missing/invalid). **Before running,
ensure the env is ready — don't run against a missing/broken `.venv`:**

1. Check health: `python3 .claude/skills/ecco-setup/scripts/verify_env.py` (verify mode).
2. If it reports **no `.venv`** or a failed import, **run `ecco-setup` first**
   (`setup_env.py`, or `--reset` to rebuild), then re-run. A healthy `.venv` is reused
   automatically. (Invoking `run.py` on an unhealthy env trips the built-in `ecco_preflight`
   guard, which points you here; a *missing* `.venv` means `.venv/bin/python` won't exist.)

## Selecting time — use `months` (important)

Monthly-mean granules carry time bounds that meet at month edges, so an edge-aligned
date range (e.g. `2000-01-01`..`2000-01-31`) **also matches the adjacent month's file**
— a silent off-by-one that would double your data. The `months=` selector avoids this
by querying each month at its midpoint. **Prefer `months` for monthly collections.**

## How to use it

**From another skill (normal case — Option A composition):**

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "ecco-common"))
from ecco_common import load_field

ds = load_field("ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4", months=["2000-01"])
theta = ds.THETA        # exactly January 2000, one time step
```

**Standalone:**

```
.venv/bin/python scripts/run.py ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4 2000-01
```

Run with the **venv** python (design.md → Interpreter policy).

## Collections (ShortNames)

Core: `ECCO_L4_TEMP_SALINITY_…`, `ECCO_L4_OCEAN_VEL_…`, `ECCO_L4_DENS_STRAT_PRESS_…`,
`ECCO_L4_SSH_…`. Flux/stress/bolus: `ECCO_L4_OCEAN_3D_{TEMPERATURE,SALINITY,VOLUME}_FLUX_…`,
`ECCO_L4_STRESS_…`, `ECCO_L4_BOLUS_…` (all `…_LLC0090GRID_MONTHLY_V4R4`). See design.md
Data Access tables for the full list, concept IDs, and key variables.

## Guards & caching

- **Size-aware guard:** if a request would download more than ~1 GB (e.g. many years),
  it stops and asks you to confirm rather than silently pulling tens of GB. Narrow the
  month range, or pass `assume_yes=True` when you really mean it.
- **Caching:** files land in `./data/ecco/<ShortName>/`; repeat requests report
  `[cache] using …`. Override location with `ECCO_DATA_DIR`.
- **Teach-as-you-go:** prints each variable and its units, so unit assumptions are
  visible before you compute (e.g. SALT units are `1e-3`, i.e. PSU).
