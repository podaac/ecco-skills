"""
ecco_common.grid_ops — shared LLC90 grid-operation primitives (Level 1).

Extracted 2026-08-05 from the calculation skills once several concrete callers had shaped
the interfaces (the project's "extract on real multi-caller demand" rule; see
docs/roadmap.md → Phase 2). These are the mechanics that were previously copied verbatim
into geostrophy / thermal-wind / curl / steric.

Extracted here (≥2 real callers each):
  - OMEGA, coriolis(ds_grid)              — Coriolis parameter f = 2Ω·sin(lat) at cell
                                            centers. Callers: geostrophy, thermal-wind, curl.
  - canon(da)                            — normalize dim order to (time,k,tile,j,i) after
                                            xgcm ops, before positional numpy indexing.
                                            Callers: thermal-wind, curl, steric.
  - grad_to_center(scalar, …)            — horizontal gradient of a tracer-centered scalar,
                                            interpolated back to cell centers (∂/∂x, ∂/∂y).
                                            Callers: geostrophy, thermal-wind.

NOT extracted (only ONE caller so far — extracting against a single caller bakes in the
wrong interface; extract when a 2nd caller appears, per the roadmap):
  - rotate-to-geographic (CS/SN)   — only curl. (And curl's rotation is bit-identical to the
    official ecco_v4_py.vector_calc.UEVNfromUXVY, which is the better thing to adopt when a
    2nd caller arrives.)
  - vertical-difference (∂/∂k / drC) — only thermal-wind.
  - volume/area weighting (rA·drF·hFacC, area-weighted mean) — OHC + steric, deferred.

DESIGN NOTE — grad_to_center returns NATIVE (un-canon'd) dim order on purpose. The
geostrophic skill compares its result's flattened .values against the official
geos_vel_compute (Rung 1) and must keep the reference's dim order; callers that then do
positional numpy indexing (thermal-wind) call canon() on the result themselves, exactly as
they did when the logic was inlined. This keeps the geostrophy refactor a true no-op.
"""

import numpy as np

# Earth rotation rate using the sidereal day (matches the ECCO tutorials' geos_vel_compute).
OMEGA = 2.0 * np.pi / 86164.0


def coriolis(ds_grid):
    """Coriolis parameter f = 2Ω·sin(lat) at tracer cell centers (dims tile,j,i).

    Returns (f, lat) where lat = ds_grid.YC. Same formula used by the geostrophy,
    thermal-wind, and curl skills.
    """
    lat = ds_grid.YC
    f = 2.0 * OMEGA * np.sin((np.pi / 180.0) * lat)
    return f, lat


def canon(da):
    """Transpose a DataArray to canonical (time,k,tile,j,i) order — only the dims present,
    in that order. xgcm.interp_2d_vector (and some xarray ops) return dims in an arbitrary
    order, so normalize before ANY positional numpy indexing (e.g. np.expand_dims broadcasts,
    k-slicing). Dims not present are simply skipped (a 2-D surface field has no k)."""
    order = [d for d in ("time", "k", "tile", "j", "i") if d in da.dims]
    return da.transpose(*order)


def grad_to_center(scalar, ds_grid, xgcm_grid, boundary="extend"):
    """Horizontal gradient of a tracer-centered SCALAR, returned at cell centers.

    Differences the scalar along model X and Y (tracer→face) and divides by the
    center-to-center distances dxC/dyC, then interpolates the (vector) gradient back to
    tracer centers with xgcm.interp_2d_vector. This is the vetted C-grid gradient sequence
    the ECCO tutorials use (and that geostrophy / thermal-wind copied inline).

    Parameters
    ----------
    scalar : xr.DataArray on tracer points (dims include i, j) — e.g. rhoConst·PHIHYDcR
             (pressure) or in-situ density.
    ds_grid : geometry dataset (provides dxC, dyC).
    xgcm_grid : the xgcm Grid from ecco.get_llc_grid.
    boundary : xgcm diff/interp boundary handling (default "extend", the tutorial default).

    Returns
    -------
    (dfdx, dfdy) : the two gradient components at cell centers, in xgcm's NATIVE dim order
                   (NOT canon'd — see the module DESIGN NOTE). Callers that need a fixed dim
                   order for positional numpy should apply canon() themselves.
    """
    import warnings
    dfdx = xgcm_grid.diff(scalar, axis="X", boundary=boundary) / ds_grid.dxC
    dfdy = xgcm_grid.diff(scalar, axis="Y", boundary=boundary) / ds_grid.dyC
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # interp_2d_vector emits benign future warnings
        grads = xgcm_grid.interp_2d_vector({"X": dfdx, "Y": dfdy}, boundary=boundary)
    return grads["X"], grads["Y"]
