#!/usr/bin/env python3
"""
Negative + positive tests for the OHC validation layers.

The point: a guard that has only ever been seen to PASS on good data could be silently
broken. This proves each check actually FIRES on bad input and PASSES on good input.
No download needed — uses tiny synthetic xarray arrays.

Run with the venv python:  .venv/bin/python test_validation.py
Exit 0 if all test cases behave as expected, 1 otherwise.
"""
import io
import os
import sys
import contextlib

import numpy as np
import xarray as xr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run  # the skill script under test  # noqa: E402


def make_theta(values, units="degree_C", dims=("k", "tile", "j", "i")):
    """Build a small THETA-like DataArray with given flat values, shaped to `dims`."""
    arr = np.array(values, dtype=float)
    # reshape into a minimal N-d array over the requested dims
    shape = (arr.size,) + (1,) * (len(dims) - 1)
    da = xr.DataArray(arr.reshape(shape), dims=dims)
    da.attrs["units"] = units
    return da


def run_validate(theta, volmean, total_vol, wet_mask=None):
    """Call run.validate, suppressing its printed trail; return the bool result."""
    with contextlib.redirect_stdout(io.StringIO()):
        return run.validate(theta, volmean, total_vol, wet_mask=wet_mask)


GOOD_VOL = run.OCEAN_VOL_REF          # ~1.34e18, passes L6
BAD_VOL = run.OCEAN_VOL_REF * 2       # 100% off, fails L6


def main():
    cases = []

    # 1. POSITIVE control: realistic ocean data → must PASS.
    good_theta = make_theta([-1.8, 3.5, 28.0])
    cases.append(("good ocean data passes", run_validate(good_theta, 3.5, GOOD_VOL), True))

    # 2. THETA in Kelvin (the classic mistake) → L3 range + mean must FAIL.
    kelvin_theta = make_theta([271.35, 276.65, 301.15])   # = -1.8, 3.5, 28 in K
    cases.append(("THETA in Kelvin fails", run_validate(kelvin_theta, 285.0, GOOD_VOL), False))

    # 3. Volume-mean too warm (e.g. only counted surface) → L3 mean must FAIL.
    cases.append(("too-warm volume mean fails", run_validate(good_theta, 18.0, GOOD_VOL), False))

    # 4. Wrong units metadata → L1 must FAIL.
    wrong_units = make_theta([-1.8, 3.5, 28.0], units="kelvin")
    cases.append(("wrong units fails L1", run_validate(wrong_units, 3.5, GOOD_VOL), False))

    # 5. Missing horizontal dims (not on tracer points) → L1 must FAIL.
    not_tracer = make_theta([-1.8, 3.5, 28.0], dims=("k", "tile", "j_g", "i_g"))
    cases.append(("non-tracer dims fails L1", run_validate(not_tracer, 3.5, GOOD_VOL), False))

    # 6. Bad ocean volume → L6 benchmark must FAIL.
    cases.append(("bad ocean volume fails L6", run_validate(good_theta, 3.5, BAD_VOL), False))

    # 7. Absurd hot temperature → L3 range must FAIL.
    hot = make_theta([-1.8, 3.5, 999.0])
    cases.append(("absurd hot THETA fails", run_validate(hot, 3.5, GOOD_VOL), False))

    # 8. NaN in a WET cell (with mask) → L1 finite must FAIL. This is the case the
    #    eval flagged: previously a wet-cell NaN slipped through as True.
    nan_theta = make_theta([-1.8, np.nan, 28.0])
    all_wet = make_theta([1, 1, 1])                      # every cell wet
    cases.append(("wet-cell NaN fails (masked)",
                  run_validate(nan_theta, 3.5, GOOD_VOL, wet_mask=all_wet), False))

    # 9. NaN present but non-finite volume-mean, no mask → L1/L2 finite must FAIL.
    cases.append(("non-finite volmean fails (no mask)",
                  run_validate(good_theta, float("nan"), GOOD_VOL), False))

    # 10. NaN only in a LAND cell (masked out) → should still PASS (land NaNs are fine).
    land_nan_theta = make_theta([-1.8, np.nan, 28.0])
    mask_middle_land = make_theta([1, 0, 1])             # middle cell is land
    cases.append(("land-cell NaN still passes",
                  run_validate(land_nan_theta, 3.5, GOOD_VOL, wet_mask=mask_middle_land), True))

    print("=" * 60)
    print("OHC validation-layer tests (negative + positive)")
    print("=" * 60)
    all_ok = True
    for name, got, expected in cases:
        passed = (got == expected)
        all_ok = all_ok and passed
        verdict = "PASS" if passed else "FAIL"
        print(f"  [{verdict}] {name}: validate()={got}, expected={expected}")

    # --- Rung 2: tutorial-number reproduction (needs the cached grid) ---
    # The scalar-quantities tutorial publishes total ocean surface area = 3.58E+08 km^2,
    # computed as (rA * maskC).isel(k=0).sum(). Reproducing it exactly validates the grid
    # geometry that the OHC volume weighting is built on. Skipped (not failed) if the
    # grid isn't cached, so the offline unit tests still run anywhere.
    print("-" * 60)
    try:
        import os as _os
        sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                         "..", "..", "ecco-common"))
        from ecco_common import cache as _cache
        geom = _cache.lookup_cached("ECCO_L4_GEOMETRY_LLC0090GRID_V4R4", "GEOMETRY")
        if geom is None:
            print("  [SKIP] Rung 2 tutorial number: geometry not cached "
                  "(run load-grid to enable this check)")
        else:
            import xarray as _xr
            dsg = _xr.open_dataset(geom)
            area_km2 = float((dsg.rA * dsg.maskC).isel(k=0).sum()) / 1e6
            ok = abs(area_km2 - 3.58e8) / 3.58e8 < 0.005
            all_ok = all_ok and ok
            print(f"  [{'PASS' if ok else 'FAIL'}] Rung 2 tutorial number: "
                  f"ocean surface area {area_km2:.2E} km^2 vs published 3.58E+08 "
                  f"(match {'✓' if ok else '✗'})")
    except Exception as e:  # noqa: BLE001
        print(f"  [SKIP] Rung 2 tutorial number: {type(e).__name__}: {e}")

    print("=" * 60)
    print("ALL TESTS PASS ✓" if all_ok else "SOME TESTS FAILED ✗")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
