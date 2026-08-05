"""
ecco_common.loaders — the building-block loaders every calculation skill composes.

    load_grid()                       -> (ds_grid, xgcm_grid)
    load_field(short_name, ...)       -> xarray.Dataset (one or more time steps)

These return in-memory xarray objects (Option A: skills chain by importing and
calling these, not by passing objects across processes). The .nc cache underneath
means repeat calls don't re-download.
"""

import os

import xarray as xr

from . import access, cache

GEOMETRY_SHORT_NAME = "ECCO_L4_GEOMETRY_LLC0090GRID_V4R4"


def load_grid(log=print):
    """Download (if needed) and open the ECCO LLC90 geometry, and build the xgcm
    grid object. Returns (ds_grid, xgcm_grid).

    The geometry is a single time-invariant file, so there is no date argument.
    """
    # Offline fast-path: if the index knows the geometry filename and it's on disk,
    # open it without any CMR round-trip (works with no network).
    path = cache.lookup_cached(GEOMETRY_SHORT_NAME, "GEOMETRY")
    if path is not None:
        log(f"  [cache] using {GEOMETRY_SHORT_NAME}/{os.path.basename(path)} (offline)")
    else:
        granules = access.granules_for(GEOMETRY_SHORT_NAME)
        if not granules:
            raise RuntimeError("CMR returned no geometry granule for "
                               f"{GEOMETRY_SHORT_NAME}")
        path = access.ensure_granule(GEOMETRY_SHORT_NAME, granules[0], log=log)
        cache.record_in_index(GEOMETRY_SHORT_NAME, "GEOMETRY",
                              os.path.basename(path))
    ds_grid = xr.open_dataset(path)

    # Build the xgcm grid via ecco_v4_py (requires xgcm < 0.10; see design gotcha #9).
    import ecco_v4_py as ecco
    xgcm_grid = ecco.get_llc_grid(ds_grid)
    log(f"  [grid] loaded LLC90 geometry: {dict(ds_grid.sizes)}")
    return ds_grid, xgcm_grid


def load_field(short_name, months=None, days=None, start=None, end=None, log=print,
               assume_yes=False):
    """Download (if needed) and open a science field collection.

    Three ways to select time (give exactly ONE):
      months : list of 'YYYY-MM' — SAFE selector for MONTHLY data. Queries each month at
               its midpoint to dodge the month-edge overlap. months=['2000-01'] → Jan 2000.
      days   : list of 'YYYY-MM-DD' — SAFE selector for DAILY data. Queries each day at
               NOON to dodge the midnight-edge overlap (a 00:00Z query also matches the
               previous day), and filters returned filenames to the requested date.
      start/end : raw ISO range (advanced). Beware edge overlap on both monthly AND daily
               collections — prefer `months`/`days` for aligned selection.
    Returns an xarray.Dataset (concatenated over time if multiple granules).
    """
    # --- selector-contract validation: fail fast, before any network/filesystem work ---
    has_months = months is not None
    has_days = days is not None
    has_range = (start is not None) or (end is not None)
    n_selectors = sum([has_months, has_days, has_range])
    if n_selectors > 1:
        raise ValueError(
            "load_field: pass EXACTLY ONE of months=[...], days=[...], or start/end."
        )
    if n_selectors == 0:
        raise ValueError(
            "load_field: no time selector given. Pass months=['YYYY-MM', ...], "
            "days=['YYYY-MM-DD', ...], or start/end ISO dates."
        )
    if has_months and len(months) == 0:
        raise ValueError("load_field: months=[] is empty — give at least one 'YYYY-MM'.")
    if has_days and len(days) == 0:
        raise ValueError("load_field: days=[] is empty — give at least one 'YYYY-MM-DD'.")

    if has_months or has_days:
        keys = months if has_months else days
        granules_fn = access.granules_for_month if has_months else access.granules_for_day
        kind = "month" if has_months else "day"
        # Pass 1: resolve each key to either a cached path (offline) or its granule(s),
        # WITHOUT downloading yet. This lets the size guard see the WHOLE request at once
        # — guarding per-key would let a 100-day request slip through 29 MB at a time.
        paths = [None] * len(keys)          # cached results by position
        to_fetch = []                       # (position, key, granule) still to download
        for i, key in enumerate(keys):
            cached = cache.lookup_cached(short_name, key)
            if cached is not None:
                log(f"  [cache] using {short_name}/{os.path.basename(cached)} (offline)")
                paths[i] = cached
                continue
            key_granules = granules_fn(short_name, key)
            if not key_granules:
                raise RuntimeError(f"No granules found for {short_name} {kind} {key}")
            for g in key_granules:
                to_fetch.append((i, key, g))
        # Single size guard across everything not already cached.
        pending = [g for (_, _, g) in to_fetch]
        access.check_download_size(short_name, pending, assume_yes=assume_yes)
        # Pass 2: download (guard already cleared, so assume_yes here).
        expanded = []      # (position, path) allowing multiple granules per key
        for i, key, g in to_fetch:
            got = access.ensure_granules(short_name, [g], log=log, assume_yes=True)
            cache.record_in_index(short_name, key, g["filename"])
            expanded.append((i, got[0]))
        # Assemble final path list in key order (a key may map to >1 granule).
        final = []
        for i, key in enumerate(keys):
            if paths[i] is not None:
                final.append(paths[i])
            final.extend(p for (j, p) in expanded if j == i)
        paths = final
    else:
        granules = access.granules_for(short_name, start=start, end=end)
        if not granules:
            raise RuntimeError(f"No granules found for {short_name} in [{start}, {end}]")
        paths = access.ensure_granules(short_name, granules, log=log,
                                       assume_yes=assume_yes)
    if len(paths) == 1:
        ds = xr.open_dataset(paths[0])
    else:
        ds = xr.open_mfdataset(sorted(paths), combine="by_coords")
    log(f"  [field] {short_name}: {len(paths)} file(s), vars "
        f"{list(ds.data_vars)}")
    return ds
