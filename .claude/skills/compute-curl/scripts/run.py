#!/usr/bin/env python3
"""
compute-curl (Recipe 6 / Q5): vertical component of the curl of a vector field on the
LLC90 grid — primarily WIND-STRESS CURL — and the implied Ekman pumping, compared to the
model's actual vertical velocity.

WHY THIS IS HARD (and has been wrong before):
  A bare `∂τy/∂x − ∂τx/∂y` on native model components is WRONG on the LLC grid, and so is
  a SINGLE rotation. Tiles 7–12 are rotated ~90°, so "along model x" is not "along zonal."
  The curl needs TWO rotations (verified against the official native-grid gradient/curl
  tutorial, ECCO_v4_Gradient_calc_on_native_grid.ipynb, cells 125→137):

    1. rotate the COMPONENTS  model → geographic (zonal/meridional)
    2. difference each geographic component along BOTH model axes, /dxC and /dyC
    3. interpolate each derivative pair back to tracer points (interp_2d_vector)
    4. rotate the DERIVATIVE VECTORS  model → geographic  (SAME CS/SN rotation, applied again)
    5. curl_z = ∂v_φ/∂λ − ∂u_λ/∂φ

  Both rotations use the SAME formula:  zonal = X·CS − Y·SN ,  merid = X·SN + Y·CS .
  It's the one rotation applied twice — once to components, once to the derivative vectors.

VERIFICATION (see references/acceptance.md, docs/verify.md):
  No official curl helper exists in ecco_po_tutorials.py OR ecco_v4_py (Rung-1 N/A). The
  curl OPERATOR is verified by (a) reproducing the tutorial pipeline and (b) matching the
  official rotation helper ecco_v4_py.vector_calc.UEVNfromUXVY for the component rotation.
  The Ekman-pumping-vs-WVEL comparison is a PHYSICAL (and scientifically softer) check —
  Ekman pumping is a small residual signal, so it's reported as sign/pattern agreement,
  not a tight correlation. Both are automated in test_curl.py.

INPUT FIELD — oceTAUX/oceTAUY, not EXFtaux/EXFtauy:
  Use the TOTAL ocean surface stress (oceTAUX/oceTAUY), which includes sea-ice–ocean drag —
  that's what actually drives the ocean's Ekman response. EXFtaux/EXFtauy is the bulk
  atmospheric wind stress and ignores the sea-ice modification; under ice they differ.

  GRID POSITION (verified from the real data — the design doc had this BACKWARDS):
    oceTAUX is at the U-point (dims tile,j,i_g); oceTAUY is at the V-point (tile,j_g,i).
    i.e. the STAGGERED velocity-face positions, NOT tracer points. So oceTAUX/oceTAUY must
    be interpolated to centers first (already_at_center=False), exactly like UVEL/VVEL
    (tutorial cell 85). It is EXFtaux/EXFtauy that live at tracer points — but those are the
    bulk stress we deliberately avoid. So: total stress on faces → interpolate first.

Run with the venv python:
    .venv/bin/python run.py 2000-01
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "ecco-common"))
from ecco_common import load_grid, load_field  # noqa: E402

STRESS = "ECCO_L4_STRESS_LLC0090GRID_MONTHLY_V4R4"
OCEAN_VEL = "ECCO_L4_OCEAN_VEL_LLC0090GRID_MONTHLY_V4R4"

RHO_CONST = 1029.0                              # kg m-3, Boussinesq reference density
OMEGA = 2.0 * 3.141592653589793 / 86164.0       # Earth rotation rate, sidereal day
R_EARTH = 6.371e6                               # m, for the beta = df/dy term

EQ_BAND_DEG = 5.0        # |lat| < this is masked (Ekman 1/f singularity)

# Physical-sanity bounds (Layer 3), calibrated against real data (see acceptance.md).
CURL_ABS_MAX = 1.0e-3    # s-1; wind-stress curl / (ρ·L) scale is O(1e-6–1e-5); generous cap
WE_ABS_MAX = 1.0e-4      # m/s; Ekman pumping is O(1e-6) m/s (~10s of m/yr); generous cap


def _log(msg=""):
    print(msg, flush=True)


def _canon(da):
    """Transpose to canonical (time,k,tile,j,i) order — only the dims present, in that
    order. xgcm.interp_2d_vector returns dims in an arbitrary order, so we normalize
    before any positional numpy indexing. (2-D surface fields simply have no k.)"""
    order = [d for d in ("time", "k", "tile", "j", "i") if d in da.dims]
    return da.transpose(*order)


def _coriolis(ds_grid):
    """Coriolis f = 2Ω·sin(lat) at cell centers (dims tile,j,i). Same formula as the
    geostrophy and thermal-wind skills. Returns (f, lat)."""
    import numpy as np
    lat = ds_grid.YC
    return 2.0 * OMEGA * np.sin((np.pi / 180.0) * lat), lat


def _beta(ds_grid):
    """Meridional gradient of f: β = df/dy = (2Ω/R)·cos(lat). At cell centers."""
    import numpy as np
    lat = ds_grid.YC
    return (2.0 * OMEGA / R_EARTH) * np.cos((np.pi / 180.0) * lat)


def _rotate_to_geographic(cx, cy, CS, SN):
    """Model (x,y) → geographic (zonal λ, meridional φ). The SAME rotation used for both
    the components and (later) the derivative vectors:
        zonal = cx·CS − cy·SN ,   merid = cx·SN + cy·CS ."""
    return (cx * CS - cy * SN), (cx * SN + cy * CS)


def curl_z(cx, cy, ds_grid, xgcm_grid, already_at_center=True, units="s-1", log=_log):
    """Vertical component of the curl of a vector field (cx, cy) on the LLC grid, at
    tracer points. Implements the verified two-rotation sequence.

    UNITS: the curl is ∂(field)/∂x − ∂(field)/∂y, so its units are [field]/m. For a
    VELOCITY (m/s) that's s⁻¹ (relative vorticity) — the default. For a STRESS (Pa=N/m²)
    it's Pa/m — pass units='Pa m-1'. The label does not change the math, only honesty.

    already_at_center=True  → inputs are at tracer points: the initial interp is skipped.
    already_at_center=False → inputs are at u/v faces (e.g. UVEL/VVEL, or oceTAUX/oceTAUY
                              which are ALSO on faces): interpolate to centers first.
    """
    import warnings
    CS, SN = ds_grid.CS, ds_grid.SN

    # Step 0: get components at tracer centers.
    if not already_at_center:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            vec = xgcm_grid.interp_2d_vector({"X": cx, "Y": cy}, boundary="fill")
        cx, cy = _canon(vec["X"]), _canon(vec["Y"])

    # Step 1: rotate COMPONENTS model → geographic.
    u_lambda, v_phi = _rotate_to_geographic(cx, cy, CS, SN)

    # Step 2: derivatives of each geographic component along BOTH model axes.
    du_lambda_dx = xgcm_grid.diff(u_lambda, axis="X", boundary="extend") / ds_grid.dxC
    du_lambda_dy = xgcm_grid.diff(u_lambda, axis="Y", boundary="extend") / ds_grid.dyC
    dv_phi_dx = xgcm_grid.diff(v_phi, axis="X", boundary="extend") / ds_grid.dxC
    dv_phi_dy = xgcm_grid.diff(v_phi, axis="Y", boundary="extend") / ds_grid.dyC

    # Step 3: interpolate each derivative pair back to tracer centers.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gu = xgcm_grid.interp_2d_vector({"X": du_lambda_dx, "Y": du_lambda_dy},
                                        boundary="fill")
        gv = xgcm_grid.interp_2d_vector({"X": dv_phi_dx, "Y": dv_phi_dy},
                                        boundary="fill")

    # Step 4: SECOND rotation — rotate the derivative VECTORS model → geographic.
    # We need ∂u_λ/∂φ (meridional derivative of zonal comp) and ∂v_φ/∂λ (zonal derivative
    # of meridional comp). Apply the same rotation and take the matching component:
    #   for gu = (∂u_λ/∂x, ∂u_λ/∂y):  meridional = X·SN + Y·CS  → ∂u_λ/∂φ
    #   for gv = (∂v_φ/∂x, ∂v_φ/∂y):  zonal      = X·CS − Y·SN  → ∂v_φ/∂λ
    du_lambda_dphi = _canon(gu["X"] * SN + gu["Y"] * CS)
    dv_phi_dlambda = _canon(gv["X"] * CS - gv["Y"] * SN)

    # Step 5: curl.
    curl = dv_phi_dlambda - du_lambda_dphi
    curl = _canon(curl)
    curl.name = "curl_z"
    curl.attrs.update({"units": units,
                       "long_name": "vertical curl of vector field (tracer points)"})
    return curl


def ekman_pumping(tau_x, tau_y, ds_grid, xgcm_grid, use_beta=True, log=_log):
    """Ekman pumping velocity w_E from wind stress (tau_x, tau_y = oceTAUX/oceTAUY).

        w_E = (1/ρ)·k·∇×(τ/f)  =  curl(τ)/(ρ·f)  +  (β·τ_zonal)/(ρ·f²)

    The second (β) term is NOT negligible for the Sverdrup/pumping story. Set
    use_beta=False for the f-plane approximation curl(τ)/(ρf) (stated explicitly).
    Returns (w_E, f, lat) with w_E on tracer points (m s-1), model-independent (a scalar).
    """
    import warnings
    CS, SN = ds_grid.CS, ds_grid.SN
    curl_tau = curl_z(tau_x, tau_y, ds_grid, xgcm_grid, already_at_center=False,
                      units="Pa m-1", log=log)      # stress curl → Pa/m, not s-1
    f, lat = _coriolis(ds_grid)

    w_E = curl_tau / (RHO_CONST * f)
    if use_beta:
        # β·τ_zonal/(ρ f²). τ_zonal must come from the CENTER-interpolated stress (oceTAUX/
        # oceTAUY live on u/v faces), else CS/SN (at centers) can't multiply it cleanly.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tvec = xgcm_grid.interp_2d_vector({"X": tau_x, "Y": tau_y}, boundary="fill")
        tcx, tcy = _canon(tvec["X"]), _canon(tvec["Y"])
        tau_zonal, _ = _rotate_to_geographic(tcx, tcy, CS, SN)
        beta = _beta(ds_grid)
        w_E = w_E + (beta * tau_zonal) / (RHO_CONST * f * f)
    w_E = _canon(w_E)
    w_E.name = "w_ekman"
    w_E.attrs.update({"units": "m s-1",
                      "long_name": "Ekman pumping velocity"
                      + ("" if use_beta else " (f-plane approx, no beta term)")})
    return w_E, f, lat


def validate(curl_tau, w_E, lat, log=_log):
    """Runtime validation trail (physical plausibility; needs no WVEL data). Returns True
    if all mandatory checks pass. Independent correctness evidence (rotation vs the
    official helper; Ekman vs actual WVEL) lives in test_curl.py."""
    import numpy as np
    ok = True
    log("  Validation trail:")

    # L1 — grid position + units: curl interpolated to tracer points → dims i,j. Units are
    # [field]/m (Pa/m for a stress curl, s⁻¹ for a velocity curl) — accept either.
    on_tracer = {"i", "j"}.issubset(set(curl_tau.dims))
    units_ok = curl_tau.attrs.get("units") in ("s-1", "Pa m-1")
    l1 = on_tracer and units_ok
    log(f"    [{'✓' if l1 else '✗'}] L1 input: curl on tracer points {tuple(curl_tau.dims)}, "
        f"units={curl_tau.attrs.get('units')!r}")
    ok = ok and l1

    eq = np.abs(lat) < EQ_BAND_DEG
    curl_oe = curl_tau.where(~eq)
    we_oe = w_E.where(~eq)

    # L1b — finite off-equator (NaN on land/equator is fine; inf is not).
    n_inf = int(np.isinf(curl_oe.values).sum() + np.isinf(we_oe.values).sum())
    l1b = (n_inf == 0)
    log(f"    [{'✓' if l1b else '✗'}] L1 finite: {n_inf} infinite value(s) off-equator "
        f"(expect 0)")
    ok = ok and l1b

    # L3 — physical bounds on the curl.
    cunits = curl_tau.attrs.get("units", "")
    cmax = float(np.nanmax(np.abs(curl_oe.values)))
    l3c = cmax <= CURL_ABS_MAX
    log(f"    [{'✓' if l3c else '✗'}] L3 bounds: |curl| ≤ {CURL_ABS_MAX:g} {cunits} outside "
        f"±{EQ_BAND_DEG}° (got max {cmax:.2e})")
    ok = ok and l3c

    # L3 — physical bounds on Ekman pumping.
    wmax = float(np.nanmax(np.abs(we_oe.values)))
    l3w = wmax <= WE_ABS_MAX
    log(f"    [{'✓' if l3w else '✗'}] L3 bounds: |w_E| ≤ {WE_ABS_MAX:g} m/s outside "
        f"±{EQ_BAND_DEG}° (got max {wmax:.2e})")
    ok = ok and l3w

    # L4 — closure: N/A (diagnostic, not a budget).
    log("    [–] L4 closure: not applicable (diagnostic curl, not a budget)")

    log("    [i] Correctness: test_curl.py checks (a) rotation vs official UEVNfromUXVY")
    log("        and (b) Ekman pumping sign/pattern vs the model's actual WVEL.")
    return ok


def main(argv):
    if not argv:
        print("usage: run.py <YYYY-MM>   (wind-stress curl + Ekman pumping)")
        return 2
    ym = argv[0]

    _log("=" * 64)
    _log("compute-curl (Recipe 6 / Q5) — wind-stress curl + Ekman pumping")
    _log("=" * 64)
    _log("Loading grid + surface stress (oceTAUX/oceTAUY, total ocean stress) ...")
    ds_grid, xgcm_grid = load_grid(log=_log)
    ds_str = load_field(STRESS, months=[ym], log=_log)
    tau_x = ds_str.oceTAUX
    tau_y = ds_str.oceTAUY

    _log(f"\nComputing wind-stress curl for {ym} (interp to centers + two rotations) ...")
    curl_tau = curl_z(tau_x, tau_y, ds_grid, xgcm_grid, already_at_center=False,
                      units="Pa m-1")            # stress curl → Pa/m
    _log("Computing Ekman pumping w_E = curl(τ)/(ρf) + β·τ_zonal/(ρf²) ...")
    w_E, f, lat = ekman_pumping(tau_x, tau_y, ds_grid, xgcm_grid, use_beta=True)

    import numpy as np
    oe = np.abs(lat) >= EQ_BAND_DEG
    c0 = curl_tau.isel(time=0) if "time" in curl_tau.dims else curl_tau
    _log(f"  |curl| median (off-equator): "
         f"{float(np.nanmedian(np.abs(c0.where(oe).values))):.2e} {curl_tau.attrs.get('units','')}")

    ok = validate(curl_tau, w_E, lat)
    _log("")
    _log("=" * 64)
    _log("VALIDATION: all runtime checks passed ✓" if ok
         else "VALIDATION: a check FAILED ✗ — do not trust the result.")
    _log("Correctness (rotation vs official helper; Ekman vs actual WVEL) → test_curl.py.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
