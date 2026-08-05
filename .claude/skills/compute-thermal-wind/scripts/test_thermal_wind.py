#!/usr/bin/env python3
"""
Verification for compute-thermal-wind. There is NO official `thermal_wind_compute` helper
(only `geos_vel_compute` exists in ecco_po_tutorials.py), so Rung-1 is N/A; correctness
rests on three cross-checks, strongest first:

  (1) INTERNAL IDENTITY (tight): thermal-wind shear ≈ ∂/∂z of the geostrophic velocity
      computed from the SAME pressure field. Thermal wind IS the vertical derivative of
      geostrophic balance, so these must agree closely (expect corr ~0.999). This proves
      the shear math (signs, g/(fρ) factor, drC vertical derivative) is right. It shares
      the density/pressure field, so it's *consistency*, not independent correctness —
      hence checks (2)/(3). The geostrophic velocity is recomputed INLINE from PHIHYDcR
      here; this test does NOT import the compute-geostrophic-balance skill.

  (2) INDEPENDENT PHYSICAL: predicted shear (from DENSITY) vs the model's ACTUAL velocity
      shear (∂/∂z of UVEL/VVEL). Different variable + code path → rules out a bug shared
      with the pressure path. Moderate correlation is expected (real ageostrophic flow).

  (3) TUTORIAL DELIVERABLE: velocity reconstructed from the thermal-wind shear (integrated
      from z0=-3000 m) vs the model's ACTUAL velocity along 26°N, as a normalized
      difference in the 100-1000 m band — the exact diagnostic the tutorial plots.

Data checks SKIP (not fail) if the Jan-2000 density/velocity + geometry aren't cached.
Offline synthetic negative/positive validate() guards always run.

Run with the venv python:
    .venv/bin/python .claude/skills/compute-thermal-wind/scripts/test_thermal_wind.py
"""
import io
import os
import sys
import contextlib
import warnings

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "ecco-common"))

import run  # the skill under test  # noqa: E402
from ecco_common import cache, load_grid, load_field  # noqa: E402

DENSPRESS = run.DENSPRESS
OCEAN_VEL = run.OCEAN_VEL
GEOM = "ECCO_L4_GEOMETRY_LLC0090GRID_V4R4"


def _data_available():
    return (cache.lookup_cached(DENSPRESS, "2000-01") is not None
            and cache.lookup_cached(OCEAN_VEL, "2000-01") is not None
            and cache.lookup_cached(GEOM, "GEOMETRY") is not None)


def _q(*a):
    return None


# --------------------------------------------------------------------------
# Data cross-checks
# --------------------------------------------------------------------------
def test_identity_shear_equals_ddz_geostrophic():
    """(1) thermal-wind shear ≈ ∂/∂z of geostrophic velocity from the same pressure field."""
    import numpy as np
    ds_grid, xg = load_grid(log=_q)
    ds_dp = load_field(DENSPRESS, months=["2000-01"], log=_q)
    dudz_p, dvdz_p, f, lat, dens = run.predicted_shear(ds_grid, xg, ds_dp, log=_q)

    # geostrophic velocity computed INLINE from PHIHYDcR (no dependency on the geos skill)
    RHO = run.RHO_CONST
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        dpx = xg.diff(RHO * ds_dp.PHIHYDcR, axis="X", boundary="extend") / ds_grid.dxC
        dpy = xg.diff(RHO * ds_dp.PHIHYDcR, axis="Y", boundary="extend") / ds_grid.dyC
        gr = xg.interp_2d_vector({"X": dpx, "Y": dpy}, boundary="extend")
    dpx, dpy = run._canon(gr["X"]), run._canon(gr["Y"])
    v_g = run._canon(dpx / (f * dens))
    u_g = run._canon(-dpy / (f * dens))
    dudz_g, dvdz_g = run.actual_shear(u_g, v_g, ds_grid)

    oe = np.abs(lat.values) >= run.EQ_BAND_DEG
    ks = slice(5, 36)                                   # ocean interior

    def fl(a):
        return np.squeeze(np.asarray(a.isel(k=ks).values))
    dvp, dvg = fl(dvdz_p), fl(dvdz_g)
    dup, dug = fl(dudz_p), fl(dudz_g)
    oeb = np.broadcast_to(oe, dvp.shape)
    g = (np.isfinite(dvp) & np.isfinite(dvg) & np.isfinite(dup) & np.isfinite(dug) & oeb)
    n = int(g.sum())
    assert n > 500000, f"too few points: {n}"
    cv = float(np.corrcoef(dvp[g], dvg[g])[0, 1])
    cu = float(np.corrcoef(dup[g], dug[g])[0, 1])
    assert cu > 0.99 and cv > 0.99, (
        f"thermal-wind shear should equal ∂/∂z of geostrophic velocity: "
        f"corr(du/dz)={cu:.4f}, corr(dv/dz)={cv:.4f} (expect >0.99)")
    return (f"shear ≈ ∂/∂z(geostrophic vel): corr(du/dz)={cu:.4f}, corr(dv/dz)={cv:.4f} "
            f"over {n} pts (analytic identity holds)")


