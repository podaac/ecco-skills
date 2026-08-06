# ECCO Skills Design and Implementation Reevaluation 3

Reevaluated against:

- The repository after the `eval2.md` fixes.
- The ECCO Version 4 Python Tutorial 4.4.1 documentation.
- Live NASA CMR metadata for monthly and daily Recipe 2 collections.
- Focused local tests of selector validation, cache backfill, pagination,
  environment verification, OHC time validation, and end-to-end OHC.

Evaluation date: 2026-07-25.

## Findings

### 1. High: the download-size guard is unreliable

`ecco_common.access.granules_for()` selects the first
`ArchiveAndDistributionInformation` entry whose unit is MB. For several
granules, that first entry describes the `.sha512` checksum sidecar rather than
the NetCDF file.

Observed from live CMR:

```text
Daily velocity reported by the loader:       0.000184 MB
Actual NetCDF size in the same CMR record:   29.26 MB

Monthly density/pressure reported:           0.000189 MB
Actual NetCDF size:                          approximately 30 MB
```

CMR's record contains separate archive entries such as:

```text
OCEAN_VELOCITY_...nc.sha512   193 bytes
OCEAN_VELOCITY_...nc          30,680,223 bytes
```

The loader currently takes the first one. Consequently, the 1 GB size guard can
approve a request that is actually hundreds of gigabytes.

Required correction:

1. Select the archive entry whose `Name` exactly matches the selected NetCDF
   filename.
2. Prefer `SizeInBytes` as the canonical size.
3. Retain the matching checksum value and algorithm.
4. Verify downloaded and cached files against the expected size and checksum.
5. Add regression data where the checksum sidecar is listed before the NetCDF.

### 2. High: exact daily selection has the temporal-overlap bug

A live CMR query for:

```text
start = 2000-01-01T00:00:00Z
end   = 2000-01-01T23:59:59Z
```

returned two daily granules for both velocity and density/pressure:

```text
1999-12-31
2000-01-01
```

The daily granules' temporal bounds meet at midnight, so a range beginning
exactly at midnight also intersects the previous daily mean. A query beginning
at `00:00:01Z`, or a narrow query around noon, returned only January 1.

The existing month-midpoint selector protects monthly data, but the raw
`start/end` path recommended for daily data has no equivalent protection or
post-query filtering. It therefore cannot yet safely reproduce the daily
portion of the official geostrophic-balance tutorial:

https://ecco-v4-python-tutorial.readthedocs.io/Geostrophic_balance.html

Recommended correction:

- Add a `days=["YYYY-MM-DD", ...]` selector that queries safely inside each
  requested day.
- Match returned granule filenames to the requested dates.
- Verify the opened dataset's time coordinates before returning it.
- Reject duplicate or unexpected dates.
- Add boundary tests covering adjacent days.

### 3. High: volume-transport pseudocode broadcasts staggered arrays

The current volume example adds U-face and V-face arrays before summing:

```python
((UVELMASS * drF * dyG) * maskW
 + (VVELMASS * drF * dxG) * maskS).sum(section_dims)
```

Those terms have different dimensions:

```text
U-face: tile, j,   i_g
V-face: tile, j_g, i
```

Adding them directly causes xarray to outer-broadcast across `j`, `j_g`, `i`,
and `i_g`, creating a very large and incorrect intermediate array.

Each face contribution must be reduced over its own dimensions before addition:

```python
x_vol = (UVELMASS * drF * dyG * maskW).sum(
    ["k", "tile", "j", "i_g"]
)
y_vol = (VVELMASS * drF * dxG * maskS).sum(
    ["k", "tile", "j_g", "i"]
)
vol_transport = x_vol + y_vol
```

The heat and salt examples already reduce X and Y terms separately, but their
single `section_dims` placeholder is still ambiguous. They should explicitly
use the corresponding X-face and Y-face dimension lists.

Reference:

https://ecco-v4-python-tutorial.readthedocs.io/ECCO_v4_Example_MHT.html

### 4. Medium: the new foundation fixes have no automated tests

The only current test module is:

```text
.claude/skills/compute-ocean-heat-content/scripts/test_validation.py
```

There are no repository tests for:

- CMR pagination.
- Correct NetCDF archive metadata selection.
- Download-size guard calculations.
- Daily temporal selection.
- Live ShortName resolution.
- `load_field` selector rejection.
- Cache-index backfill.
- Atomic cache-index replacement.
- Offline reuse after backfill.
- OHC requested-time mismatch.

