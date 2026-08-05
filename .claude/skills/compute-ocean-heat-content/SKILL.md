---
name: compute-ocean-heat-content
description: Compute global ocean heat content (OHC) from ECCO, as a volume-weighted sum of potential temperature, and report the change between two months. Chains load-grid + load-field, applies the volume weighting correctly (rA·drF·hFacC), and prints a validation trail (physical bounds, ocean-volume benchmark). Use for questions about ocean heat content, ocean warming, or Earth's energy imbalance. Requires the ecco-setup environment.
---

# compute-ocean-heat-content (Recipe 1)

> **🔬 Verification status (per `docs/verify.md`): ✅ DONE (2026-07-25).** All applicable
> rungs cleared: tutorial-number match (Rung 2, ocean surface area 3.58E+08 km² — automated
> test), physical sanity (Rung 4), volume cross-check within 0.4% of literature (Rung 5),
> teeth-verified regression tests (Rung 6), and a clean independent **adversarial pass**
> (Rung 7 — zero confirmed errors). Rung 1 N/A (no official OHC helper exists); Rung 3 N/A
> (snapshot, not a budget). Two documented physical caveats remain (z\*/SSH volume term;
> snapshot aliasing — see Limits). Full record: `references/acceptance.md`.

Global volume-integrated ocean heat content:

```
OHC = Σ_wet-cells  THETA · rhoConst · Cp · (rA · drF · hFacC)
```

This is the **reference calculation skill** — the simplest end-to-end science, and the
template every later calc copies: import `ecco_common` building blocks → compute →
run the applicable validation layers → print the trail (teach-as-you-go).

## The science (what a learner should take away)

- **THETA is *potential* temperature** (degC). So OHC here is heat content *relative to
  0 degC* — an arbitrary baseline. The **absolute** number is not physically meaningful
  on its own; the **change** between two times is. Always prefer a change.
- **Volume weighting is the crux.** Each cell's ocean volume is `rA · drF · hFacC`:
  area × layer thickness × the open (wet) fraction. `hFacC` handles partial cells at
  the seafloor and is 0 on land, so it doubles as the land mask. Getting this factor
  right is exactly the kind of thing this skill encodes so it isn't re-derived (wrongly)
  each time.
- **Constants:** `rhoConst = 1029 kg m-3` (Boussinesq reference density), `Cp = 3994
  J kg-1 K-1` (seawater heat capacity) — ECCO/MITgcm values.

## How to run

```
.venv/bin/python scripts/run.py 2000-01              # OHC for one month
.venv/bin/python scripts/run.py 2000-01 2010-01      # OHC change between two months
```

Run with the **venv** python (design.md → Interpreter policy). First use downloads the
temp/salinity granule(s) (~17 MB each) and caches them; the grid comes from `load-grid`.

## Composition (Option A)

This skill imports the shared building blocks — it does **not** re-implement download,
caching, or grid loading:

```python
from ecco_common import load_grid, load_field
ds_grid, _ = load_grid()
ds = load_field("ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4", months=["2000-01"])
```

## Validation trail (printed every run)

| Layer | Check |
|-------|-------|
| L1 input | THETA is on tracer points, units are degC |
| L2 numeric sanity | result finite & volume > 0 (unit chain degC × kg m-3 × J kg-1 K-1 × m3 → J is *documented*, not machine-checked) |
| L3 bounds | THETA within [-2.5, 40] degC; volume-mean ≈ 3.5 degC (the ocean is cold) |
| L4 closure | N/A — a snapshot heat content is not a budget (no conservation to close) |
| L6 benchmark | total ocean volume ≈ 1.34×10¹⁸ m³ (validates the volume machinery) |

If any mandatory check fails, the run reports "do not trust the number" and exits
non-zero.

## Known-good result (acceptance)

On Jan 2000: volume-mean THETA ≈ **3.59 degC**, ocean volume ≈ **1.335×10¹⁸ m³**
(0.4% from literature), OHC ≈ 1.97×10²⁵ J vs 0 degC. Jan 2000→2010 change ≈
**+7.8×10²² J** (ocean warming; right sign and order of magnitude vs published ~10²²
J/yr uptake). See `references/acceptance.md`.

## Limits / honest caveats

*(Items 1–2 confirmed by the 2026-07-25 adversarial review as legitimate caveats, not errors.)*

- **Seasonal/interannual aliasing.** A two-month **snapshot difference** aliases
  seasonal + interannual variability into the "change." Jan→Jan reduces seasonal
  aliasing but doesn't remove interannual noise. For a rigorous OHC *trend*, use annual
  means / average seasonal cycles — a future refinement.
- **Fixed geometry ignores z\*/SSH.** ECCO v4r4 uses z* vertical coordinates: true cell
  thickness is `drF·hFacC·(1 + η/Depth)`. This skill uses the *static* geometry `hFacC`,
  so the sea-surface-height contribution to volume (and to the OHC change) is omitted.
  The effect is small (η is cm–dm over a full-depth column) and omitting it is standard
  for snapshot OHC, but it means the "change" reflects the temperature term only, not
  the volume term. Documenting, not fixing, for now.
- **Absolute OHC depends on the 0 degC baseline; only differences are physical.**
