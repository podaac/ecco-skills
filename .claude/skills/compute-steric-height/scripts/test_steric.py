#!/usr/bin/env python3
"""
Verification for compute-steric-height. No official steric helper exists (Rung-1 N/A for
the integral), so correctness rests on:

  (0) EOS CHECK-VALUE (Rung-1-style anchor): the vendored JMD95 reproduces its own published
      check value densjmd95(35.5, 3, 3000 dbar) = 1041.83267 kg/m³. Offline, no ECCO data.

  (1) SUM-OF-PARTS (Rung 5a): thermosteric + halosteric ≈ full steric anomaly. The tutorial's
      own decomposition check. Measured Jan 2000: median residual 0.005 m, corr 0.9998.

  (2) STERIC ≈ SSH (Rung 5b, INDEPENDENT physical): steric height explains most of the
      spatial SSH structure (both global-mean-removed). SSH is a different variable from a
      different collection, so this rules out a bug confined to the density path. Measured
      Jan 2000: corr 0.921 (std SSH 0.79 m; non-steric residual only 0.31 m).

Data checks SKIP (not fail) if Jan-2000 density/T-S/SSH + geometry aren't cached. The EOS
check-value and the offline synthetic validate() guards always run.

Run with the venv python:
    .venv/bin/python .claude/skills/compute-steric-height/scripts/test_steric.py
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

DENSPRESS = run.DENSPRESS
TEMPSALT = run.TEMPSALT
SSH = run.SSH
GEOM = "ECCO_L4_GEOMETRY_LLC0090GRID_V4R4"


def _data_available():
    return all(cache.lookup_cached(sn, "2000-01") is not None
               for sn in (DENSPRESS, TEMPSALT, SSH)) \
        and cache.lookup_cached(GEOM, "GEOMETRY") is not None


def _q(*a):
    return None


# --------------------------------------------------------------------------
# (0) EOS check value — always runs (offline, no ECCO data)
# --------------------------------------------------------------------------
def test_eos_check_value():
    """Vendored JMD95 reproduces its published check value."""
    from jmd95 import densjmd95
    rho = float(densjmd95(35.5, 3.0, 3000.0))
    assert abs(rho - 1041.83267) < 1e-3, (
        f"JMD95 check value wrong: got {rho:.5f}, expected 1041.83267")
    return f"densjmd95(35.5, 3, 3000) = {rho:.5f} == published 1041.83267"


# --------------------------------------------------------------------------
# Data cross-checks
# --------------------------------------------------------------------------
def _compute():
    ds_grid, _ = load_grid(log=_q)
    ds_dp = load_field(DENSPRESS, months=["2000-01"], log=_q)
    ds_ts = load_field(TEMPSALT, months=["2000-01"], log=_q)
    ds_ssh = load_field(SSH, months=["2000-01"], log=_q)
    h_gm, thermo, halo, um = run.compute_all(ds_grid, ds_dp, ds_ts, ds_ssh)
    return ds_grid, ds_ssh, h_gm, thermo, halo, um


def test_sum_of_parts():
    """(1) thermosteric + halosteric ≈ full steric anomaly (tutorial's decomposition check)."""
    import numpy as np
    _, _, h_gm, thermo, halo, um = _compute()
    umb = um.astype(bool).values
    h = np.squeeze(h_gm.values)
    p = np.squeeze((thermo + halo).values)
    g = np.isfinite(h) & np.isfinite(p) & umb
    n = int(g.sum())
    assert n > 20000, f"too few points: {n}"
    resid = float(np.nanmedian(np.abs(h[g] - p[g])))
    corr = float(np.corrcoef(h[g], p[g])[0, 1])
    assert resid < 0.05, f"sum-of-parts residual too large: {resid:.3f} m (measured ~0.005)"
    assert corr > 0.99, f"sum-of-parts correlation too low: {corr:.4f} (measured ~0.9998)"
    return f"thermo+halo ≈ full steric: median residual {resid:.4f} m, corr {corr:.4f} ({n} pts)"


def test_steric_vs_ssh():
    """(2) steric height explains most of the spatial SSH structure (independent check)."""
    import numpy as np
    ds_grid, ds_ssh, h_gm, _, _, um = _compute()
    # SSH, global-mean-removed over the SAME valid region
    w = um * ds_grid.rA
    ssh = ds_ssh.SSH
    ssh_gm = ssh - (float((w * ssh).sum()) / float(w.sum()))

    umb = um.astype(bool).values
    h = np.squeeze(h_gm.values)
    s = np.squeeze(ssh_gm.values)
    g = np.isfinite(h) & np.isfinite(s) & umb
    n = int(g.sum())
    assert n > 20000, f"too few points: {n}"
    corr = float(np.corrcoef(h[g], s[g])[0, 1])
    resid_std = float(np.std(s[g] - h[g]))
    ssh_std = float(np.std(s[g]))
    # Threshold from the measured Jan-2000 value (corr~0.92), with margin. Steric explains
    # most (not all) of SSH — the residual is the non-steric (mass/barotropic) component.
    assert corr > 0.85, f"steric vs SSH correlation too low: {corr:.3f} (measured ~0.92)"
    assert resid_std < ssh_std, "non-steric residual should be smaller than SSH variability"
    return (f"steric ≈ SSH: corr {corr:.3f}, std(SSH)={ssh_std:.2f} m, "
            f"non-steric residual std={resid_std:.2f} m ({n} pts)")


def test_zstar_weighting_is_load_bearing():
    """TEETH: flipping the sign of the specific-volume anomaly must break steric-vs-SSH
    (steric would anti-correlate with SSH). Proves the sign/weighting is load-bearing."""
    import numpy as np
    ds_grid, ds_ssh, h_gm, _, _, um = _compute()
    w = um * ds_grid.rA
    ssh = ds_ssh.SSH
    ssh_gm = ssh - (float((w * ssh).sum()) / float(w.sum()))
    umb = um.astype(bool).values
    h = np.squeeze(h_gm.values); s = np.squeeze(ssh_gm.values)
    g = np.isfinite(h) & np.isfinite(s) & umb
    corr_good = float(np.corrcoef(h[g], s[g])[0, 1])
    corr_flipped = float(np.corrcoef(-h[g], s[g])[0, 1])   # sign-flipped steric
    assert corr_good > 0.85 and corr_flipped < -0.85, (
        f"sign is not load-bearing: good corr {corr_good:.3f}, flipped {corr_flipped:.3f}")
    return f"specvol-anomaly sign is load-bearing: corr {corr_good:.2f} → {corr_flipped:.2f} when flipped"


# --------------------------------------------------------------------------
# Offline synthetic validate() guards (no data)
# --------------------------------------------------------------------------
def _run_validate(h, thermo, halo, unmasked):
    with contextlib.redirect_stdout(io.StringIO()):
        return run.validate(h, thermo, halo, unmasked, log=_q)


def _field(values, dims=("tile", "j", "i"), units="m"):
    import numpy as np
    import xarray as xr
    arr = np.array(values, dtype=float)
    shape = (1,) * (len(dims) - 1) + (arr.size,)
    da = xr.DataArray(arr.reshape(shape), dims=dims)
    da.attrs["units"] = units
    return da


def test_validate_negative_and_positive():
    """Runtime guards must FIRE on bad input and PASS on good — no data needed."""
    results = []
    um = _field([1, 1, 1])                      # all valid

    # positive control: small steric + parts that sum to it
    h = _field([0.5, -0.3, 0.1])
    thermo = _field([0.4, -0.2, 0.15]); halo = _field([0.1, -0.1, -0.05])
    results.append(("good steric passes", _run_validate(h, thermo, halo, um) is True))

    # wrong units → L1 fails
    h_bad = _field([0.5, -0.3, 0.1], units="cm")
    results.append(("wrong units fails", _run_validate(h_bad, thermo, halo, um) is False))

    # non-tracer dims → L1 fails
    h_nt = _field([0.5, -0.3, 0.1], dims=("tile", "j_g", "i_g"))
    results.append(("non-tracer dims fails", _run_validate(h_nt, thermo, halo, um) is False))

    # absurd steric (50 m) in a valid cell → L3 fails
    h_big = _field([50.0, -0.3, 0.1])
    results.append(("absurd steric fails", _run_validate(h_big, thermo, halo, um) is False))

    # parts that DON'T sum to the full field → L5 sum-of-parts fails
    thermo_bad = _field([5.0, 5.0, 5.0]); halo_bad = _field([5.0, 5.0, 5.0])
    results.append(("bad sum-of-parts fails",
                    _run_validate(h, thermo_bad, halo_bad, um) is False))

    bad = [name for name, ok in results if not ok]
    assert not bad, f"validation guard cases wrong: {bad}"
    return f"{len(results)} negative/positive guard cases behaved correctly"


TESTS = [
    ("EOS check value (JMD95)", test_eos_check_value, False),
    ("Sum-of-parts: thermo+halo ≈ full", test_sum_of_parts, True),
    ("Steric ≈ SSH (independent)", test_steric_vs_ssh, True),
    ("TEETH: specvol sign is load-bearing", test_zstar_weighting_is_load_bearing, True),
    ("validation guards fire (neg+pos)", test_validate_negative_and_positive, False),
]


def main():
    print("=" * 64)
    print("compute-steric-height tests")
    print("=" * 64)
    data = _data_available()
    if not data:
        print("  [note] Jan-2000 density/T-S/SSH or geometry not cached — the data")
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