These behaviors passed some focused manual checks, but they need a committed
`ecco-common` test suite before Recipe 2 depends on them.

### 5. Medium: Recipe 2 lacks a concrete acceptance contract

The design requires reproduction of a tutorial's published result, but the
geostrophic tutorial primarily supplies arrays and figures rather than one
scalar golden number.

Before implementation, define and record:

- Initial scope: January 2000 monthly means.
- Exact velocity, density/pressure, and geometry granules.
- Granule sizes and checksums.
- Expected input variables, dimensions, units, and time coordinates.
- The exact masking sequence.
- Equatorial cutoff.
- The tutorial's `0.005 m/s` small-velocity cutoff.
- Array comparison against
  `ecco_po_tutorials.geos_vel_compute`.
- Numerical `rtol` and `atol`.
- Reference summaries for `u_g`, `v_g`, and normalized differences.
- Expected single-tile and global figures.

The official helper should be used as build-time reference evidence, not
assumed to be part of `ecco_v4_py`.

### 6. Medium: `spatial-difference` is described too generically

The design currently presents:

```python
diff_x = grid.diff(field, "X", boundary="extend") / dxC
diff_y = grid.diff(field, "Y", boundary="extend") / dyC
```

This is correct for Recipe 2's tracer-center to face pressure gradients. It is
not a general rule for every staggered field; the correct metric depends on the
input and output grid positions.

Choose one of these contracts:

1. Scope the first implementation explicitly to scalar center-to-face
   gradients using `dxC` and `dyC`.
2. Require source and target grid positions and select/assert the appropriate
   metric for every supported transition.

A generic-looking helper that silently assumes tracer-center input will be
misused by later velocity, curl, and transport skills.

### 7. Low: documentation remains internally inconsistent

Remaining examples:

- Recipe 6's shorthand still says
  `interp -> rotate -> diff -> recombine`, omitting the second derivative-vector
  rotation and implying that centered stress needs initial interpolation.
- The detailed curl pseudocode says stress should skip interpolation but then
  refers to `vec`, which is assigned only by the skipped interpolation step.
  The centered-input branch needs to assign the model components directly.
- The OHC `SKILL.md` validation table still labels L2 as a unit check, while the
  runtime correctly labels it numeric sanity and states that units are not
  machine-checked.
- Cache writes are atomic but remain vulnerable to concurrent lost updates,
  which the design now acknowledges.
- Recipe 4's summary lists only the X tracer-flux names even though the detailed
  section correctly requires both X and Y components.

## Verified Correct

The following `eval2.md` corrections are present and passed inspection or
focused testing:

- Tracer section transport now conceptually combines X- and Y-face
  contributions with `maskW` and `maskS`.
- The detailed curl design now includes both mandatory rotations.
- The four newly added daily collection IDs returned real CMR granules.
- `load_field()` rejects both, neither, and empty selector cases before I/O.
- Cache backfill discovers pre-index monthly files.
- Cache index replacement is atomic.
- Indexed files load from outside the repository without CMR.
- OHC rejects a loaded time coordinate that does not match the requested month.
- The OHC runtime reports L2 honestly as numeric sanity.
- Environment verification passes from `/private/tmp`.
- All required imports and the real LLC grid-difference smoke test pass.
- Python compilation under `.claude/skills` passes.
- All 10 OHC validation tests pass.

## End-to-End OHC Regression

The cached December 1999 to January 2000 calculation completed successfully:

```text
December 1999 OHC:             1.9709e25 J
January 2000 OHC:              1.9720e25 J
OHC change:                   +1.1195e22 J
Ocean volume:                  1.335e18 m3
```

Both requested-time checks passed, and all applicable OHC validation checks
passed.

## Recipe 2 Gate

The Level 1 implementation can start if the initial Recipe 2 milestone is
explicitly restricted to the January 2000 monthly calculation.

Before calling Recipe 2 end-to-end ready:

1. Fix NetCDF metadata selection so the size guard is trustworthy.
2. Define the Recipe 2 acceptance inputs, masks, tolerances, and reference
   artifacts.
3. Add automated tests for the new common-loader behavior.
4. Implement safe daily selection before claiming reproduction of the complete
   geostrophic tutorial.

The monthly Recipe 2 work is a conditional go. Complete tutorial reproduction
is not yet ready.
