"""
ecco_common.plots — save-to-file plotting for ECCO LLC90 fields.

Thin wrappers over the OFFICIAL ecco_v4_py plotting functions (Rung-1: we use the
tutorial authors' own plotting code, not a reinvention):
  - plot_tile(...)                 -> ecco.plot_tile        (one tile, model orientation)
  - plot_global(...)               -> ecco.plot_proj_to_latlon_grid (stitched world map)
  - plot_all_tiles(...)            -> ecco.plot_tiles       (all 13 tiles laid out)

Design for a headless / agent environment: we force the non-interactive 'Agg' matplotlib
backend and SAVE every figure to a PNG (no windows to pop up), returning the path so the
user can open it. A 2-D field (one tile/level/time) is expected — callers reduce to 2-D
first (helper `to_2d` does the common isel).
"""

import os

# Force a headless backend BEFORE importing pyplot, so this works with no display.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def _default_out(name):
    """Default output path: ./plots/<name>.png at the project root (gitignore-able)."""
    from . import cache
    d = os.path.join(cache.project_root(), "plots")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _save(fig, out, log):
    """Save a figure to `out`, creating its parent directory first. Ensures the target
    dir exists whether `out` came from _default_out or an explicit caller path (e.g.
    'plots/gallery/x.png'), so savefig never fails on a missing directory."""
    parent = os.path.dirname(os.path.abspath(out))
    os.makedirs(parent, exist_ok=True)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out


def to_2d(field, tile=None, k=0, time=0):
    """Reduce a DataArray to a single 2-D horizontal slice for plotting.
    Selects k/time if those dims exist, and one tile if `tile` is given."""
    da = field
    if "time" in da.dims:
        da = da.isel(time=time)
    if "k" in da.dims:
        da = da.isel(k=k)
    if tile is not None and "tile" in da.dims:
        da = da.isel(tile=tile)
    return da


def plot_tile(field, tile, k=0, time=0, cmap="RdBu_r", title=None, out=None,
              log=print):
    """Plot ONE LLC tile of a field and save to PNG. Field is reduced to 2-D first.
    Uses ecco.plot_tile. Note: a single tile is in MODEL orientation (tiles 7–12 are
    not north-up) — for a geographic view use plot_global()."""
    import ecco_v4_py as ecco
    da = to_2d(field, tile=tile, k=k, time=time)
    f, arr = None, None
    result = ecco.plot_tile(da, cmap=cmap, show_colorbar=True)
    # ecco.plot_tile draws into the current figure; grab it
    fig = plt.gcf()
    if title:
        fig.suptitle(title)
    out = out or _default_out(f"tile{tile}_{getattr(field,'name','field')}.png")
    _save(fig, out, log)
    log(f"  [plot] saved single-tile plot → {out}")
    return out


def plot_all_tiles(field, k=0, time=0, cmap="RdBu_r", title=None, out=None, log=print):
    """Plot all 13 tiles laid out (ecco.plot_tiles). Good for seeing the whole grid at
    once without re-projection. Field reduced to 2-D (keeps the tile dim)."""
    import ecco_v4_py as ecco
    da = to_2d(field, tile=None, k=k, time=time)
    f, _ = ecco.plot_tiles(da, cmap=cmap, show_colorbar=True)
    if title:
        f.suptitle(title)
    out = out or _default_out(f"alltiles_{getattr(field,'name','field')}.png")
    _save(f, out, log)
    log(f"  [plot] saved all-tiles plot → {out}")
    return out


def plot_global(field, ds_grid, k=0, time=0, cmap="RdBu_r", title=None,
                projection_type="robin", cmin=None, cmax=None, out=None, log=print):
    """Stitched global lat-lon map via ecco.plot_proj_to_latlon_grid — the 'correct'
    whole-ocean view (handles tile rotation/re-projection). Needs the grid for XC/YC.
    Field reduced to 2-D (all tiles, one level/time)."""
    import ecco_v4_py as ecco
    da = to_2d(field, tile=None, k=k, time=time)
    kwargs = dict(projection_type=projection_type, cmap=cmap, show_colorbar=True)
    if cmin is not None:
        kwargs["cmin"] = cmin
    if cmax is not None:
        kwargs["cmax"] = cmax
    res = ecco.plot_proj_to_latlon_grid(ds_grid.XC, ds_grid.YC, da, **kwargs)
    fig = res[0]
    if title:
        fig.suptitle(title)
    out = out or _default_out(f"global_{getattr(field,'name','field')}.png")
    _save(fig, out, log)
    log(f"  [plot] saved global map → {out}")
    return out
