# ECCO Skills Design and Implementation Reevaluation

Reevaluated against:

- The updated repository design and implementation.
- The ECCO Version 4 Python Tutorial 4.4.1 documentation.
- The geostrophic-balance, native-grid curl, meridional heat transport, and
  OSNAP tutorials.
- Focused local tests of environment verification, offline caching, pagination,
  loader behavior, and ocean heat content.

Evaluation date: 2026-07-25.

## Findings

### 1. Blocker: the requested geostrophic workflow is still not implemented

The equations in `design.md` have been corrected, but Recipe 2 remains future
work in `roadmap.md`. There are no implemented spatial-difference,
spatial-interpolation, geostrophic-velocity, normalized-difference, or plotting
skills yet.

The system therefore cannot currently reproduce the complete official
geostrophic-balance tutorial:

https://ecco-v4-python-tutorial.readthedocs.io/Geostrophic_balance.html

### 2. High: tracer transport across arbitrary sections is incomplete

The heat-transport example in `design.md` uses only:

```python
(ADVx_TH + DFxE_TH) * section_mask
```

An arbitrary LLC section can cross both native X and Y faces. It requires the
signed west- and south-face masks separately:

```python
x_trsp = (ADVx_TH + DFxE_TH) * maskW
y_trsp = (ADVy_TH + DFyE_TH) * maskS
heat_transport = rho * Cp * (x_trsp.sum(...) + y_trsp.sum(...))
```

The official meridional heat-transport tutorial explicitly combines both
components and masks:

https://ecco-v4-python-tutorial.readthedocs.io/ECCO_v4_Example_MHT.html

The volume-transport example already uses separate U- and V-face masks; the
tracer-transport path needs the same directional treatment.

### 3. High: the curl correction is still scientifically incomplete

The revised `compute-curl` design rotates the input vector components, takes
model-axis derivatives, interpolates them, and then immediately combines them.
That omits the second rotation required to convert derivatives along model X/Y
into derivatives along geographic zonal/meridional directions.

For vector components already located at tracer points, such as surface stress,
the correct sequence is:

1. Rotate model X/Y components into zonal/meridional components.
2. Differentiate each geographic component along both model X and Y.
3. Interpolate the derivative pairs to tracer points.
4. Rotate each derivative pair from model derivative directions into
   zonal/meridional derivative directions.
5. Compute `curl_z = d(v_meridional)/d(x_zonal) -
   d(u_zonal)/d(y_meridional)`.

The initial interpolation should be omitted when the input components are
already at tracer points.

Reference:

https://ecco-v4-python-tutorial.readthedocs.io/ECCO_v4_Gradient_calc_on_native_grid.html

### 4. High for full tutorial reproduction: daily collections cannot be loaded

`design.md` states that daily variants exist by replacing `MONTHLY` with
`DAILY`, but `ecco_common.access.CONCEPT_IDS` contains only monthly collection
IDs. `load_field()` rejects any ShortName that is not in that mapping.

The geostrophic tutorial uses both monthly and daily velocity and
density/pressure datasets. The current loader is adequate for a deliberately
monthly-only first milestone, but it cannot reproduce the complete tutorial.

Add the required daily collection IDs or replace the fixed mapping with a safe
CMR collection lookup.

### 5. Medium: offline cache reuse remains fragile

The new index enables offline reuse for indexed files, and that path works.
However:

- `cache_index.json` is rewritten without locking.
- The write is not atomic.
- Corrupt JSON is silently treated as an empty index.
- Existing cached files are not discovered or backfilled when the index lacks
  their entries.

The local 1999-12 and 2010-01 temperature files exist but are absent from the
index, so they cannot currently be resolved offline. Concurrent agent or skill
runs could also lose mappings through read-modify-write races.

Add cache discovery/backfill and use an atomic temporary-file replacement with
appropriate locking.

### 6. Medium: `load_field()` does not enforce its selector contract

The function documents that exactly one of `months` or `start/end` should be
given, but it does not enforce this:

- Passing both selectors silently ignores `start/end`.
- Passing `months=[]` eventually raises `OSError: no files to open`.
- Passing no selector initiates a broad collection query.

These cases should fail immediately with explicit `ValueError` messages before
performing network or filesystem work.

### 7. Medium: OHC validation is improved but still incomplete

The wet-cell finite-value guard now works, and the validation tests prove that
it fires. Remaining gaps:

- `compute_ohc_one_month()` selects `time=0` without verifying that the returned
  time coordinate matches the requested month.
