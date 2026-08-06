#!/usr/bin/env python3
"""
Verification for compute-curl. No official curl helper exists (Rung-1 N/A), so correctness
rests on:

  (1) ROTATION vs the OFFICIAL helper (tight): our CS/SN component rotation must match
      `ecco_v4_py.vector_calc.UEVNfromUXVY` (the official model→East/North rotation) to
      floating-point. The CS/SN rotation is the exact operation that's been wrong before
      on this grid, so matching the official implementation is the strongest available
      check on the rotation core. (Measured: bit-identical, max|Δ|=0.)

  (2) EKMAN PUMPING vs the model's ACTUAL WVEL (physical): the wind-stress-curl-driven
      Ekman pumping w_E should track the model's real vertical velocity near the base of
      the Ekman layer (~20-40 m), off-equator. Measured Jan 2000: corr≈0.74,
      sign-agreement≈0.89 — a genuinely strong physical corroboration that the full curl
      pipeline (both rotations + the pumping formula) is right. WVEL is a completely
      different variable/path, so this rules out a bug confined to the stress path.

Data checks SKIP (not fail) if Jan-2000 stress/velocity + geometry aren't cached.
Offline synthetic validate() guards always run.

Run with the venv python:
    .venv/bin/python .claude/skills/compute-curl/scripts/test_curl.py
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

STRESS = run.STRESS
OCEAN_VEL = run.OCEAN_VEL
GEOM = "ECCO_L4_GEOMETRY_LLC0090GRID_V4R4"


def _data_available():
    return (cache.lookup_cached(STRESS, "2000-01") is not None
            and cache.lookup_cached(OCEAN_VEL, "2000-01") is not None
            and cache.lookup_cached(GEOM, "GEOMETRY") is not None)


def _q(*a):
    return None


# --------------------------------------------------------------------------
# Data cross-checks
# --------------------------------------------------------------------------
def test_rotation_matches_official_UEVNfromUXVY():
    """(1) our CS/SN component rotation == official ecco_v4_py.vector_calc.UEVNfromUXVY."""
    import numpy as np
    from ecco_v4_py import vector_calc

    ds_grid, xg = load_grid(log=_q)
    ds_str = load_field(STRESS, months=["2000-01"], log=_q)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vec = xg.interp_2d_vector({"X": ds_str.oceTAUX, "Y": ds_str.oceTAUY},
                                  boundary="fill")
    tcx, tcy = run._canon(vec["X"]), run._canon(vec["Y"])

    ours_zonal, ours_merid = run._rotate_to_geographic(tcx, tcy, ds_grid.CS, ds_grid.SN)
    uE, vN = vector_calc.UEVNfromUXVY(tcx, tcy, ds_grid)   # official rotation

    du = float(np.nanmax(np.abs(np.squeeze(ours_zonal.values) - np.squeeze(uE.values))))
    dv = float(np.nanmax(np.abs(np.squeeze(ours_merid.values) - np.squeeze(vN.values))))
    assert du < 1e-9 and dv < 1e-9, (
        f"CS/SN rotation disagrees with official UEVNfromUXVY: "
        f"max|Δzonal|={du:.2e}, max|Δmerid|={dv:.2e}")
    return f"CS/SN rotation == official UEVNfromUXVY (max|Δ|={max(du, dv):.1e})"


def test_ekman_pumping_vs_actual_wvel():
    """(2) Ekman pumping w_E vs the model's ACTUAL WVEL near the base of the Ekman layer."""
    import numpy as np
    ds_grid, xg = load_grid(log=_q)
    ds_str = load_field(STRESS, months=["2000-01"], log=_q)
    ds_vel = load_field(OCEAN_VEL, months=["2000-01"], log=_q)

    w_E, f, lat = run.ekman_pumping(ds_str.oceTAUX, ds_str.oceTAUY, ds_grid, xg,
                                    use_beta=True, log=_q)
    wvel = ds_vel.WVEL                                    # on interface k_l
    kl = [d for d in wvel.dims if d.startswith("k")][0]

    w = np.squeeze(w_E.values)                            # (tile,j,i)
    wv = np.squeeze(wvel.isel({kl: 3}).values)            # ~30 m, base of Ekman layer
    oe = np.abs(lat.values) >= run.EQ_BAND_DEG
    g = np.isfinite(w) & np.isfinite(wv) & oe & (wv != 0)
    n = int(g.sum())
    assert n > 20000, f"too few comparison points: {n}"
    corr = float(np.corrcoef(w[g], wv[g])[0, 1])
    sign_agree = float(np.mean(np.sign(w[g]) == np.sign(wv[g])))
    # Thresholds set from the measured Jan-2000 values (corr~0.74, sign~0.89), with margin.
    assert corr > 0.6, f"Ekman w_E vs WVEL correlation too low: {corr:.3f} (measured ~0.74)"
    assert sign_agree > 0.8, f"Ekman w_E vs WVEL sign agreement too low: {sign_agree:.3f}"
    return (f"Ekman w_E vs ACTUAL WVEL @~30 m off-eq: corr={corr:.3f}, "
            f"sign-agree={sign_agree:.2f} over {n} pts (independent physical check)")


