#!/usr/bin/env python3
"""
Rung-1 verification for compute-geostrophic-balance: our u_g/v_g must match the
OFFICIAL tutorial helper `ecco_po_tutorials.geos_vel_compute` to tight tolerance.

This is the strongest correctness evidence available for this skill (see docs/verify.md):
we compare against the tutorial authors' own code, not against our own reasoning.

Needs the Jan-2000 density/pressure file + geometry cached (run the skill once, or
load-field, first). If they aren't cached, the Rung-1 test SKIPS (not fails) so the
offline-safe portions can still run. Also includes negative/positive validation tests
that need no data.

Run with the venv python:
    .venv/bin/python .claude/skills/compute-geostrophic-balance/scripts/test_geostrophic.py
Exit 0 iff all run tests pass.
"""
import io
import os
import sys
import contextlib

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "..", "ecco-common"))
sys.path.insert(0, os.path.join(_HERE, "..", "..", "ecco-common", "vendor"))

import run  # the skill under test  # noqa: E402
from ecco_common import cache, load_grid, load_field  # noqa: E402

DENSPRESS = "ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4"
GEOM = "ECCO_L4_GEOMETRY_LLC0090GRID_V4R4"


def _data_available():
    return (cache.lookup_cached(DENSPRESS, "2000-01") is not None
            and cache.lookup_cached(GEOM, "GEOMETRY") is not None)


def test_rung1_matches_official_helper():
    """Our u_g/v_g == ecco_po_tutorials.geos_vel_compute, off-equator, to tight tol."""
    import numpy as np
    import ecco_po_tutorials as ept   # the vendored official helper

    dp_file = cache.lookup_cached(DENSPRESS, "2000-01")
    grid_file = cache.lookup_cached(GEOM, "GEOMETRY")

    # Reference: the official helper, straight from filenames.
    ref = ept.geos_vel_compute(dp_file, grid_filename=grid_file)

    # Ours: via the skill's compute function on the same data.
    ds_grid, xgcm_grid = load_grid(log=lambda *a: None)
    ds_dp = load_field(DENSPRESS, months=["2000-01"], log=lambda *a: None)
    u_g, v_g, f, lat, dens = run.compute_geostrophic(ds_grid, xgcm_grid, ds_dp,
                                                     log=lambda *a: None)

    # Align: reference has no explicit time dim handling difference; compare values.
    ru = np.asarray(ref.u_g.values)
    rv = np.asarray(ref.v_g.values)
    ou = np.asarray(u_g.values)
    ov = np.asarray(v_g.values)
    # squeeze any singleton time dim so shapes line up
    ru, rv, ou, ov = [np.squeeze(a) for a in (ru, rv, ou, ov)]
    assert ru.shape == ou.shape, f"shape mismatch u: {ru.shape} vs {ou.shape}"

    # Compare where BOTH are finite (land/equator produce NaN/inf in both).
    finite = np.isfinite(ru) & np.isfinite(ou) & np.isfinite(rv) & np.isfinite(ov)
    n = int(finite.sum())
    assert n > 100000, f"suspiciously few comparable points: {n}"
    du = np.abs(ru[finite] - ou[finite])
    dv = np.abs(rv[finite] - ov[finite])
    max_du = float(du.max())
    max_dv = float(dv.max())
    # Same formula, same data → expect agreement to floating-point/interp noise.
    assert max_du < 1e-9 and max_dv < 1e-9, (
        f"u_g/v_g differ from official helper: max|Δu|={max_du:.2e}, "
        f"max|Δv|={max_dv:.2e} over {n} points")
    return f"matched official geos_vel_compute over {n} pts (max|Δ|<1e-9 m/s)"


def _run_validate(u_g, v_g, lat):
    with contextlib.redirect_stdout(io.StringIO()):
        return run.validate(u_g, v_g, lat, log=lambda *a: None)


def _synthetic_field(values, dims=("time", "k", "tile", "j", "i"), units="m s-1"):
    """Values vary along the LAST dim ('i'); all others are size 1. Pairs with
    _lat_array (also varying along 'i') so tile/j sizes match and broadcast like real
    ECCO data (avoids a spurious alignment error in the test)."""
    import numpy as np
    import xarray as xr
    arr = np.array(values, dtype=float)
    shape = (1,) * (len(dims) - 1) + (arr.size,)
    da = xr.DataArray(arr.reshape(shape), dims=dims)
    da.attrs["units"] = units
    return da


def _lat_array(vals, dims=("tile", "j", "i")):
    import numpy as np
    import xarray as xr
    arr = np.array(vals, dtype=float)
    shape = (1,) * (len(dims) - 1) + (arr.size,)   # vary along 'i' to match fields
    return xr.DataArray(arr.reshape(shape), dims=dims)


