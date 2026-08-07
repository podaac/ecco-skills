---
name: compute-curl
description: Compute the vertical curl of a vector field on the ECCO LLC90 grid — primarily wind-stress curl (from oceTAUX/oceTAUY) — and the implied Ekman pumping velocity, compared to the model's actual vertical velocity WVEL. Handles the LLC grid's mandatory TWO rotations (components + derivative vectors). Use for wind-stress curl, Ekman pumping, vorticity, or "does the curl of the wind stress line up with vertical velocity?". Requires ecco-setup + Earthdata credentials.
---

# compute-curl (Recipe 6 / Q5)

> **🔬 Verification status (per `docs/verify.md`): ✅ DONE** (Rung-7 adversarial pass clean,
> 2026-08-06 — `docs/eval5.md`; both historical rotation bugs confirmed blocked). No official
> curl helper exists (Rung 1 N/A). Correctness rests on: **(1)**
> the CS/SN component rotation is **bit-identical** to the official `ecco_v4_py.vector_calc.
> UEVNfromUXVY` (max|Δ|=0); **(2)** Ekman pumping `w_E` matches the model's **actual WVEL**
> near the base of the Ekman layer (~30 m): **corr 0.74, sign-agreement 0.89** off-equator
> — a strong, independent physical check. Teeth-verified: dropping the mandatory second
> rotation shifts the curl by ~30%, and flipping the Ekman sign drops the WVEL correlation
> to −0.56 (both fail the suite). Full record: `references/acceptance.md`.

The vertical component of the curl of a vector field on the LLC90 grid — the operation
behind **wind-stress curl → Ekman pumping** (Q5). Also usable for relative vorticity
(curl of velocity).

## The science (what a learner should take away)

- **Ekman pumping** is vertical velocity driven by the *spatial variation* of the wind
  stress: `w_E = (1/ρ)·k·∇×(τ/f)`. Where the wind-stress curl is negative (subtropical
  gyres), the ocean downwells; where positive (subpolar, Southern Ocean), it upwells.
- **Use `oceTAUX`/`oceTAUY`, not `EXFtaux`/`EXFtauy`.** `oceTAUX/Y` is the *total* stress
  the ocean surface feels, including sea-ice–ocean drag — that's what drives the real
  Ekman response. `EXFtaux/y` is the bulk atmospheric wind stress and ignores sea ice;
  under ice they differ substantially.
- **Grid position (a real gotcha — the design doc had it backwards):** `oceTAUX` lives on
  the U-point (`i_g`), `oceTAUY` on the V-point (`j_g`) — the staggered *velocity-face*
  positions, NOT tracer points. So they must be interpolated to centers first, exactly
  like `UVEL`/`VVEL`. (It's `EXFtaux/y` that sit at tracer points — but those are the bulk
  stress we avoid.)
- **Units:** the curl is `∂(field)/∂x − ∂(field)/∂y`, so its units are `[field]/m`. For a
  *stress* (Pa) that's **Pa/m**; for a *velocity* (m/s) it's **s⁻¹** (relative vorticity).
  The skill labels these honestly (`units=` argument).

## The two rotations (why a naive curl is wrong)

On the LLC grid, tiles 7–12 are rotated ~90°, so "along model x" is **not** "along zonal."
A bare `∂τy/∂x − ∂τx/∂y` on model components is wrong, and so is a *single* rotation. The
correct sequence needs **TWO** rotations (verified against the official native-grid
gradient/curl tutorial):

1. **Rotate the components** model→geographic: `u_λ = τx·CS − τy·SN`, `v_φ = τx·SN + τy·CS`.
2. **Difference** each geographic component along **both** model axes (`/dxC`, `/dyC`).
3. **Interpolate** each derivative pair back to tracer centers (`interp_2d_vector`).
4. **Rotate the derivative vectors** model→geographic — the SAME CS/SN rotation, applied
   again — to get `∂u_λ/∂φ` and `∂v_φ/∂λ`.
5. **curl** `= ∂v_φ/∂λ − ∂u_λ/∂φ`.

Both rotations use the identical `X·CS − Y·SN` (zonal) / `X·SN + Y·CS` (merid) formula.
The second rotation is not optional: skipping it changes the curl by ~30% (teeth test).

## Environment — do this first