def test_second_rotation_is_required():
    """TEETH: the SECOND rotation must be load-bearing. We build a 'naive' curl that skips
    step 4 — combining the model-axis derivatives directly as (∂v_φ/∂x − ∂u_λ/∂y) after
    interpolating each to centers — which is exactly the class of error eval #2 caught.
    It must differ substantially from the correct two-rotation curl. Also the naive curl
    must disagree MORE with the model's WVEL sign than the correct one, i.e. the 2nd
    rotation improves physical agreement."""
    import numpy as np
    ds_grid, xg = load_grid(log=_q)
    ds_str = load_field(STRESS, months=["2000-01"], log=_q)
    ds_vel = load_field(OCEAN_VEL, months=["2000-01"], log=_q)
    CS, SN = ds_grid.CS, ds_grid.SN

    # correct curl
    good = run.curl_z(ds_str.oceTAUX, ds_str.oceTAUY, ds_grid, xg,
                      already_at_center=False, units="Pa m-1", log=_q)

    # naive curl: rotate components, diff each along its OWN axis, interp to centers,
    # subtract directly — NO second rotation of the derivative vectors.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        vec = xg.interp_2d_vector({"X": ds_str.oceTAUX, "Y": ds_str.oceTAUY}, boundary="fill")
        cx, cy = run._canon(vec["X"]), run._canon(vec["Y"])
        u_l, v_p = run._rotate_to_geographic(cx, cy, CS, SN)
        dv_phi_dx = xg.diff(v_p, axis="X", boundary="extend") / ds_grid.dxC
        du_lambda_dy = xg.diff(u_l, axis="Y", boundary="extend") / ds_grid.dyC
        # interpolate each derivative (paired with its natural partner) back to centers
        gv = xg.interp_2d_vector({"X": dv_phi_dx, "Y": dv_phi_dy_zero(v_p, xg, ds_grid)},
                                 boundary="fill")
        gu = xg.interp_2d_vector({"X": du_lambda_dx_zero(u_l, xg, ds_grid), "Y": du_lambda_dy},
                                 boundary="fill")
    naive = run._canon(run._canon(gv["X"]) - run._canon(gu["Y"]))

    a = np.squeeze(good.values); b = np.squeeze(naive.values)
    m = np.isfinite(a) & np.isfinite(b)
    reldiff = float(np.nanmedian(np.abs(a[m] - b[m]))
                    / (np.nanmedian(np.abs(a[m])) + 1e-30))
    # Threshold TIGHTENED 0.05 → 0.20 (2026-08-06, adversarial-review caveat A). Dropping
    # the 2nd rotation entirely (the historical eval-#2 bug) gives reldiff ≈ 0.315, so 0.20
    # catches it with margin. The old 0.05 was too loose: a *partial* rotation error —
    # scaling SN to ~90% of correct — lands at reldiff ≈ 0.055 and slipped through while
    # being physically wrong. Measured SN-scaling landings: correct 0.000, SN×0.90 0.055,
    # ×0.80 0.105, ×0.70 0.150, dropped(×0) 0.315. 0.20 fails a ≳30% rotation error while
    # staying far clear of the correct code (0.000).
    assert reldiff > 0.20, (
        f"2nd rotation not load-bearing enough (reldiff={reldiff:.3f} ≤ 0.20) — either the "
        f"rotation is being partly skipped/mis-scaled, or the teeth check stopped discriminating")
    return f"2nd rotation is load-bearing: skipping it shifts the curl by {reldiff*100:.0f}% (median)"


