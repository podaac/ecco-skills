"""
ecco_common — shared building blocks for the ECCO skills.

Calculation/plotting/data skills import from here so the download, caching, and
grid-loading logic is written ONCE and reused (Option A architecture; see
design.md → How skills compose). All code here runs under the project .venv python.

Typical use inside a skill script:

    from ecco_common import load_grid, load_field

    ds_grid, grid = load_grid()
    ds_ts = load_field("ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4",
                       start="2000-01-01", end="2000-01-31")
"""

from .loaders import load_grid, load_field, GEOMETRY_SHORT_NAME
from .grid_ops import OMEGA, coriolis, canon, grad_to_center
from . import access, cache, loaders, plots, grid_ops

__all__ = ["load_grid", "load_field", "GEOMETRY_SHORT_NAME",
           "OMEGA", "coriolis", "canon", "grad_to_center",
           "access", "cache", "loaders", "plots", "grid_ops"]
