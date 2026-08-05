#!/usr/bin/env python3
"""
compute-thermal-wind (Recipe 3): vertical shear of geostrophic flow from the horizontal
density structure, plus velocity reconstruction from a level of no motion.

Thermal-wind balance (Boussinesq, as the ECCO Thermal Wind tutorial writes it):

    ∂v/∂z = -(g / (f·ρ)) · ∂ρ/∂x        ∂u/∂z =  (g / (f·ρ)) · ∂ρ/∂y

with ρ = rhoConst + RHOAnoma (rhoConst = 1029), g = 9.81, f = 2Ω·sin(lat), Ω = 2π/86164.
This is what you get by taking ∂/∂z of geostrophic balance and substituting hydrostatic
balance — so the density field alone predicts the *shear* of the currents.

Then, given a "level of no motion" z0 where the flow is assumed ~0, we integrate the shear
vertically to reconstruct the velocity profile (upward above z0, downward below), and — as
the tutorial does — compare that reconstruction to the model's ACTUAL velocity.

VERIFICATION (see references/acceptance.md, docs/verify.md):
  There is NO official `thermal_wind_compute` helper in ecco_po_tutorials.py (only
  `geos_vel_compute` exists), so Rung-1 (official-helper match) is N/A. Correctness rests
  on the tutorial's own two independent cross-checks, both automated in test_thermal_wind.py:
    (A) predicted shear (from DENSITY) ≈ actual velocity shear (∂/∂z of UVEL/VVEL) off-equator;
    (B) reconstructed velocity ≈ the model's ACTUAL velocity along 26°N (normalized diff).
  Both compare against a *different* variable/collection (velocity), so they rule out a bug
  confined to the density path.

COORDINATE FRAME — why we stay in model x/y:
  The tutorial rotates shear/velocity to geographic (zonal/meridional) with CS/SN before its
  panels. We keep everything in **model x/y**. This is provably equivalent for the balance
  and for the tutorial's verification metric: the CS/SN rotation is orthogonal, so the vector
  magnitudes |(u,v)| and |Δ(u,v)| — hence the normalized difference |Δvel|/|vel| the tutorial
  reports — are rotation-invariant. Rotating is a presentation step for maps, not needed for
  the physics check. (Mirrors compute-geostrophic-balance, which also outputs model x/y.)

Run with the venv python:
    .venv/bin/python run.py 2000-01
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "ecco-common"))
from ecco_common import load_grid, load_field  # noqa: E402

DENSPRESS = "ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4"
OCEAN_VEL = "ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4"

RHO_CONST = 1029.0                              # kg m-3, Boussinesq reference density
OMEGA = 2.0 * 3.141592653589793 / 86164.0       # Earth rotation rate, sidereal day
G = 9.81                                        # m s-2

EQ_BAND_DEG = 5.0        # |lat| < this is masked (equatorial 1/f singularity)
Z0_DEFAULT = -3000.0     # level of no motion for the reconstruction (tutorial value)

# Physical-sanity bounds (Layer 3), calibrated against Jan-2000 real data (see acceptance.md).
SHEAR_ABS_MAX = 1.0e-2   # s-1; off-equator vertical shear is O(1e-4); this is a generous cap
UREC_ABS_MAX = 5.0       # m/s; reconstructed speeds are < a few m/s except near f→0


def _log(msg=""):
    print(msg, flush=True)


def _canon(da):
    """Transpose to canonical (time,k,tile,j,i) order — only the dims present, in that
    order. xgcm.interp_2d_vector returns dims in an arbitrary order (e.g. tile,j,i,time,k),
    so we normalize before any positional numpy indexing (drC broadcast, k-slicing)."""
    order = [d for d in ("time", "k", "tile", "j", "i") if d in da.dims]
    return da.transpose(*order)


def _coriolis(ds_grid):
    """Coriolis parameter f = 2Ω·sin(lat) at cell centers (dims tile,j,i). Same formula
    as compute-geostrophic-balance."""
    import numpy as np
    lat = ds_grid.YC
    return 2.0 * OMEGA * np.sin((np.pi / 180.0) * lat), lat


def predicted_shear(ds_grid, xgcm_grid, ds_dp, log=_log):
    """Thermal-wind RHS: the vertical shear predicted from the DENSITY field, in MODEL x/y.

        dv/dz = -(g/(f·ρ))·∂ρ/∂x        du/dz = (g/(f·ρ))·∂ρ/∂y

    Returns (dudz_pred, dvdz_pred, f, lat, dens). Density gradient uses the same
    xgcm.diff → interp_2d_vector pattern as the geostrophic skill (tracer→face→tracer).
    """
    dens = (RHO_CONST + ds_dp.RHOAnoma)
    if hasattr(dens, "compute"):
        dens = dens.compute()

    # horizontal density gradient on the C-grid, then interpolate the vector back to centers
    d_rho_dx = xgcm_grid.diff(dens, axis="X", boundary="extend") / ds_grid.dxC
    d_rho_dy = xgcm_grid.diff(dens, axis="Y", boundary="extend") / ds_grid.dyC
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        grads = xgcm_grid.interp_2d_vector({"X": d_rho_dx, "Y": d_rho_dy},
                                           boundary="extend")
    # interp_2d_vector returns dims in a non-canonical order; normalize before math.
    d_rho_dx = _canon(grads["X"])        # at tracer centers now, dims time,k,tile,j,i
    d_rho_dy = _canon(grads["Y"])

    f, lat = _coriolis(ds_grid)

    # model-axis thermal wind (un-rotated; see COORDINATE FRAME note in the module docstring)
    dvdz_pred = _canon(-(G / (f * dens)) * d_rho_dx)
    dudz_pred = _canon((G / (f * dens)) * d_rho_dy)
    dudz_pred.name, dvdz_pred.name = "dudz_pred", "dvdz_pred"
    for da in (dudz_pred, dvdz_pred):
        da.attrs.update({"units": "s-1",
                         "long_name": "thermal-wind vertical shear (model axis)"})
    return dudz_pred, dvdz_pred, f, lat, dens


def actual_velocity_centers(ds_grid, xgcm_grid, ds_vel):
    """Model's ACTUAL velocity interpolated to tracer centers (model x/y), NaN→0 first
    (tutorial does this before vector interpolation). Returns (u, v) with dims time,k,tile,j,i."""
    import numpy as np
    import warnings
    UVEL = ds_vel.UVEL.compute() if hasattr(ds_vel.UVEL, "compute") else ds_vel.UVEL
    VVEL = ds_vel.VVEL.compute() if hasattr(ds_vel.VVEL, "compute") else ds_vel.VVEL
    UVEL = UVEL.copy(); VVEL = VVEL.copy()
    UVEL.values[np.isnan(UVEL.values)] = 0.0
    VVEL.values[np.isnan(VVEL.values)] = 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vel = xgcm_grid.interp_2d_vector({"X": UVEL, "Y": VVEL}, boundary="extend")
    return _canon(vel["X"]), _canon(vel["Y"])


def actual_shear(u, v, ds_grid):
    """Vertical shear of the ACTUAL velocity (LHS of thermal wind), model x/y. Differences
    over k and divides by drC (center-to-center distance) — negated because k increases
    downward while z increases upward — then interpolates edge values back to cell centers.
    Faithful to the tutorial (cell 17). Returns (dudz_act, dvdz_act)."""
    import numpy as np
    import xarray as xr
    drC_int = ds_grid.drC[1:-1].values                     # 49 interior center-to-center
    exp = np.expand_dims(drC_int, axis=(0, 2, 3, 4))       # broadcast over time,tile,j,i

    def _shear(vel):
        edge = -(vel.diff("k").values) / exp               # (time,49,tile,j,i), at k-edges
        out = np.empty(vel.shape); out.fill(np.nan)
        # interpolate edge-centered shear back to tracer centers (interior levels only)
        out[:, 1:-1, :, :, :] = edge[:, 1:, :, :, :] - (np.diff(edge, axis=1) / 2)
        return xr.DataArray(out, dims=vel.dims, coords=vel.coords)

    return _shear(u), _shear(v)


def reconstruct_velocity(dudz_pred, dvdz_pred, ds_grid, z0=Z0_DEFAULT):
    """Reconstruct velocity by integrating the predicted shear vertically from a level of
    no motion z0 (default -3000 m): upward integration above z0, downward below, combined.
    Faithful transcription of the tutorial (cell 21). Returns (u_recon, v_recon), model x/y.
    """
    import numpy as np
    nk = len(ds_grid.k)

    # --- upward integration (surface side of z0) ---
    Zl = ds_grid.Zl.compute() if hasattr(ds_grid.Zl, "compute") else ds_grid.Zl
    dist_up = (Zl - z0).where(~(Zl < z0), 0.0)                     # 0 below z0
    delta_up = (-dist_up.diff("k_l")).values                      # 49
    delta_up = np.concatenate((delta_up, np.array([0.0])))        # 50 (last level → 0)
    delta_up = np.expand_dims(delta_up, axis=(0, 2, 3, 4))

    def _up(rhs):
        # cumulative sum from the bottom of the upper column toward the surface
        acc = ((delta_up * rhs).sel(k=slice(None, None, -1))
               .cumsum(dim="k", skipna=True)).sel(k=slice(None, None, -1))
        # interpolate to cell centers (interior levels)
        out = acc.copy()
        out.values[:, :nk - 1, ...] = (acc.isel(k=slice(0, nk - 1)).values
                                       + (acc.diff("k").values) / 2)
        return out

    v_up = _up(dvdz_pred)
    u_up = _up(dudz_pred)

    # --- downward integration (deep side of z0) ---
    Zu = ds_grid.Zu.compute() if hasattr(ds_grid.Zu, "compute") else ds_grid.Zu
    dist_lo = (Zu - z0).where(~(Zu > z0), 0.0)                     # 0 above z0
    delta_lo = (-dist_lo.diff("k_u")).values                      # 49
    delta_lo = np.concatenate((np.array([0.0]), delta_lo))        # 50
    delta_lo = np.expand_dims(delta_lo, axis=(0, 2, 3, 4))

    def _down(rhs):
        acc = (delta_lo * rhs).cumsum(dim="k", skipna=True)
        interp = (acc.isel(k=slice(0, nk - 1)).values + (acc.diff("k").values) / 2)
        out = acc.copy()
        out.values[:, 1:, ...] = interp                           # shift down by one, level0→pad
        out.values[:, 0, ...] = 0.0
        return out

    v_down = _down(dvdz_pred)
    u_down = _down(dudz_pred)

    # --- combine: upward above z0, downward below ---
    zc = v_up.Z.values
    v_recon = v_up.copy()
    u_recon = u_up.copy()
    below = zc < z0
    v_recon.values[:, below, ...] = v_down.values[:, below, ...]
    u_recon.values[:, below, ...] = u_down.values[:, below, ...]
    u_recon.name, v_recon.name = "u_recon", "v_recon"
    for da in (u_recon, v_recon):
        da.attrs.update({"units": "m s-1",
                         "long_name": f"velocity reconstructed from thermal wind, z0={z0:.0f} m"})
    return u_recon, v_recon


def validate(dudz_pred, dvdz_pred, u_recon, v_recon, lat, log=_log):
    """Runtime validation trail (physical plausibility; needs no velocity data). Returns
    True if all mandatory checks pass. The independent correctness evidence is the two
    cross-checks in test_thermal_wind.py (vs the model's actual velocity)."""
    import numpy as np
    ok = True
    log("  Validation trail:")

    # L1 — grid position + units: shear interpolated to tracer points → dims i,j; units s-1.
    on_tracer = {"i", "j"}.issubset(set(dudz_pred.dims))
    units_ok = dudz_pred.attrs.get("units") == "s-1"
    l1 = on_tracer and units_ok
    log(f"    [{'✓' if l1 else '✗'}] L1 input: shear on tracer points {tuple(dudz_pred.dims)}, "
        f"units={dudz_pred.attrs.get('units')!r}")
    ok = ok and l1

    eq_mask = np.abs(lat) < EQ_BAND_DEG
    du_oe = dudz_pred.where(~eq_mask); dv_oe = dvdz_pred.where(~eq_mask)

    # L1b — finite off-equator (NaN on land/equator is fine; inf is not).
    n_inf = int(np.isinf(du_oe.values).sum() + np.isinf(dv_oe.values).sum())
    l1b = (n_inf == 0)
    log(f"    [{'✓' if l1b else '✗'}] L1 finite: {n_inf} infinite shear value(s) off-equator "
        f"(expect 0)")
    ok = ok and l1b

    # L3 — physical bounds on the shear (away from the equatorial 1/f blow-up).
    sh_max = float(np.nanmax(np.abs(du_oe.values)))
    sh_max = max(sh_max, float(np.nanmax(np.abs(dv_oe.values))))
    l3s = sh_max <= SHEAR_ABS_MAX
    log(f"    [{'✓' if l3s else '✗'}] L3 bounds: |∂u/∂z|,|∂v/∂z| ≤ {SHEAR_ABS_MAX:g} s⁻¹ "
        f"outside ±{EQ_BAND_DEG}° (got max {sh_max:.2e})")
    ok = ok and l3s

    # L3 — physical bounds on the reconstructed speed.
    ur_oe = u_recon.where(~eq_mask); vr_oe = v_recon.where(~eq_mask)
    spd_max = float(np.nanmax(np.hypot(ur_oe.values, vr_oe.values)))
    l3v = spd_max <= UREC_ABS_MAX
    log(f"    [{'✓' if l3v else '✗'}] L3 bounds: reconstructed speed ≤ {UREC_ABS_MAX} m/s "
        f"outside ±{EQ_BAND_DEG}° (got max {spd_max:.2f})")
    ok = ok and l3v

    # L4 — closure: N/A (diagnostic shear, not a budget).
    log("    [–] L4 closure: not applicable (diagnostic shear, not a budget)")

    log("    [i] Correctness: test_thermal_wind.py checks (A) predicted shear ≈ actual")
    log("        velocity shear and (B) reconstruction ≈ actual velocity @26°N.")
    return ok


def main(argv):
    if not argv:
        print("usage: run.py <YYYY-MM>   (thermal-wind shear + velocity reconstruction)")
        return 2
    ym = argv[0]

    _log("=" * 64)
    _log("compute-thermal-wind (Recipe 3)")
    _log("=" * 64)
    _log("Loading grid + density/pressure ...")
    ds_grid, xgcm_grid = load_grid(log=_log)
    ds_dp = load_field(DENSPRESS, months=[ym], log=_log)

    _log(f"\nComputing thermal-wind shear for {ym} (model x/y coords) ...")
    dudz_pred, dvdz_pred, f, lat, dens = predicted_shear(ds_grid, xgcm_grid, ds_dp)

    _log(f"Reconstructing velocity from a level of no motion z0={Z0_DEFAULT:.0f} m ...")
    u_recon, v_recon = reconstruct_velocity(dudz_pred, dvdz_pred, ds_grid)

    import numpy as np
    oe = np.abs(lat) >= EQ_BAND_DEG
    dv0 = dvdz_pred.isel(time=0, k=10) if "time" in dvdz_pred.dims else dvdz_pred.isel(k=10)
    _log(f"  |∂v/∂z| median @k=10 (off-equator): "
         f"{float(np.nanmedian(np.abs(dv0.where(oe).values))):.2e} s⁻¹")

    ok = validate(dudz_pred, dvdz_pred, u_recon, v_recon, lat)
    _log("")
    _log("=" * 64)
    _log("VALIDATION: all runtime checks passed ✓" if ok
         else "VALIDATION: a check FAILED ✗ — do not trust the result.")
    _log("Correctness vs the model's actual velocity is checked by test_thermal_wind.py.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