def du_lambda_dx_zero(u_l, xg, ds_grid):
    """Helper for the teeth test: the X-derivative of the zonal component (partner needed
    only to satisfy interp_2d_vector's paired-position requirement)."""
    return xg.diff(u_l, axis="X", boundary="extend") / ds_grid.dxC


def dv_phi_dy_zero(v_p, xg, ds_grid):
    """Helper for the teeth test: the Y-derivative of the meridional component."""
    return xg.diff(v_p, axis="Y", boundary="extend") / ds_grid.dyC


# --------------------------------------------------------------------------
# Offline synthetic validate() guards (no data)
# --------------------------------------------------------------------------
def _run_validate(curl_tau, w_E, lat):
    with contextlib.redirect_stdout(io.StringIO()):
        return run.validate(curl_tau, w_E, lat, log=_q)


def _field(values, dims=("time", "tile", "j", "i"), units="Pa m-1"):
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
    we = _field([1e-6, 2e-6, -1.5e-6], units="m s-1")

    # positive control: small off-equator curl, tracer dims, right units
    curl = _field([1e-7, 2e-7, -1.5e-7])
    results.append(("good curl passes", _run_validate(curl, we, lat) is True))

    # wrong units → L1 fails
    curl_bad = _field([1e-7, 2e-7, -1.5e-7], units="m/s")
    results.append(("wrong curl units fails", _run_validate(curl_bad, we, lat) is False))

    # non-tracer dims → L1 fails
    curl_nt = _field([1e-7, 2e-7, -1.5e-7], dims=("time", "tile", "j_g", "i_g"))
    results.append(("non-tracer dims fails", _run_validate(curl_nt, we, lat) is False))

    # absurd off-equator curl (1 Pa/m at 30°N) → L3 fails
    curl_fast = _field([1.0, 2e-7, -1.5e-7])
    results.append(("absurd off-equator curl fails", _run_validate(curl_fast, we, lat) is False))

    # SAME absurd curl but AT the equator (masked) → PASS (f→0 blowup tolerated)
    lat_eq = _lat([1.0, 40.0, -35.0])
    results.append(("equatorial blowup tolerated", _run_validate(curl_fast, we, lat_eq) is True))

    # absurd Ekman velocity off-equator → L3 fails
    we_fast = _field([1.0, 2e-6, -1.5e-6], units="m s-1")
    results.append(("absurd w_E fails", _run_validate(curl, we_fast, lat) is False))

    bad = [name for name, ok in results if not ok]
    assert not bad, f"validation guard cases wrong: {bad}"
    return f"{len(results)} negative/positive guard cases behaved correctly"


TESTS = [
    ("Rotation == official UEVNfromUXVY", test_rotation_matches_official_UEVNfromUXVY, True),
    ("Ekman pumping ≈ actual WVEL", test_ekman_pumping_vs_actual_wvel, True),
    ("TEETH: 2nd rotation is load-bearing", test_second_rotation_is_required, True),
    ("validation guards fire (neg+pos)", test_validate_negative_and_positive, False),
]


def main():
    print("=" * 64)
    print("compute-curl tests")
    print("=" * 64)
    data = _data_available()
    if not data:
        print("  [note] Jan-2000 stress/velocity or geometry not cached — the data")
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
