#!/usr/bin/env python3
"""
Offline tests for ecco_common.grid_ops (the Level-1 primitives extracted 2026-08-05).

`coriolis` and `canon` are fully synthetic (no data). `grad_to_center` needs a real xgcm
grid, so it's data-gated: it SKIPs when the geometry isn't cached, and when it is, it
asserts the helper equals the inline diff/interp sequence it replaced (a self-consistency
check — the skills' own Rung-1/cross-check suites prove the physics end-to-end).

Run with the venv python:
    .venv/bin/python .claude/skills/ecco-common/tests/test_grid_ops.py
"""
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))

from ecco_common import grid_ops, cache  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


# --------------------------------------------------------------------------
# canon — pure synthetic
# --------------------------------------------------------------------------
@test
def test_canon_reorders_and_drops_missing():
    import numpy as np
    import xarray as xr
    # deliberately scrambled dim order, as interp_2d_vector can return
    da = xr.DataArray(np.zeros((3, 2, 5, 4)), dims=("tile", "i", "time", "k"))
    out = grid_ops.canon(da)
    assert out.dims == ("time", "k", "tile", "i"), out.dims   # j absent → skipped, rest ordered
    # a 2-D surface field (no time/k) keeps only tile,j,i in order
    da2 = xr.DataArray(np.zeros((4, 3, 2)), dims=("i", "tile", "j"))
    assert grid_ops.canon(da2).dims == ("tile", "j", "i"), grid_ops.canon(da2).dims


@test
def test_canon_preserves_values():
    import numpy as np
    import xarray as xr
    arr = np.arange(2 * 3 * 4, dtype=float).reshape(2, 3, 4)
    da = xr.DataArray(arr, dims=("tile", "j", "i"))
    out = grid_ops.canon(da)                       # already canonical → identical
    assert np.array_equal(out.values, arr)


# --------------------------------------------------------------------------
# coriolis — pure synthetic
# --------------------------------------------------------------------------
@test
def test_coriolis_formula_and_signs():
    import numpy as np
    import xarray as xr

    class G:  # minimal stand-in with a YC attribute
        pass
    lat = xr.DataArray(np.array([[-45.0, 0.0, 45.0]]), dims=("j", "i"))
    g = G(); g.YC = lat
    f, latout = grid_ops.coriolis(g)
    fv = f.values.ravel()
    # equator → 0; symmetric magnitude; northern positive, southern negative
    assert abs(fv[1]) < 1e-12, fv
    assert fv[2] > 0 and fv[0] < 0, fv
    assert abs(fv[2] + fv[0]) < 1e-12, "f should be antisymmetric in latitude"
    # magnitude at 45N: 2*Omega*sin(45)
    expect = 2.0 * grid_ops.OMEGA * np.sin(np.pi / 4)
    assert abs(fv[2] - expect) < 1e-15, (fv[2], expect)
    assert latout is lat


@test
def test_omega_value():
    import numpy as np
    assert abs(grid_ops.OMEGA - 2.0 * np.pi / 86164.0) < 1e-18


# --------------------------------------------------------------------------
# grad_to_center — data-gated (needs a real xgcm grid)
# --------------------------------------------------------------------------
@test
def test_grad_to_center_matches_inline_sequence():
    """grad_to_center == the raw diff/interp sequence it replaced (self-consistency)."""
    import warnings
    geom = cache.lookup_cached("ECCO_L4_GEOMETRY_LLC0090GRID_V4R4", "GEOMETRY")
    if geom is None:
        print("  [SKIP] test_grad_to_center_matches_inline_sequence: geometry not cached")
        return
    import numpy as np
    from ecco_common import load_grid
    ds_grid, xg = load_grid(log=lambda *a: None)
    scalar = ds_grid.Depth                      # any tracer-centered field works

    dfdx, dfdy = grid_ops.grad_to_center(scalar, ds_grid, xg, boundary="extend")

    # inline reference (what the skills used to do verbatim)
    rx = xg.diff(scalar, axis="X", boundary="extend") / ds_grid.dxC
    ry = xg.diff(scalar, axis="Y", boundary="extend") / ds_grid.dyC
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ref = xg.interp_2d_vector({"X": rx, "Y": ry}, boundary="extend")
    a = np.asarray(dfdx.values); b = np.asarray(ref["X"].values)
    c = np.asarray(dfdy.values); d = np.asarray(ref["Y"].values)
    fa = np.isfinite(a) & np.isfinite(b)
    assert np.array_equal(a[fa], b[fa]), "dfdx differs from inline sequence"
    fc = np.isfinite(c) & np.isfinite(d)
    assert np.array_equal(c[fc], d[fc]), "dfdy differs from inline sequence"


def main():
    print("=" * 64)
    print("ecco_common.grid_ops tests")
    print("=" * 64)
    passed = failed = 0
    for fn in TESTS:
        try:
            fn()
            print(f"  [PASS] {fn.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print("=" * 64)
    print(f"{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
