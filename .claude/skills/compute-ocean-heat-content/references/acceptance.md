# Acceptance evidence — compute-ocean-heat-content

Build-time acceptance testing (see design.md → Build-time acceptance testing). This
records why we trust the skill's implementation.

## V&V status (per docs/verify.md) — updated 2026-07-25

**Overall: ✅ DONE (all applicable rungs cleared 2026-07-25).** Rung 1 N/A (no helper
exists); Rungs 2,4,5,6 ✅; Rung 3 N/A (snapshot); Rung 7 ✅ (adversarial pass clean).

| Rung | Status | Evidence |
|------|--------|----------|
| 1 — official-helper match | **N/A** | Confirmed no OHC/volume-weighted-mean helper exists in `ecco_v4_py` 1.8.1 (checked `dir()`, `scalar_calc` submodule = mask helpers only). No helper to match against, so this rung cannot apply. Cell-volume machinery instead cross-checked (see Rung 5). |
| 2 — tutorial number | ✅ | Reproduces the `ECCO_v4_Example_calculations_with_scalar_quantities` tutorial's published **total ocean surface area = 3.58E+08 km²** exactly, via its formula `(rA·maskC).isel(k=0).sum()/1e6`. Now an automated test in `scripts/test_validation.py` (skips gracefully if grid not cached). The tutorial publishes no OHC scalar directly, so this anchors the grid geometry the OHC weighting is built on. |
| 3 — conservation | N/A | A snapshot heat content is not a budget; nothing to close. |
| 4 — physical sanity | ✅ | volume-mean THETA 3.594 °C (≈ known ~3.5); THETA range [-1.97, 31.94] °C; runtime L3 guard. |
| 5 — internal cross-check | ✅ | Ocean volume `rA·drF·hFacC` = 1.335e18 m³, within 0.4% of literature ~1.34e18. Also confirmed `hFacC` already zeroes land (volume identical with/without `maskC`). |
| 6 — regression (teeth) | ✅ | `scripts/test_validation.py` (10 cases) + `ecco-common/tests/` (13). Teeth verified: reintroducing the size-guard sidecar bug fails the suite. |
| 7 — adversarial review | ✅ | Dedicated "disprove OHC" pass by an independent agent (2026-07-25): **zero confirmed errors**. It verified as correct: cell-volume formula, no hFacC/maskC double-count (tested identical to last digit), constants, potential-temp usage, NaN handling, that 3.59 °C / 1.335e18 m³ are known values not coincidence, the baseline-cancelling change computation, and that no official helper is being skipped. Raised 3 caveats (not errors): z\*/SSH omission + snapshot aliasing (both now documented in SKILL.md), and a loose L3 band (fixed: `[0,10]`→`[2,6]` °C). |

## Adversarial review (Rung 7) — 2026-07-25

An independent agent was instructed to *disprove* the calculation. Verdict: could not —
zero confirmed errors after attacking volume formula, double-counting, constants,
temperature variable, NaN bias, benchmark validity, and the change computation. Actions
taken from its caveats: tightened the L3 volume-mean band to `[2,6]` °C; documented the
z\*/SSH volume omission and snapshot-aliasing caveats in `SKILL.md`.

**Conclusion:** OHC meets verify.md's "done" bar — every applicable rung satisfied with
recorded evidence, teeth-verified regression tests, and a clean adversarial pass. Report
as ✅ (verified), noting the two documented physical caveats.

## Run environment
- macOS/arm64, project `.venv`, Python 3.12.13, xgcm 0.9.0, ecco_v4_py 1.8.1.
- Data: `ECCO_L4_TEMP_SALINITY_LLC0090GRID_MONTHLY_V4R4`, `ECCO_L4_GEOMETRY_…`.
- Verified 2026-07-23.

## Results

### Jan 2000 (single month)
- volume-mean potential temperature: **3.594 degC**
- total ocean volume: **1.335×10¹⁸ m³**
- OHC (vs 0 degC): **1.9720×10²⁵ J**

### Jan 2000 → Jan 2010 (change)
- OHC change: **+7.83×10²² J**
- volume-mean THETA: 3.594 → 3.609 degC

## Why these pass acceptance

1. **Volume-mean temperature ≈ 3.5 degC.** The global ocean's volume-mean potential
   temperature is a well-known value near 3.5 degC. Hitting 3.59 degC independently
   confirms both the field load and the volume weighting.
2. **Ocean volume within 0.4% of literature** (~1.34×10¹⁸ m³). Validates the
   `rA·drF·hFacC` cell-volume machinery and the land masking (via hFacC).
3. **Warming has the right sign and magnitude.** +7.8×10²² J/decade is consistent with
   published ocean heat-uptake estimates (~10²² J/yr order of magnitude).
4. **Validation layers fire.** L1/L2/L3/L6 all report ✓ on good data; the script exits
   non-zero if any mandatory check fails.

## Known limitations (not acceptance failures)
- Snapshot month-to-month difference, not a seasonal-cycle-corrected trend. Fine for
  validating the machinery; a rigorous climate trend needs annual/seasonal averaging.
- Absolute OHC is baseline-dependent (relative to 0 degC); only changes are physical.

## Negative + positive tests (done — 2026-07-23; extended 2026-07-25)

`scripts/test_validation.py` proves the guards actually fire, not just pass on good
data. Run: `.venv/bin/python scripts/test_validation.py`. All 10 cases pass:

- ✓ good ocean data → validate() True (positive control)
- ✓ THETA in Kelvin → L3 fails (the classic mistake)
- ✓ too-warm volume mean (e.g. surface-only) → L3 fails
- ✓ wrong units metadata → L1 fails
- ✓ non-tracer dims (j_g/i_g) → L1 fails
- ✓ bad ocean volume → L6 fails
- ✓ absurd hot THETA → L3 fails
- ✓ **wet-cell NaN → L1 finite fails** (added 2026-07-25, external-eval fix #4)
- ✓ **non-finite volume-mean (no mask) → L1/L2 fails** (added 2026-07-25)
- ✓ **land-cell NaN → still passes** (land NaNs are legitimate; added 2026-07-25)

**2026-07-25 hardening (external eval #4):** L1 now checks for non-finite values in
*wet* cells (a wet-cell NaN previously slipped through as `True`), and L2 is a real
finiteness/`volume>0` assertion rather than an unconditional success message.

This closes the "a guard that only ever passes could be silently broken" gap. Uses tiny
synthetic arrays — no download needed.

## TODO (future hardening)
- Cross-check against `ecco_v4_py`'s own volume/OHC helpers if available.