This skill runs in the project `.venv` built by **`ecco-setup`**. Before running it, make sure
that environment is ready — **don't run against a missing or broken `.venv`**:

1. Check health: `python3 .claude/skills/ecco-setup/scripts/verify_env.py` (verify mode).
2. If it reports **no `.venv`** or a failed import, **run `ecco-setup` first**
   (`python3 .claude/skills/ecco-setup/scripts/setup_env.py`, or `--reset` to rebuild a
   broken one), then re-run this skill. Building is a one-time step; a healthy `.venv` is
   reused automatically.

(If you invoke `run.py` directly and the `.venv` is unhealthy, the built-in `ecco_preflight`
guard prints a clear "run ecco-setup" message. If the `.venv` is missing entirely,
`.venv/bin/python` won't exist — that's your cue to run `ecco-setup`.)

## How to run

```
.venv/bin/python scripts/run.py 2000-01     # wind-stress curl + Ekman pumping for Jan 2000
```

Run with the **venv** python. Loads the stress collection (~small, downloaded on first use)
+ geometry. Prints the runtime validation trail (grid position, units, off-equator
finiteness, physical bounds on curl and w_E).

## Composition (Option A)

```python
from ecco_common import load_grid, load_field
ds_grid, xgcm_grid = load_grid()
ds_str = load_field("ECCO_L4_STRESS_LLC0090GRID_MONTHLY_V4R4", months=["2000-01"])
# curl_z(tau_x, tau_y, ds_grid, xgcm_grid, already_at_center=False, units="Pa m-1")
```

The Ekman-pumping cross-check additionally loads `ECCO_L4_OCEAN_VEL_…` for `WVEL`.

## Verification (per `docs/verify.md`)

| Rung | Status | Evidence |
|------|--------|----------|
| 1 official helper | **N/A** | No curl helper in `ecco_po_tutorials.py` or `ecco_v4_py`. *Partial:* the CS/SN rotation core matches the official `vector_calc.UEVNfromUXVY` exactly (max\|Δ\|=0). |
| 2 tutorial number | ✅ (operator) | Reproduces the official native-grid gradient/curl tutorial's two-rotation pipeline; the tutorial publishes maps, not scalars. |
| 3 conservation | N/A | Diagnostic, not a budget. |
| 4 physical sanity | ✅ | Wind-stress curl O(1e-7 Pa/m); Ekman `w_E` O(1e-6 m/s); correct sign — negative curl (downwelling) in the N. Pacific subtropical gyre. Equator masked. |
| 5 cross-check | ✅ | **(a)** rotation == official `UEVNfromUXVY` (bit-identical). **(b) independent physical:** `w_E` vs the model's *actual* `WVEL` at ~30 m: corr **0.74**, sign-agree **0.89** off-equator (different variable/path → rules out a stress-path-only bug). |
| 6 regression (teeth) | ✅ | `test_curl.py`: rotation + Ekman-vs-WVEL + a teeth test proving the 2nd rotation is load-bearing (~30% shift) + offline guards. Sign flip drops WVEL corr to −0.56 (fails). |
| 7 adversarial | ✅ | Independent Sonnet disprove-pass (2026-08-06, `docs/eval5.md`): could not disprove; zero confirmed errors; both historical rotation bugs blocked. One caveat fixed (teeth threshold 0.05→0.20). |

## Limits / honest caveats

- **The curl operator is the strong part** (official-rotation match + tutorial pipeline +
  teeth on the 2nd rotation). The **Ekman-vs-WVEL** comparison is a *physical* check —
  strong here (corr 0.74) but it's a real ocean relationship, not an identity: `WVEL`
  contains more than Ekman pumping, so don't expect corr→1.
- **β term included by default:** `w_E = curl(τ)/(ρf) + β·τ_zonal/(ρf²)`. Pass
  `use_beta=False` for the f-plane approximation (stated in the output label).
- **Equatorial band** (`|lat|<5°`) excluded — `1/f` blows up there; don't report values.
- **`WVEL` is on the vertical interface (`k_l`)**; the cross-check samples ~30 m (base of
  the Ekman layer), off-equator.

## Files
- `scripts/run.py` — `curl_z` (two-rotation) + `ekman_pumping` + runtime validation trail.
- `scripts/test_curl.py` — rotation-vs-official + Ekman-vs-WVEL + teeth + offline guards.
- `references/acceptance.md` — verification evidence.
