---
name: plot-ecco-field
description: Make a PNG image of any ECCO field — a single LLC tile, all 13 tiles laid out, or a geographically-correct stitched global map. Saves to ./plots/ (no display needed). Use to SEE a field (SST, SSH, salinity, velocity, geostrophic output, etc.) or to visually sanity-check any calculation's result. Wraps the official ecco_v4_py plotting functions. Requires the ecco-setup environment.
---

# plot-ecco-field

> **🔬 Verification status (per `docs/verify.md`): ✅ verified (visualization).** Wraps the
> **official `ecco_v4_py` plotting functions** — `plot_tile`, `plot_tiles`,
> `plot_proj_to_latlon_grid` (Rung 1: we use the tutorial authors' own plotting code, not
> a reinvention). Verified by producing a physically-correct global SST map (warm equator,
> cold poles, land masked) and a model-orientation single-tile view. Not a numerical
> calculation, so the physics rungs don't apply; correctness = "the official plotter
> renders our field faithfully."

See ECCO fields as images. Three modes:

| Mode | What it shows | When to use |
|------|---------------|-------------|
| `global` | Stitched lat-lon world map (Robinson), tiles rotated & re-projected | **The correct whole-ocean view.** Default. |
| `tile` | One 90×90 LLC tile in **model** orientation | Debugging / inspecting a single tile (note: tiles 7–12 are not north-up). |
| `alltiles` | All 13 tiles laid out in the LLC arrangement | Seeing the raw grid layout at a glance. |

## How to run

```
.venv/bin/python scripts/run.py \
    --collection ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4 \
    --var THETA --month 2000-01 --mode global --cmap RdYlBu_r
```

Key args: `--collection` (ShortName), `--var` (e.g. THETA/SALT/SSH/UVEL), `--month
YYYY-MM` or `--day YYYY-MM-DD`, `--mode global|tile|alltiles`, `--k` (depth level,
0=surface), `--tile` (for tile mode), `--cmap`, `--cmin/--cmax`, `--title`, `--out`.

Output PNGs go to `./plots/` (gitignored) unless `--out` is given. The script prints the
path; open it to view.

## Plotting a calculation's output (from another skill)

Import the shared plot helpers directly — this is how a calc skill visualizes its result:

```python
from ecco_common import load_grid, plots
ds_grid, _ = load_grid()
# ... compute some field `u_g` (a DataArray on tile,j,i) ...
plots.plot_global(u_g, ds_grid, k=0, cmap="RdBu_r", cmin=-0.3, cmax=0.3,
                  title="Surface geostrophic u_g")   # → ./plots/…png
```

`plots.to_2d(field, tile=, k=, time=)` reduces a 4-D/5-D field to the 2-D slice the
plotters expect.

## Notes / honest caveats

- **Headless by design:** forces the `Agg` matplotlib backend and saves to file — no
  window opens. Good for agents/servers; the deliverable is the PNG path.
- **Global mode needs the grid** (for XC/YC) — the skill loads it automatically.
- **Single-tile is model orientation**, not geographic. For "where on Earth is this",
  use `global`.
- **Colormap is yours to choose** — `RdYlBu_r` suits temperature; diverging `RdBu_r`
  suits anomalies/velocities; set `--cmin/--cmax` for a fixed scale.
- First global plot triggers a one-time cartopy coastline download (needs network once).

## Files
- `scripts/run.py` — CLI.
- Shared helpers live in `ecco_common/plots.py` (`plot_global`, `plot_tile`,
  `plot_all_tiles`, `to_2d`).