- Collection identity and granule identity are not recorded in the result.
- The L2 "units" check only checks finite scalars and positive volume; the unit
  equation is still a hardcoded message rather than a machine-checked unit
  assertion.
- The OHC change itself has no validation beyond validation of the two
  snapshots.
- There is no automated end-to-end golden-value regression.

At minimum, assert the returned year/month before computing. Relabel L2 as
numeric-result sanity unless real unit propagation or explicit metadata
assertions are added.

### 8. Low: documentation drift remains

Examples:

- `design.md` proposes cross-checking against
  `ecco_v4_py.geos_vel_compute`, but that function is absent from the installed
  `ecco_v4_py` 1.8.1 package. `geos_vel_compute` belongs to the separately
  downloadable `ecco_po_tutorials.py` helper.
- `roadmap.md` calls `compute-tracer-budget` "Recipe 3", while Recipe 3 in
  `design.md` is thermal wind.
- `roadmap.md` says the curl issue is fixed, but the required derivative-vector
  rotation is still missing.
- `plot_proj_to_latlon_grid` remains listed as unverified even though its
  installed signature is available and was inspected successfully.

### 9. Medium: reproducibility and regression automation are not yet provided

`requirements.txt` uses lower bounds for nearly every dependency rather than an
exact tested lock. The directory is not currently a Git repository, and there
is no CI suite.

The handwritten OHC acceptance record is useful evidence, but it is not an
automated golden-value regression. Before calling the system reproducible:

- Add an exact dependency lock under a stated Python/platform policy.
- Add automated loader, cache, pagination, calculation, and golden-result
  tests.
- Record source granule identifiers, timestamps, sizes, and checksums.
- Run the acceptance suite in CI.

## Corrected Since the First Evaluation

The following previous findings are now corrected or materially improved:

- The geostrophic pressure-gradient formula now includes `rhoConst` and divides
  by actual density `rhoConst + RHOAnoma`.
- Eulerian section volume transport no longer multiplies `UVELMASS` or
  `VVELMASS` by `hFac` or adds bolus velocity.
- Project and cache paths are derived from source-file locations rather than
  the caller's working directory.
- Indexed grid and field files can be reused without a CMR request.
- CMR `Search-After` pagination retrieves multiple pages.
- OHC validation catches non-finite values in wet cells.
- OHC L2 now rejects non-finite results and non-positive volume instead of
  always passing.
- Setup verification reads geometry from the project cache.

## Verification Results

The reevaluation ran the following checks:

### Environment verification from outside the repository

`verify_env.py` was launched by absolute path with `/private/tmp` as its working
directory.

Result:

- Python 3.12.13 accepted.
- All 11 required imports passed.
- Installed `xgcm` is 0.9.0.
- `ecco.get_llc_grid()` succeeded.
- A real X-direction grid difference produced the expected staggered
  dimensions.

### Offline cache

CMR was replaced with an intentionally invalid host and the loaders were
invoked from `/private/tmp`.

Result:

- Indexed geometry loaded successfully.
- Indexed January 2000 temperature/salinity loaded successfully.
- Both used the project-level `data/ecco` cache.

### CMR pagination

A synthetic three-page `CMR-Search-After` response was supplied.

Result:

- All three pages were retrieved.
- Tokens were passed in the expected sequence.
- All three filenames were returned.

### OHC validation tests

All 10 positive and negative validation cases passed, including:

- Wet-cell NaN rejected.
- Land-cell NaN accepted.
- Non-finite volume mean rejected.
- Bad units, dimensions, bounds, and ocean volume rejected.

### OHC end-to-end

January 2000 completed successfully from the cache:

```text
OHC relative to 0 degC:       1.9720e25 J
Volume-mean THETA:            3.594 degC
Ocean volume:                 1.335e18 m3
```

All applicable runtime checks passed.

### Static verification

Python compilation of all files under `.claude/skills` completed without
errors.

## Verdict

Phase 1 is in reasonable prototype condition, and most implementation defects
from the first evaluation were fixed.

The system is not yet ready to claim reproduction of the geostrophic-balance
tutorial or scientifically safe arbitrary-section tracer transport and curl
calculations. The recommended next sequence is:

1. Correct the remaining curl and tracer-section designs.
2. Harden loader selector validation and cache indexing.
3. Add the daily collections needed by the full geostrophic tutorial.
4. Implement Recipe 2.
5. Validate Recipe 2 against the official helper/tutorial using an automated
   end-to-end regression.