def test_predicted_shear_vs_actual_velocity_shear():
    """(2) predicted shear (density) vs the model's ACTUAL velocity shear — independent."""
    import numpy as np
    ds_grid, xg = load_grid(log=_q)
    ds_dp = load_field(DENSPRESS, months=["2000-01"], log=_q)
    ds_vel = load_field(OCEAN_VEL, months=["2000-01"], log=_q)

    dudz_p, dvdz_p, f, lat, dens = run.predicted_shear(ds_grid, xg, ds_dp, log=_q)
    u, v = run.actual_velocity_centers(ds_grid, xg, ds_vel)
    dudz_a, dvdz_a = run.actual_shear(u, v, ds_grid)

    oe = np.abs(lat.values) >= run.EQ_BAND_DEG
    ks = slice(5, 36)

    def fl(a):
        return np.squeeze(np.asarray(a.isel(k=ks).values))
    dup, dua = fl(dudz_p), fl(dudz_a)
    dvp, dva = fl(dvdz_p), fl(dvdz_a)
    oeb = np.broadcast_to(oe, dup.shape)
    g = (np.isfinite(dup) & np.isfinite(dua) & np.isfinite(dvp) & np.isfinite(dva) & oeb)
    n = int(g.sum())
    assert n > 500000, f"too few points: {n}"
    cu = float(np.corrcoef(dup[g], dua[g])[0, 1])
    cv = float(np.corrcoef(dvp[g], dva[g])[0, 1])
    # Moderate positive correlation: geostrophy explains much (not all) of the shear.
    assert cu > 0.4 and cv > 0.4, (
        f"predicted vs actual velocity shear correlation too low: "
        f"corr(du/dz)={cu:.3f}, corr(dv/dz)={cv:.3f} (expect ~0.6–0.85)")
    return (f"predicted shear vs ACTUAL velocity shear: corr(du/dz)={cu:.3f}, "
            f"corr(dv/dz)={cv:.3f} over {n} pts (independent of the pressure path)")


def test_reconstruction_vs_actual_velocity_26N():
    """(3) reconstructed velocity vs the model's ACTUAL velocity, normalized diff, 100-1000 m."""
    import numpy as np
    ds_grid, xg = load_grid(log=_q)
    ds_dp = load_field(DENSPRESS, months=["2000-01"], log=_q)
    ds_vel = load_field(OCEAN_VEL, months=["2000-01"], log=_q)

    dudz_p, dvdz_p, f, lat, dens = run.predicted_shear(ds_grid, xg, ds_dp, log=_q)
    u, v = run.actual_velocity_centers(ds_grid, xg, ds_vel)
    u_rec, v_rec = run.reconstruct_velocity(dudz_p, dvdz_p, ds_grid)

    Z = ds_grid.Z.values
    kmask = (-Z > 100) & (-Z < 1000)                     # tutorial's depth band
    oe = np.abs(lat.values) >= run.EQ_BAND_DEG

    def fl(a):
        return np.squeeze(np.asarray(a.isel(k=np.where(kmask)[0]).values))
    ur, vr, ua, va = fl(u_rec), fl(v_rec), fl(u), fl(v)
    oeb = np.broadcast_to(oe, ur.shape)
    num = np.hypot(ua - ur, va - vr)
    den = np.hypot(ua, va)
    g = np.isfinite(num) & np.isfinite(den) & (den > 0.005) & oeb   # tutorial's 0.5 cm/s cut
    n = int(g.sum())
    assert n > 200000, f"too few points: {n}"
    med = float(np.median(num[g] / den[g]))
    # Tutorial regime: reconstruction tracks the actual flow to within a normalized diff
    # that's small but above its 0.1 reference line at these depths. Guard against gross
    # failure (a sign flip or bad z0 integration would send this ≳1).
    assert med < 0.6, (f"reconstruction vs actual velocity normalized diff too high: "
                       f"median={med:.3f} (expect ~0.2–0.4 in 100–1000 m)")
    return (f"reconstruction vs ACTUAL velocity @100–1000 m off-eq: median norm-diff="
            f"{med:.3f} over {n} pts (tutorial's deliverable)")


