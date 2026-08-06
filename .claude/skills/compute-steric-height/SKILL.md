---
name: compute-steric-height
description: Compute steric height anomaly from ECCO density — the part of sea level set by the water column's temperature/salinity structure — with a thermosteric/halosteric decomposition, and compare it to the model's actual sea surface height (SSH). Uses the model's own RHOAnoma for the base term and the vendored MITgcm JMD95 equation of state for the reference profile and the T/S split. Use for steric height, steric sea-level rise, thermosteric/halosteric contributions, or "how much of SSH is steric?". Requires ecco-setup + Earthdata credentials.
---

# compute-steric-height (Recipe 3-steric)

> **🔬 Verification status (per `docs/verify.md`): ✅ DONE** (Rung-7 adversarial pass clean,
> 2026-08-06 — `docs/eval6.md`). No official steric helper (Rung 1 N/A), but the vendored JMD95 EOS
> reproduces its **published check value** exactly (1041.83267). Correctness rests on:
> **sum-of-parts** — thermosteric + halosteric reconstruct the full steric field (median
> residual **0.005 m**, corr **0.9998**); and **steric ≈ SSH** — steric height explains most
> of the spatial sea-level structure (corr **0.921**; non-steric residual std 0.31 m vs SSH
> std 0.79 m), an independent check against a different collection. Teeth-verified: flipping
> the specific-volume-anomaly sign flips steric-vs-SSH corr to −0.92. Full record:
> `references/acceptance.md`.

Steric height is the part of sea level set by the **density structure** of the water column
— warm/fresh (light) columns stand higher, cold/salty (dense) columns lower. It's most of
what sea-surface height measures, and its change over time is a major term in sea-level rise.

## The science (what a learner should take away)

- **The integral:** `h' = ∫ (−V'_sp / g) dp`, where the specific-volume anomaly
  `V'_sp = 1/ρ − 1/ρ_ref`. Integrated from the surface (0 dbar) **down to a reference level
  (2000 dbar)** — steric height is always *relative to* that reference depth. `ρ = rhoConst
  + RHOAnoma` is the model's own in-situ density (**no equation of state needed for the base
  term**), and `ρ_ref` is a standard profile (JMD95 at S=35, θ=0).
- **Decomposition:** recompute density holding one variable at its reference —
  **thermosteric** = `1/ρ(S_r, θ)` (temperature contribution), **halosteric** = `1/ρ(S, θ_r)`
  (salinity contribution). They sum to ≈ the full steric anomaly (a linearization; the
  residual is tiny — 0.005 m here).
- **z\* coordinate:** ECCO uses z*, so the integration thickness is scaled by
  `rstarfac = 1 + ETAN/Depth` (the free surface stretches the column) and gated by `hFacC`
  (partial bottom cells). Both are applied.
- **Masking:** land columns and **"too-shallow" columns** (bathymetry shallower than the
  2000 dbar reference — the integral never reaches the reference level) are excluded, and
  the global mean is removed (steric height is meaningful as a spatial anomaly).

## Why the vendored JMD95 equation of state

The base steric term uses the model's `RHOAnoma` directly — no EOS call. But the
**reference profile** and the **thermosteric/halosteric split** need a T,S→ρ equation of
state, and none is in the environment (`gsw`/TEOS-10 not installed; `ecco_v4_py` has no
EOS). So we vendor the canonical **MITgcm JMD95** (`ecco_common/vendor/jmd95.py`, pinned to
the same commit as `ecco_po_tutorials.py`) — the *same* EOS ECCO uses internally, so the
reference profile is consistent with the model's density. It carries a published check value
(`densjmd95(35.5, 3, 3000 dbar) = 1041.83267`) used as a self-test. Note: JMD95 wants
pressure in **dbar**, so the Pa reference pressure is scaled by 1e-4.

## How to run

```
.venv/bin/python scripts/run.py 2000-01     # steric height + thermo/halo split for Jan 2000
```

Run with the **venv** python. Loads density/pressure + temp/salinity + SSH (for ETAN and
the comparison) + geometry. Prints the runtime validation trail (grid position, units,
finiteness in valid columns, physical bounds, and the sum-of-parts residual).

## Composition (Option A)

```python
from ecco_common import load_grid, load_field
# + vendored EOS: sys.path→ecco-common/vendor; from jmd95 import densjmd95
ds_grid, _ = load_grid()
ds_dp  = load_field("ECCO_L4_DENS_STRAT_PRESS_LLC0090GRID_MONTHLY_V4R4", months=["2000-01"])
ds_ts  = load_field("ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4",   months=["2000-01"])
ds_ssh = load_field("ECCO_L4_SSH_LLC0090GRID_MONTHLY_V4R4",             months=["2000-01"])
```

## Verification (per `docs/verify.md`)

| Rung | Status | Evidence |
|------|--------|----------|
| 1 official helper | **N/A** for the steric integral. **Anchor:** the vendored JMD95 EOS reproduces its published check value 1041.83267 (automated). |
| 2 tutorial number | ✅ (operator) | Pipeline transcribed from the official Steric Height tutorial; it publishes maps, not scalars. |
| 3 conservation | N/A | Diagnostic, not a budget. |
| 4 physical sanity | ✅ | Steric anomaly (global-mean-removed) range ≈ [-3.2, 2.2] m; high in the warm subtropics/tropical Pacific, low in the Southern Ocean — matches SSH. Land + too-shallow masked. |
| 5 cross-check | ✅ | **(a) sum-of-parts:** thermo+halo ≈ full steric (median residual 0.005 m, corr 0.9998). **(b) INDEPENDENT:** steric ≈ SSH spatially, corr **0.921** (different collection/variable → the non-steric residual is the mass/barotropic part). |
| 6 regression (teeth) | ✅ | `test_steric.py`: EOS check-value + sum-of-parts + steric-vs-SSH + a teeth test (specvol sign is load-bearing: corr 0.92 → −0.92 when flipped) + offline guards. |
| 7 adversarial | ✅ | Independent Sonnet disprove-pass (2026-08-06, `docs/eval6.md`): could not disprove; zero confirmed errors; all numbers reproduced. One caveat fixed (added a thermo/halo label-swap guard vs SST). |

## Limits / honest caveats

- **Reference level matters:** steric height is relative to 2000 dbar (`P_R_DBAR`). Columns
  shallower than that are excluded (their steric height vs 2000 dbar is undefined).
- **Steric ≈ SSH is a physical relationship, not an identity:** steric explains ~85% of SSH
  variance here; the remainder is the non-steric (ocean-mass / barotropic) component — so
  don't expect corr → 1.
- **Decomposition is a linearization** about (S_r, θ_r); the sum-of-parts residual is small
  (0.005 m) but nonzero by construction.
- **Absolute vs anomaly:** only the global-mean-removed spatial anomaly is reported (the
  absolute value depends on the arbitrary reference profile). A *change over time* would be
  the sea-level-rise quantity — a natural follow-on, not built here.

## Files
- `scripts/run.py` — steric integral + thermo/halo decomposition + runtime validation trail.
- `scripts/test_steric.py` — EOS check-value + sum-of-parts + steric-vs-SSH + teeth + guards.
- `references/acceptance.md` — verification evidence.
- (EOS: `../ecco-common/vendor/jmd95.py`.)
