#!/usr/bin/env python3
"""
compute-steric-height (Recipe 3-steric): steric height anomaly — the part of sea level set
by the density structure of the water column — plus its thermosteric (temperature) and
halosteric (salinity) decomposition.

THE PHYSICS:
  Steric height anomaly is the vertical integral of the specific-volume anomaly:

      h' = ∫ (−V'_sp / g) dp ,     V'_sp = 1/ρ − 1/ρ_ref

  where ρ = rhoConst + RHOAnoma is the model's in-situ density and ρ_ref is a standard
  reference profile (JMD95 at S_r=35, θ_r=0). Integrated from a sea pressure p_top (0 dbar,
  the surface) DOWN to a reference level p_r (2000 dbar): steric height is defined relative
  to that reference depth. Warm/fresh (light) columns stand higher; cold/salty lower.

  Decomposition (recompute density holding one of S/θ at its reference):
      thermosteric: 1/ρ(S_r, θ)  − 1/ρ_ref     (temperature contribution)
      halosteric:   1/ρ(S,   θ_r) − 1/ρ_ref     (salinity contribution)
  These sum to ≈ the full steric anomaly (a linearization about S_r/θ_r; small residual).

WHY VENDORED jmd95:
  The base steric integral needs NO equation of state (it uses the model's own RHOAnoma).
  But the reference profile ρ_ref and the thermo/halo split DO need a T,S→ρ EOS. gsw
  (TEOS-10) is not installed and ecco_v4_py has no EOS, so we vendor the canonical MITgcm
  JMD95 (`ecco_common/vendor/jmd95.py`, pinned) — the SAME EOS ECCO uses internally, so the
  reference profile is consistent with RHOAnoma. densjmd95 wants pressure in DBAR, while our
  reference pressure is in Pa, hence the 1e-4 Pa→dbar factor (faithful to the tutorial).

VERIFICATION (see references/acceptance.md, docs/verify.md):
  Rung-1 N/A for the integral, but the vendored EOS self-tests against its published check
  value (1041.83267). Correctness rests on: reproducing the tutorial's steric field (Rung 2);
  thermo+halo ≈ full steric (sum-of-parts, Rung 5a); and steric height ≈ SSH spatially
  (Rung 5b — an INDEPENDENT check against a different collection, the tutorial's headline
  result). All automated in test_steric.py.

Run with the venv python:
    .venv/bin/python run.py 2000-01
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "ecco-common"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "ecco-common", "vendor"))
import ecco_preflight  # noqa: E402
ecco_preflight.ensure_env("compute-steric-height")  # clear msg if env is unhealthy
from ecco_common import load_grid, load_field, canon as _canon  # noqa: E402
from jmd95 import densjmd95                     # vendored MITgcm JMD95 EOS  # noqa: E402

DENSPRESS = "ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4"
TEMPSALT = "ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4"
SSH = "ECCO_L4_SSH_LLC0090GRID_MONTHLY_V4R4"

G = 9.81
RHO_CONST = 1029.0
S_R = 35.0            # reference salinity for the standard specific volume
THETA_R = 0.0         # reference potential temperature
P_R_DBAR = 2000.0     # reference level (steric height is relative to this depth)
P_TOP_DBAR = 0.0      # top of the integral (sea surface)

# Physical-sanity bounds (Layer 3), calibrated against Jan-2000 data (see acceptance.md).
STERIC_ABS_MAX = 4.0          # m; global-mean-removed steric anomaly is O(0.1-2 m), with
                              # local extrema to ~3+ m near strong fronts/marginal seas
                              # (Jan-2000 real range ≈ [-3.2, 2.2] m). 4.0 rejects gross error.
SUMPARTS_RESID_MAX = 0.15     # m; median |full - (thermo+halo)| tolerance (linearization)


def _log(msg=""):
    print(msg, flush=True)


def reference_pressures(ds_grid):
    """Reference pressures (Pa) at cell centers and at the vertical cell faces (k_u, k_l),
    clipped to the ocean bottom (so a column can't integrate below the seafloor)."""
    press_ref = G * (-ds_grid.Z) * RHO_CONST                 # centers (k), Pa
    press_ref_k_u = G * (-ds_grid.Zu) * RHO_CONST            # upper faces (k_u)
    press_ref_k_l = G * (-ds_grid.Zl) * RHO_CONST            # lower faces (k_l)
    press_ref_bot = G * ds_grid.Depth * RHO_CONST            # seafloor
    press_ref_k_u = press_ref_k_u.where(press_ref_k_u < press_ref_bot, press_ref_bot)
    press_ref_k_l = press_ref_k_l.where(press_ref_k_l < press_ref_bot, press_ref_bot)
    return press_ref, press_ref_k_u, press_ref_k_l


def specvol_standard_profile(press_ref):
    """Reference specific volume 1/ρ_ref(S_r, θ_r, p) as a function of depth (dim k).
    JMD95 wants pressure in dbar; press_ref is in Pa → multiply by 1e-4."""
    import xarray as xr
    rho_ref = densjmd95(S_R, THETA_R, (1.0e-4) * press_ref.values)
    return xr.DataArray(1.0 / rho_ref, dims=press_ref.dims)


def dp_integrate(ds_grid, ds_ssh, press_ref_k_u, press_ref_k_l,
                 p_top_dbar=P_TOP_DBAR, p_r_dbar=P_R_DBAR):
    """Pressure-integration thickness (Pa) per cell, between the reference bounds
    [p_top, p_r], with cells outside that range contributing zero. Gated by hFacC (partial
    bottom cells) and scaled by the z* factor rstarfac = 1 + ETAN/Depth."""
    import xarray as xr
    p_top = 1.0e4 * p_top_dbar
    p_r = 1.0e4 * p_r_dbar

    def _clip(pf):
        return pf.where(pf > p_top, p_top).where(pf < p_r, p_r)

    dp = _clip(press_ref_k_l).values - _clip(press_ref_k_u).values
    dp = ds_grid.hFacC * xr.DataArray(dp, dims=["k", "tile", "j", "i"])   # partial cells
    rstarfac = 1.0 + (ds_ssh.ETAN / ds_grid.Depth)                        # z* scaling
    return _canon(rstarfac * dp)


def steric_height(specvol_anom, dp):
    """h' = ∫ (−V'_sp/g) dp, summed over k → steric height anomaly (m) at each column."""
    h = (-(specvol_anom / G) * dp).sum("k")
    h.name = "steric_height_anom"
    h.attrs.update({"units": "m", "long_name": "steric height anomaly"})
    return _canon(h)


def _area_weighted_globmean(field2d, weight2d):
    """Area-weighted mean of a 2-D (tile,j,i[,time]) field over weight2d (e.g. rA*unmasked)."""
    import numpy as np
    num = float((weight2d * field2d).sum().values)
    den = float(weight2d.sum().values)
    return num / den if den != 0 else np.nan


def remove_global_mean(h, ds_grid, press_ref_k_u, p_r_dbar=P_R_DBAR):
    """Subtract the area-weighted global mean, excluding land and 'too-shallow' columns that
    never reach the reference level p_r (their steric height is undefined vs p_r)."""
    p_r = 1.0e4 * p_r_dbar
    land_surf = (~ds_grid.maskC.astype(bool)).isel(k=0)
    too_shallow = (press_ref_k_u.isel(k_u=-1) < p_r)            # deepest face < p_r
    unmasked = (~land_surf) & (~too_shallow)
    weight = unmasked * ds_grid.rA
    gm = _area_weighted_globmean(h, weight)
    return _canon(h - gm), unmasked, gm


def decompose(ds_ts, press_ref, specvol_std, dp):
    """Thermosteric and halosteric height anomalies (m) via JMD95, holding S or θ at ref."""
    import numpy as np
    import xarray as xr
    # broadcast reference pressure (k) across the full T/S field (time,k,tile,j,i)
    press_expanded = _canon(press_ref * xr.ones_like(ds_ts.THETA))
    p_dbar = (1.0e-4) * press_expanded.values

    theta = _canon(ds_ts.THETA)
    salt = _canon(ds_ts.SALT)
    sv_thermo = xr.DataArray(1.0 / densjmd95(S_R, theta.values, p_dbar), dims=theta.dims,
                             coords=theta.coords)          # vary θ, hold S=S_r
    sv_halo = xr.DataArray(1.0 / densjmd95(salt.values, THETA_R, p_dbar), dims=salt.dims,
                           coords=salt.coords)             # vary S, hold θ=θ_r
    thermo = steric_height(_canon(sv_thermo) - specvol_std, dp)
    halo = steric_height(_canon(sv_halo) - specvol_std, dp)
    thermo.name, halo.name = "thermosteric_hgt_anom", "halosteric_hgt_anom"
    return thermo, halo


def validate(h_anom, thermo, halo, unmasked, log=_log):
    """Runtime validation trail. Returns True if all mandatory checks pass."""
    import numpy as np
    ok = True
    log("  Validation trail:")

    # L1 — grid position + units: steric height on tracer columns (i,j), units m.
    on_tracer = {"i", "j"}.issubset(set(h_anom.dims))
    units_ok = h_anom.attrs.get("units") == "m"
    l1 = on_tracer and units_ok
    log(f"    [{'✓' if l1 else '✗'}] L1 input: steric height on tracer points {tuple(h_anom.dims)}, "
        f"units={h_anom.attrs.get('units')!r}")
    ok = ok and l1

    # L1b — finite in the valid (unmasked, deep-enough, wet) region. Restrict to the mask
    # via xarray alignment (handles dim matching / broadcasting robustly), so land and
    # too-shallow columns are legitimately excluded from the finiteness check.
    umb = unmasked.astype(bool)
    valid = h_anom.where(umb)                       # NaN outside the valid region
    n_bad = int(((~np.isfinite(h_anom)) & umb).sum().values)
    l1b = (n_bad == 0)
    log(f"    [{'✓' if l1b else '✗'}] L1 finite: {n_bad} non-finite value(s) in valid columns "
        f"(expect 0)")
    ok = ok and l1b

    # L3 — physical bounds on the (global-mean-removed) steric anomaly, valid region only.
    hmax = float(np.nanmax(np.abs(valid.values)))
    l3 = hmax <= STERIC_ABS_MAX
    log(f"    [{'✓' if l3 else '✗'}] L3 bounds: |steric anomaly| ≤ {STERIC_ABS_MAX} m "
        f"(got max {hmax:.2f})")
    ok = ok and l3

    # L4 — closure: N/A.
    log("    [–] L4 closure: not applicable (diagnostic height, not a budget)")

    # Sum-of-parts residual (L5a, reported here for the live trail): thermo+halo ≈ full.
    resid = float(np.nanmedian(np.abs((h_anom - (thermo + halo)).where(umb).values)))
    l5a = resid <= SUMPARTS_RESID_MAX
    log(f"    [{'✓' if l5a else '✗'}] L5 sum-of-parts: median|full − (thermo+halo)| = "
        f"{resid:.3f} m (≤ {SUMPARTS_RESID_MAX}; linearization about S_r/θ_r)")
    ok = ok and l5a

    log("    [i] Correctness: test_steric.py checks the EOS check-value, tutorial")
    log("        reproduction, and steric ≈ SSH spatially (independent, vs a different field).")
    return ok


def compute_all(ds_grid, ds_dp, ds_ts, ds_ssh):
    """Full pipeline → (steric_anom, thermo, halo, unmasked), ALL global-mean-removed over
    the same valid region so they are directly comparable (the tutorial de-means each
    separately before comparing full vs thermo+halo)."""
    press_ref, pku, pkl = reference_pressures(ds_grid)
    sv_std = specvol_standard_profile(press_ref)
    dens = _canon(RHO_CONST + ds_dp.RHOAnoma)
    specvol_anom = _canon(1.0 / dens - sv_std)
    dp = dp_integrate(ds_grid, ds_ssh, pku, pkl)

    h = steric_height(specvol_anom, dp)
    h_gm, unmasked, _ = remove_global_mean(h, ds_grid, pku)

    thermo, halo = decompose(ds_ts, press_ref, sv_std, dp)
    # de-mean thermo/halo over the SAME valid region, so full ≈ thermo+halo holds.
    weight = unmasked * ds_grid.rA
    thermo = _canon(thermo - _area_weighted_globmean(thermo, weight))
    halo = _canon(halo - _area_weighted_globmean(halo, weight))
    thermo.name, halo.name = "thermosteric_hgt_anom", "halosteric_hgt_anom"
    thermo.attrs.update({"units": "m"}); halo.attrs.update({"units": "m"})
    return h_gm, thermo, halo, unmasked


def main(argv):
    if not argv:
        print("usage: run.py <YYYY-MM>   (steric height anomaly + thermo/halo split)")
        return 2
    ym = argv[0]

    _log("=" * 64)
    _log("compute-steric-height (Recipe 3-steric)")
    _log("=" * 64)
    _log("Loading grid + density/pressure + temp/salinity + SSH ...")
    ds_grid, _ = load_grid(log=_log)
    ds_dp = load_field(DENSPRESS, months=[ym], log=_log)
    ds_ts = load_field(TEMPSALT, months=[ym], log=_log)
    ds_ssh = load_field(SSH, months=[ym], log=_log)

    _log(f"\nComputing steric height for {ym} "
         f"(0→{P_R_DBAR:.0f} dbar, ref S={S_R} θ={THETA_R}) ...")
    h_gm, thermo, halo, unmasked = compute_all(ds_grid, ds_dp, ds_ts, ds_ssh)

    import numpy as np
    um = unmasked.astype(bool)
    _log(f"  steric anomaly (global-mean-removed): "
         f"min {float(np.nanmin(h_gm.where(um).values)):.2f} m, "
         f"max {float(np.nanmax(h_gm.where(um).values)):.2f} m")

    ok = validate(h_gm, thermo, halo, unmasked)
    _log("")
    _log("=" * 64)
    _log("VALIDATION: all runtime checks passed ✓" if ok
         else "VALIDATION: a check FAILED ✗ — do not trust the result.")
    _log("Correctness (EOS check-value; tutorial reproduction; steric≈SSH) → test_steric.py.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