def test_validate_negative_and_positive():
    """The runtime guards must FIRE on bad input and PASS on good — no data needed."""
    import numpy as np
    results = []

    # positive control: small off-equator velocities, tracer dims, right units
    ug = _synthetic_field([0.1, 0.2, -0.15]); vg = _synthetic_field([0.1, -0.1, 0.05])
    lat = _lat_array([30.0, 40.0, -35.0])
    results.append(("good geostrophic passes", _run_validate(ug, vg, lat) is True))

    # wrong units → L1 fails
    ug_bad = _synthetic_field([0.1, 0.2, -0.15], units="cm/s")
    results.append(("wrong units fails", _run_validate(ug_bad, vg, lat) is False))

    # non-tracer dims → L1 fails
    ug_nt = _synthetic_field([0.1, 0.2, -0.15], dims=("time", "k", "tile", "j_g", "i_g"))
    results.append(("non-tracer dims fails", _run_validate(ug_nt, vg, lat) is False))

    # absurd off-equator speed (50 m/s at 30°N) → L3 fails
    ug_fast = _synthetic_field([50.0, 0.2, -0.15])
    results.append(("absurd off-equator speed fails", _run_validate(ug_fast, vg, lat) is False))

    # SAME absurd speed but AT the equator (masked) → should PASS (equatorial blowup ok)
    ug_eqfast = _synthetic_field([50.0, 0.2, -0.15])
    lat_eq = _lat_array([1.0, 40.0, -35.0])   # first cell now on the equator
    results.append(("equatorial blowup tolerated", _run_validate(ug_eqfast, vg, lat_eq) is True))

    bad = [name for name, ok in results if not ok]
    assert not bad, f"validation guard cases wrong: {bad}"
    return f"{len(results)} negative/positive guard cases behaved correctly"


def test_independent_corroboration_vs_model_velocity():
    """INDEPENDENT correctness check (rules out a shared bug with the reference):
    compare our geostrophic u_g/v_g to the model's ACTUAL UVEL/VVEL in the ocean
    interior (~350 m), where geostrophy should dominate. This is stronger evidence than
    the Rung-1 helper match, because UVEL/VVEL come from a completely different variable/
    computation, not the pressure field. Expected (per the tutorial + adversarial
    review): high correlation (~0.99) and small normalized difference at depth.

    Needs UVEL/VVEL (Jan 2000) in addition to density/pressure + geometry.
    """
    import numpy as np
    vel_file = cache.lookup_cached("ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4", "2000-01")
    if vel_file is None:
        # download it (small) so this test is self-sufficient
        load_field("ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4", months=["2000-01"],
                   log=lambda *a: None)

    ds_grid, xgcm_grid = load_grid(log=lambda *a: None)
    ds_dp = load_field(DENSPRESS, months=["2000-01"], log=lambda *a: None)
    u_g, v_g, f, lat, dens = run.compute_geostrophic(ds_grid, xgcm_grid, ds_dp,
                                                     log=lambda *a: None)

    ds_vel = load_field("ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4", months=["2000-01"],
                        log=lambda *a: None)
    # interpolate actual staggered velocities to tracer centers (same frame as u_g/v_g)
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vel_c = xgcm_grid.interp_2d_vector(
            {"X": ds_vel.UVEL, "Y": ds_vel.VVEL}, boundary="extend")
    u_act, v_act = vel_c["X"], vel_c["Y"]

    k = 20   # ~350 m: well below the Ekman layer, geostrophy should dominate
    eqmask = np.abs(lat.values) >= run.EQ_BAND_DEG
    def _flat(a):
        arr = np.squeeze(np.asarray(a.isel(k=k).values))
        return arr
    ug = _flat(u_g); vg = _flat(v_g); ua = _flat(u_act); va = _flat(v_act)
    good = (np.isfinite(ug) & np.isfinite(vg) & np.isfinite(ua) & np.isfinite(va)
            & eqmask)
    n = int(good.sum())
    assert n > 40000, f"too few comparison points: {n}"
    cu = float(np.corrcoef(ug[good], ua[good])[0, 1])
    cv = float(np.corrcoef(vg[good], va[good])[0, 1])
    # normalized difference of the velocity vector
    num = np.hypot(ua[good] - ug[good], va[good] - vg[good])
    den = np.hypot(ua[good], va[good])
    med_norm = float(np.median(num[den > 0.005] / den[den > 0.005]))
    assert cu > 0.9 and cv > 0.9, (
        f"geostrophic vs actual velocity correlation too low at ~350 m: "
        f"corr(u)={cu:.3f}, corr(v)={cv:.3f} (expect ~0.99)")
    assert med_norm < 0.25, (
        f"median normalized diff vs actual velocity too high: {med_norm:.3f} "
        f"(expect ~0.03 at 350 m)")
    return (f"vs ACTUAL model velocity at ~350 m: corr(u)={cu:.3f}, corr(v)={cv:.3f}, "
            f"median norm-diff={med_norm:.3f} over {n} pts (rules out shared bug)")


TESTS = [
    ("Rung 1: match official geos_vel_compute", test_rung1_matches_official_helper, True),
    ("Independent: geostrophic ≈ model velocity @350m", test_independent_corroboration_vs_model_velocity, True),
    ("validation guards fire (neg+pos)", test_validate_negative_and_positive, False),
]


def main():
    print("=" * 64)
    print("compute-geostrophic-balance tests")
    print("=" * 64)
    data = _data_available()
    if not data:
        print("  [note] Jan-2000 density/pressure or geometry not cached — the Rung-1")
        print("         data test will SKIP. Run the skill once to enable it.")
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
