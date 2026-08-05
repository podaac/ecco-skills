#!/usr/bin/env python3
"""
compute-geostrophic-balance (Recipe 2): geostrophic velocities from ECCO pressure.

Geostrophic balance  f·v = (1/ρ)·∂p/∂x ,  f·u = -(1/ρ)·∂p/∂y .
ECCO stores PHIHYDcR = p/rhoConst − gz, so ∂p/∂x = rhoConst·∂(PHIHYDcR)/∂x. Thus:

    v_g =  [rhoConst · ∂(PHIHYDcR)/∂x] / (ρ · f)
    u_g = -[rhoConst · ∂(PHIHYDcR)/∂y] / (ρ · f)      with  ρ = rhoConst + RHOAnoma

This implementation is a line-for-line match of the OFFICIAL tutorial helper
`ecco_po_tutorials.geos_vel_compute`. That match proves *reproducibility* (we equal the
reference); the stronger *correctness* evidence is the independent comparison to the
model's actual UVEL/VVEL (corr ~0.998 at ~200 m — rules out a bug shared with the
reference). Both are automated in test_geostrophic.py. Velocities are returned in
**model x/y** coordinates (NOT rotated to zonal/meridional) — what the reference
produces and what a like-for-like balance check requires.

Run with the venv python:
    .venv/bin/python run.py 2000-01
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "ecco-common"))
from ecco_common import load_grid, load_field  # noqa: E402

DENSPRESS = "ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4"

RHO_CONST = 1029.0            # kg m-3, Boussinesq reference density (ECCO/MITgcm)
OMEGA = 2.0 * 3.141592653589793 / 86164.0   # Earth rotation rate, sidereal day
G = 9.81

# Physical-sanity bounds (Layer 3), degC/velocity.
UG_ABS_MAX = 5.0              # m/s; geostrophic speeds are < a few m/s except near f→0
EQ_BAND_DEG = 5.0             # |lat| < this is masked (equatorial 1/f singularity)


def _log(msg=""):
    print(msg, flush=True)


def compute_geostrophic(ds_grid, xgcm_grid, ds_dp, log=_log):
    """Compute model-coordinate geostrophic velocities u_g, v_g (and f, lat, dens).

    Mirrors ecco_po_tutorials.geos_vel_compute exactly."""
    import numpy as np

    densanom = ds_dp.RHOAnoma
    dens = RHO_CONST + densanom
    pressanom = ds_dp.PHIHYDcR

    # ∂p/∂x, ∂p/∂y  (note the rhoConst factor: PHIHYDcR = p/rhoConst − gz)
    d_press_dx = (xgcm_grid.diff(RHO_CONST * pressanom, axis="X", boundary="extend")
                  ) / ds_grid.dxC
    d_press_dy = (xgcm_grid.diff(RHO_CONST * pressanom, axis="Y", boundary="extend")
                  ) / ds_grid.dyC

    # interpolate the (vector) gradient to cell centers
    grads = xgcm_grid.interp_2d_vector({"X": d_press_dx, "Y": d_press_dy},
                                       boundary="extend")
    dp_dx = grads["X"]
    dp_dy = grads["Y"]

    # Coriolis parameter from cell-center latitude
    lat = ds_grid.YC
    f = 2.0 * OMEGA * np.sin((np.pi / 180.0) * lat)

    v_g = dp_dx / (f * dens)
    u_g = -dp_dy / (f * dens)
    u_g.name, v_g.name = "u_g", "v_g"
    u_g.attrs.update({"long_name": "Geostrophic velocity in model-x direction",
                      "units": "m s-1"})
    v_g.attrs.update({"long_name": "Geostrophic velocity in model-y direction",
                      "units": "m s-1"})
    return u_g, v_g, f, lat, dens


def validate(u_g, v_g, lat, log=_log):
    """Runtime validation trail. Returns True if all mandatory checks pass.

    NOTE: this checks the *computation is well-formed and physically plausible*. The
    strongest correctness evidence is the Rung-1 match against geos_vel_compute
    (see test_geostrophic.py / acceptance.md) — not this runtime trail alone."""
    import numpy as np
    ok = True
    log("  Validation trail:")

    # L1 — grid position: gradients were interpolated to tracer points → dims i,j.
    on_tracer = {"i", "j"}.issubset(set(u_g.dims))
    units_ok = u_g.attrs.get("units") == "m s-1"
    l1 = on_tracer and units_ok
    log(f"    [{'✓' if l1 else '✗'}] L1 input: u_g on tracer points {tuple(u_g.dims)}, "
        f"units={u_g.attrs.get('units')!r}")
    ok = ok and l1

    # L3 — physical bounds AWAY FROM THE EQUATOR. Near the equator f→0 makes u_g/v_g
    # blow up legitimately (the balance breaks down); the tutorial masks |lat|<5°. So
    # bound-check only outside that band.
    eq_mask = np.abs(lat) < EQ_BAND_DEG                    # (tile,j,i)
    # broadcast eq_mask across (time,k) of u_g via xarray alignment on tile,j,i
    ug_off_eq = u_g.where(~eq_mask)
    vg_off_eq = v_g.where(~eq_mask)
    umax = float(np.nanmax(np.abs(ug_off_eq.values)))
    vmax = float(np.nanmax(np.abs(vg_off_eq.values)))
    l3 = (umax <= UG_ABS_MAX) and (vmax <= UG_ABS_MAX)
    log(f"    [{'✓' if l3 else '✗'}] L3 bounds: |u_g|,|v_g| ≤ {UG_ABS_MAX} m/s outside "
        f"±{EQ_BAND_DEG}° (got |u|max={umax:.2f}, |v|max={vmax:.2f})")
    ok = ok and l3

    # L1b — finite where expected (off-equator, wet). NaNs on land/equator are fine.
    n_bad = int(np.isinf(ug_off_eq.values).sum() + np.isinf(vg_off_eq.values).sum())
    l1b = (n_bad == 0)
    log(f"    [{'✓' if l1b else '✗'}] L1 finite: {n_bad} infinite value(s) off-equator "
        f"(expect 0)")
    ok = ok and l1b

    # Correctness evidence lives in the tests, not this runtime trail:
    log("    [i] Correctness: test_geostrophic.py checks (a) reproducibility vs official")
    log("        geos_vel_compute AND (b) independent match to actual model UVEL/VVEL "
        "(~0.998 corr @200m).")
    return ok


def main(argv):
    if not argv:
        print("usage: run.py <YYYY-MM>   (monthly geostrophic velocities, model coords)")
        return 2
    ym = argv[0]

    _log("=" * 64)
    _log("compute-geostrophic-balance (Recipe 2)")
    _log("=" * 64)
    _log("Loading grid + density/pressure ...")
    ds_grid, xgcm_grid = load_grid(log=_log)
    ds_dp = load_field(DENSPRESS, months=[ym], log=_log)

    _log(f"\nComputing geostrophic velocities for {ym} (model x/y coords) ...")
    u_g, v_g, f, lat, dens = compute_geostrophic(ds_grid, xgcm_grid, ds_dp)

    import numpy as np
    ug0 = u_g.isel(time=0, k=0) if "time" in u_g.dims else u_g.isel(k=0)
    vg0 = v_g.isel(time=0, k=0) if "time" in v_g.dims else v_g.isel(k=0)
    _log(f"  surface |u_g| median (off-equator): "
         f"{float(np.nanmedian(np.abs(ug0.where(np.abs(lat) >= EQ_BAND_DEG).values))):.3f} m/s")

    ok = validate(u_g, v_g, lat)
    _log("")
    _log("=" * 64)
    _log("VALIDATION: all runtime checks passed ✓" if ok
         else "VALIDATION: a check FAILED ✗ — do not trust the result.")
    _log("Correctness vs the official helper is checked by test_geostrophic.py (Rung 1).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