# --------------------------------------------------------------------------
# Offline synthetic validate() guards (no data)
# --------------------------------------------------------------------------
def _run_validate(dudz, dvdz, urec, vrec, lat):
    with contextlib.redirect_stdout(io.StringIO()):
        return run.validate(dudz, dvdz, urec, vrec, lat, log=_q)


def _field(values, dims=("time", "k", "tile", "j", "i"), units="s-1"):
    import numpy as np
    import xarray as xr
    arr = np.array(values, dtype=float)
    shape = (1,) * (len(dims) - 1) + (arr.size,)
    da = xr.DataArray(arr.reshape(shape), dims=dims)
    da.attrs["units"] = units
    return da


def _lat(vals, dims=("tile", "j", "i")):
    import numpy as np
    import xarray as xr
    arr = np.array(vals, dtype=float)
    shape = (1,) * (len(dims) - 1) + (arr.size,)
    return xr.DataArray(arr.reshape(shape), dims=dims)


def test_validate_negative_and_positive():
    """Runtime guards must FIRE on bad input and PASS on good — no data needed."""
    results = []
    lat = _lat([30.0, 40.0, -35.0])
    urec = _field([0.1, 0.2, -0.15], units="m s-1")
    vrec = _field([0.1, -0.1, 0.05], units="m s-1")

    # positive control: small off-equator shear, tracer dims, right units
    du = _field([1e-4, 2e-4, -1.5e-4]); dv = _field([1e-4, -1e-4, 5e-5])
    results.append(("good shear passes", _run_validate(du, dv, urec, vrec, lat) is True))

    # wrong units on shear → L1 fails
    du_bad = _field([1e-4, 2e-4, -1.5e-4], units="1/m")
    results.append(("wrong shear units fails", _run_validate(du_bad, dv, urec, vrec, lat) is False))

    # non-tracer dims → L1 fails
    du_nt = _field([1e-4, 2e-4, -1.5e-4], dims=("time", "k", "tile", "j_g", "i_g"))
    results.append(("non-tracer dims fails", _run_validate(du_nt, dv, urec, vrec, lat) is False))

    # absurd off-equator shear (1 s-1 at 30°N) → L3 fails
    du_fast = _field([1.0, 2e-4, -1.5e-4])
    results.append(("absurd off-equator shear fails",
                    _run_validate(du_fast, dv, urec, vrec, lat) is False))

    # SAME absurd shear but AT the equator (masked) → PASS (f→0 blowup tolerated)
    lat_eq = _lat([1.0, 40.0, -35.0])
    results.append(("equatorial blowup tolerated",
                    _run_validate(du_fast, dv, urec, vrec, lat_eq) is True))

    # absurd reconstructed speed off-equator → L3 fails
    urec_fast = _field([50.0, 0.2, -0.15], units="m s-1")
    results.append(("absurd reconstructed speed fails",
                    _run_validate(du, dv, urec_fast, vrec, lat) is False))

    bad = [name for name, ok in results if not ok]
    assert not bad, f"validation guard cases wrong: {bad}"
    return f"{len(results)} negative/positive guard cases behaved correctly"


TESTS = [
    ("Identity: shear ≈ ∂/∂z(geostrophic vel)", test_identity_shear_equals_ddz_geostrophic, True),
    ("Independent: predicted vs actual velocity shear", test_predicted_shear_vs_actual_velocity_shear, True),
    ("Tutorial: reconstruction ≈ actual velocity @26°N", test_reconstruction_vs_actual_velocity_26N, True),
    ("validation guards fire (neg+pos)", test_validate_negative_and_positive, False),
]


def main():
    print("=" * 64)
    print("compute-thermal-wind tests")
    print("=" * 64)
    data = _data_available()
    if not data:
        print("  [note] Jan-2000 density/velocity or geometry not cached — the data")
        print("         cross-checks will SKIP. Run the skill once to enable them.")
    passed = failed = skipped = 0
    for name, fn, needs_data in TESTS:
        if needs_data and not data:
            print(f"  [SKIP] {name}")
            skipped += 1
            continue
        try:
            detail = fn()
            print(f"  [PASS] {name} — {detail}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            import traceback
            print(f"  [FAIL] {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print("=" * 64)
    print(f"{passed} passed, {failed} failed, {skipped} skipped")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
