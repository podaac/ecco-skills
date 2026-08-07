#!/usr/bin/env python3
"""
compute-ocean-heat-content (Recipe 1): global volume-integrated ocean heat content.

    OHC = sum over wet cells of  THETA * rhoConst * Cp * (rA * drF * hFacC)

THETA is potential temperature (degC), so OHC is heat content relative to 0 degC.
For a *change*, pass two (or more) months: change = OHC(last) - OHC(first).

This is the reference calculation skill — it establishes the pattern every later
calc copies: import ecco_common building blocks, compute, run the applicable
validation layers, and print the whole validation trail (teach-as-you-go).

Run with the venv python:
  .venv/bin/python run.py 2000-01
  .venv/bin/python run.py 2000-01 2010-01        # reports change between the two
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "ecco-common"))
import ecco_preflight  # noqa: E402
ecco_preflight.ensure_env("compute-ocean-heat-content")  # clear msg if env is unhealthy
from ecco_common import load_grid, load_field  # noqa: E402

TS_SHORTNAME = "ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4"

# Physical constants used by ECCO's MITgcm configuration.
RHO_CONST = 1029.0    # kg m-3, Boussinesq reference density
CP = 3994.0           # J kg-1 K-1, seawater heat capacity

# Physical-bounds sanity limits (Layer 3).
THETA_MIN, THETA_MAX = -2.5, 40.0        # degC, plausible in-ocean potential temp
VOLMEAN_MIN, VOLMEAN_MAX = 2.0, 6.0      # degC; global volume-mean is ~3.5 (well
                                         # established). Tightened from [0,10] after
                                         # adversarial review flagged that band as too
                                         # loose to have validation power. 2-6 still has
                                         # margin for legitimate ECCO/era variation but
                                         # would reject a grossly wrong weighting.
# Known global ocean volume for the ECCO LLC90 grid (order-of-magnitude benchmark).
OCEAN_VOL_REF = 1.34e18                   # m^3 (literature ~1.335e18)
OCEAN_VOL_TOL = 0.05                      # accept within 5%


def _log(msg=""):
    print(msg, flush=True)


def cell_volume(ds_grid):
    """Wet-cell volume (m^3): rA * drF * hFacC. hFacC encodes partial cells and is
    zero on land, so this is already the ocean volume per cell."""
    return ds_grid.rA * ds_grid.drF * ds_grid.hFacC


def compute_ohc_one_month(ds_grid, ym):
    """Return (ohc_joules, volmean_theta_degC, total_volume_m3) for one 'YYYY-MM'."""
    ds = load_field(TS_SHORTNAME, months=[ym], log=_log)

    # L1 time check: confirm the loaded data really is the requested month before
    # trusting it. isel(time=0) is only safe once we've verified the coordinate.
    if "time" in ds.THETA.dims:
        n_t = ds.sizes.get("time", 1)
        if n_t != 1:
            raise ValueError(f"Expected exactly 1 time step for {ym}, got {n_t} "
                             "(month selection may have pulled extra granules).")
        t0 = ds["time"].isel(time=0).values
        got = str(t0)[:7]                          # 'YYYY-MM'
        if got != ym:
            raise ValueError(f"Requested {ym} but loaded data is dated {got} — "
                             "wrong granule (see month-edge overlap gotcha).")
        _log(f"  [time ✓] loaded month {got} matches request {ym}")

    theta = ds.THETA.isel(time=0)                 # (k, tile, j, i), degC
    vol = cell_volume(ds_grid)                    # (k, tile, j, i), m^3
    maskC = ds_grid.maskC                         # 1 wet / 0 land

    wet_vol = (vol * maskC)
    total_vol = float(wet_vol.sum().values)
    # volume-weighted global mean potential temperature
    volmean_theta = float((theta * wet_vol).sum().values / total_vol)
    # heat content relative to 0 degC
    ohc = RHO_CONST * CP * float((theta * wet_vol).sum().values)
    return ohc, volmean_theta, total_vol, theta, maskC


def validate(theta, volmean_theta, total_vol, wet_mask=None):
    """Run the applicable validation layers, printing a ✓/✗ trail. Returns True if
    all mandatory checks pass.

    wet_mask (optional): the ocean mask (maskC). If given, L1 asserts there are no
    NaN/inf values in *wet* cells — land NaNs are fine, but a NaN in the ocean would
    silently poison the sum. Passing it enables the finite-in-wet-cells guard.
    """
    import numpy as np

    ok = True
    _log("  Validation trail:")

    # L1 — input/metadata: THETA on tracer points, degC.
    dims = set(theta.dims)
    on_tracer = {"i", "j"}.issubset(dims)
    units = theta.attrs.get("units", "")
    l1 = on_tracer and units in ("degC", "degree_C", "deg_C", "degrees_C")
    _log(f"    [{'✓' if l1 else '✗'}] L1 input: THETA on tracer points {tuple(theta.dims)}, "
         f"units={units!r}")
    ok = ok and l1

    # L1b — finite values where it matters. A NaN/inf in a wet cell would poison the
    # sum silently. If a wet mask is provided, check only wet cells (land NaNs are OK);
    # otherwise fall back to requiring the reported volume-mean to be finite.
    if wet_mask is not None:
        wet_vals = theta.where(wet_mask.astype(bool))
        n_bad = int((~np.isfinite(wet_vals)).where(wet_mask.astype(bool)).sum().values)
        l1b = (n_bad == 0)
        _log(f"    [{'✓' if l1b else '✗'}] L1 finite: {n_bad} non-finite value(s) in wet cells "
             f"(expect 0)")
    else:
        l1b = bool(np.isfinite(volmean_theta))
        _log(f"    [{'✓' if l1b else '✗'}] L1 finite: volume-mean is finite "
             f"(no wet-cell NaN leaked into the sum)")
    ok = ok and l1b

    # L2 — units: check the result is finite and the unit chain is dimensionally sound.
    # (degC × kg/m3 × J/kg/K × m3 → J). We assert finiteness rather than print an
    # unconditional success, so a NaN/inf total is actually caught here.
    l2 = bool(np.isfinite(volmean_theta)) and bool(np.isfinite(total_vol)) and total_vol > 0
    _log(f"    [{'✓' if l2 else '✗'}] L2 numeric sanity: result finite & volume > 0 "
         f"(unit chain degC×kg/m3×J/kg/K×m3→J is documented, not machine-checked)")
    ok = ok and l2

    # L3 — physical bounds.
    tmin = float(theta.min().values)
    tmax = float(theta.max().values)
    l3_range = THETA_MIN <= tmin and tmax <= THETA_MAX
    l3_mean = VOLMEAN_MIN <= volmean_theta <= VOLMEAN_MAX
    _log(f"    [{'✓' if l3_range else '✗'}] L3 bounds: THETA in "
         f"[{tmin:.2f}, {tmax:.2f}] degC (expect within [{THETA_MIN}, {THETA_MAX}])")
    _log(f"    [{'✓' if l3_mean else '✗'}] L3 bounds: volume-mean THETA "
         f"{volmean_theta:.2f} degC (expect cold, ~3.5)")
    ok = ok and l3_range and l3_mean

    # L4 — conservation closure: N/A for a bare snapshot (no budget to close).
    _log("    [–] L4 closure: not applicable (snapshot heat content, not a budget)")

    # L6 — benchmark: total ocean volume vs known global value.
    vol_err = abs(total_vol - OCEAN_VOL_REF) / OCEAN_VOL_REF
    l6 = vol_err <= OCEAN_VOL_TOL
    _log(f"    [{'✓' if l6 else '✗'}] L6 benchmark: ocean volume {total_vol:.3e} m3 "
         f"vs ~{OCEAN_VOL_REF:.2e} (off {100*vol_err:.1f}%, tol {100*OCEAN_VOL_TOL:.0f}%)")
    ok = ok and l6

    return ok


def main(argv):
    if not argv:
        print("usage: run.py <YYYY-MM> [<YYYY-MM>]   (2nd month → reports OHC change)")
        return 2
    months = argv

    _log("=" * 64)
    _log("compute-ocean-heat-content (Recipe 1)")
    _log("=" * 64)
    _log("Loading grid ...")
    ds_grid, _ = load_grid(log=_log)

    results = {}
    all_ok = True
    for ym in months:
        _log("")
        _log(f"Month {ym}:")
        ohc, volmean, total_vol, theta, wet_mask = compute_ohc_one_month(ds_grid, ym)
        _log(f"  OHC = {ohc:.4e} J   (relative to 0 degC)")
        _log(f"  volume-mean potential temperature = {volmean:.3f} degC")
        ok = validate(theta, volmean, total_vol, wet_mask=wet_mask)
        all_ok = all_ok and ok
        results[ym] = ohc

    _log("")
    _log("=" * 64)
    if len(months) >= 2:
        first, last = months[0], months[-1]
        change = results[last] - results[first]
        _log(f"OHC CHANGE {first} → {last}: {change:+.4e} J")
        # A change is what's physically meaningful (absolute value is vs 0 degC).
        _log(f"  ({results[last]:.4e} − {results[first]:.4e} J)")
    else:
        _log(f"OHC ({months[0]}) = {results[months[0]]:.4e} J  relative to 0 degC.")
        _log("  Note: absolute OHC is baseline-dependent. For a physically meaningful")
        _log("  result, pass two months to get a CHANGE, e.g. run.py 2000-01 2010-01.")
    _log("=" * 64)
    _log("VALIDATION: all applicable checks passed ✓" if all_ok
         else "VALIDATION: one or more checks FAILED ✗ — do not trust the number.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
