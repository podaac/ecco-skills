# ECCO Skills Design and Implementation Evaluation

Evaluated against:

- The current repository design and implementation.
- The complete ECCO Version 4 Python Tutorial 4.4.1 documentation navigation.
- The `Geostrophic_balance` tutorial and its `ecco_po_tutorials.py` helper.
- Local end-to-end and validation runs using the project's existing ECCO data.

Evaluation date: 2026-07-25.

## Findings

### 1. Critical: Geostrophic balance is not implemented, and the proposed formula omits density

There is no geostrophic skill yet, so the system cannot currently reproduce the
requested tutorial. More importantly, `design.md` defines:

```python
v_g = (1/f) * d(PHIHYDcR)/dx
u_g = -(1/f) * d(PHIHYDcR)/dy
```

The tutorial computes `rhoConst * d(PHIHYDcR)/dx`, then divides by actual density
`rhoConst + RHOAnoma` and `f`. Omitting `rhoConst/rho` introduces a spatially varying
error of roughly a few percent. Recipe 2 also fails to list `RHOAnoma` as an input.

Reference:
[official geostrophic-balance calculation](https://ecco-v4-python-tutorial.readthedocs.io/Geostrophic_balance.html).

### 2. Critical: The raw section-transport recipe applies the wrong factors

`design.md` multiplies `UVELMASS + UVELSTAR` by `hFacW`. `UVELMASS` and `UVELSTAR`
are already scaled for partial and time-varying cell thickness, so multiplying by
`hFacW` again double-counts partial cells.

The installed official `calc_section_vol_trsp` uses:

```python
x_vol = UVELMASS * drF * dyG
y_vol = VVELMASS * drF * dxG
```

It does not multiply by `hFacW`/`hFacS` or add bolus velocity. Bolus belongs in
reconstructed tracer transport, not ordinary volume transport.

The precomputed `ADV + DF` heat/salt path is the correct production default,
consistent with the
[official MHT tutorial](https://ecco-v4-python-tutorial.readthedocs.io/ECCO_v4_Example_MHT.html).

### 3. High: The proposed curl primitive is insufficient for Ekman pumping

`design.md` reduces curl to two native-grid differences:

```python
curl = d(v_field)/dx - d(u_field)/dy
```

On LLC90, centered stress components must first be rotated into geographic
zonal/meridional components. Their gradients are then differenced, interpolated,
and rotated again. The
[native-grid gradient and curl tutorial](https://ecco-v4-python-tutorial.readthedocs.io/ECCO_v4_Gradient_calc_on_native_grid.html)
explicitly uses that sequence.

This sequence must be encoded in `compute-curl`, not left to agent inference.

### 4. High: OHC computes correctly, but its validation does not meet the documented contract

The OHC runtime checks basic dimensions and units, but its Layer 2 unit check is an
unconditional success message. It does not validate:

- The requested time coordinate.
- Collection identity.
- Finite values in wet cells.
- The OHC change itself.
- Symbolic or machine-checkable output units.

A synthetic THETA array containing a NaN still returns `True` from `validate()`.
The current real files contain zero wet-cell NaNs, but the guard would not detect
future corruption.

The seven existing tests prove that several explicit boolean guards fire. They do
not test the complete calculation, loader behavior, time selection, NaN handling,
or unit propagation.

### 5. High: Project behavior depends on the caller's working directory

Setup, verification, and cache roots use `os.getcwd()`:

- `.claude/skills/ecco-setup/scripts/setup_env.py`
- `.claude/skills/ecco-setup-verify/scripts/verify_env.py`
- `.claude/skills/ecco-common/ecco_common/cache.py`

Running verification from its skill directory incorrectly reports that no `.venv`
exists. Running a loader there targets:

```text
.claude/skills/load-grid/data/ecco
```

instead of the project-level `data/ecco`.

Agent skills cannot safely assume repository-root CWD. The project root should be
derived from the script/package location or passed explicitly.

### 6. High: The cache is not actually usable offline, and broad queries truncate silently

The loaders query CMR before checking local files. Fully cached calculations
therefore still fail without network access.

The CMR client also requests one page of 200 granules without pagination. A daily
or full-record `start/end` request can silently omit everything after the first
200 results.

Required changes:

- Resolve known cached filenames before making a metadata request when possible.
- Store enough granule metadata locally to support offline cache reuse.
- Implement CMR pagination and assert that all result pages were retrieved.
- Validate file size or checksum before treating a cached file as complete.

### 7. High: Arbitrary-volume budget support is substantially under-specified

Exact closure requires:

- The correct state snapshots and time bounds.
- Surface forcing terms.
- Correct vertical boundary handling.
- The model's z-star conventions.
- Complete advective and diffusive term lists.
- A dimensioned or normalized residual definition.

The loader currently knows only ten monthly collections and lacks several forcing
and snapshot collections needed for the advertised budgets.

The statement "closes to ~1e-10" is not meaningful without units and
normalization. The tutorials report different residual units and scales for
volume, heat, and salt. Certain daily snapshots specifically exist to support
closure.

References:

- [ECCO field-frequency documentation](https://ecco-v4-python-tutorial.readthedocs.io/fields.html)
- [Heat-budget tutorial](https://ecco-v4-python-tutorial.readthedocs.io/ECCO_v4_Heat_budget_closure.html)
- [Volume-budget tutorial](https://ecco-v4-python-tutorial.readthedocs.io/ECCO_v4_Volume_budget_closure.html)
- [Salt/salinity/freshwater-budget tutorial](https://ecco-v4-python-tutorial.readthedocs.io/ECCO_v4_Salt_and_salinity_budget.html)

### 8. Medium: The single source of truth already contains drift

Examples include:

- The project cache versus the `~/Downloads` verification path.
- Credential checks promised by the design but excluded by the setup skill.
- Recipe 3 meaning thermal wind in `design.md` but tracer budget in `roadmap.md`.
- Resolved questions still listed as unverified.
- `--reset` implemented while part of the decisions section describes reset as future.
- `load-field` described as supporting local/S3 access modes while its implementation
  only downloads to a local cache.
- The current Intro to PO section containing four calculation notebooks
  (Geostrophic Balance, Thermal Wind, Steric Height 3a, and Steric Height 3b), while
  the design refers to three tutorials.

The Python 3.12 ceiling rationale is also stale. `ecco_access` supports Python 3.13
and Cartopy 0.25 publishes Python 3.13 wheels. A conservative tested band is
reasonable, but it should be described as tested policy rather than current wheel
availability.

References:

- [ecco-access on PyPI](https://pypi.org/project/ecco-access/)
- [Cartopy 0.25 release metadata](https://pypi.org/pypi/Cartopy/0.25.0/json)

### 9. Medium: Reproducibility is promised but not yet provided

`requirements.txt` uses lower bounds for almost every dependency. A future install
can resolve to versions that were never tested and can produce different behavior.
The existing `xgcm<0.10` ceiling is important, but it is not a complete lock.

The acceptance evidence is a handwritten Markdown record rather than output
generated and checked by an automated regression suite.

Before calling the helpers reproducible:

- Add an exact lock file for each supported Python/platform policy.
- Add automated loader, calculation, and golden-result tests.
- Record input granule identifiers and checksums with acceptance results.
- Run the acceptance suite in CI.

## What Is Correct

The overall architecture is sound. Guidance plus vetted helpers plus acceptance
evidence is the right model for scientific guardrails.

The following foundations are correct or directionally strong:

- LLC90 and Arakawa C-grid staggering are treated as first-class concerns.
- Cell volume uses `rA * drF * hFacC`.
- Vertical section calculations distinguish face area from horizontal area.
- `PHIHYDcR` is correctly selected instead of the time-varying-depth pressure field.
- The `xgcm<0.10` compatibility issue is understood and tested locally.
- GM bolus transport is recognized as necessary for tracer transport.
- Precomputed model tracer-flux diagnostics are preferred for production heat/salt
  transport and budget calculations.
- `ecco_v4_py.get_section_line_masks` and section transport helpers exist in the
  installed package.
- The month-midpoint CMR query avoids the adjacent-month overlap problem.
- Downloads use a temporary `.part` file followed by an atomic replace.
- The download-size guard is a useful safety feature.
- The roadmap correctly places geostrophic balance after the foundational loaders.

## Verification Results

### OHC end-to-end run

The December 1999 to January 2000 calculation completed successfully using the
project cache:

```text
OHC change: +1.1195e22 J
Ocean volume: 1.335e18 m3
Volume-mean THETA: 3.592 -> 3.594 degC
```

The calculation agrees with the implementation's documented results and the cell
volume is physically reasonable.

### Other checks

```text
OHC validation test cases: 7/7 passed
Python compileall: passed
Environment imports: passed
ecco.get_llc_grid + X diff smoke test: passed
```

The environment smoke test passed from the repository root, but it used a duplicate
geometry file under `~/Downloads`. A clean machine with only the project cache would
skip that definitive test because `verify_env.py` checks the wrong location.

## Verdict

This is a strong prototype and a credible proposal foundation, but it is not yet a
reliable general ECCO skill system.

Today it has one working scientific vertical slice: ocean heat content. It cannot
yet perform the requested geostrophic-balance workflow. The proposal should describe
the current state as:

> One validated calculation skill and a tested data/environment foundation, with a
> planned hierarchy for geostrophic balance, transports, budgets, and diagnostics.

It should not yet claim that all questions in the design's user-question table have
trustworthy answer paths.

## Recommended Next Milestone

Build one complete `compute-geostrophic-balance` skill before expanding into
transports and budgets.

It should:

1. Load `RHOAnoma`, `PHIHYDcR`, `UVEL`, `VVEL`, and grid geometry for the tutorial's
   reference month.
2. Replace velocity land NaNs with zero before vector interpolation.
3. Compute pressure gradients as:

   ```python
   dp_dx = interp(diff(rhoConst * PHIHYDcR, "X") / dxC)
   dp_dy = interp(diff(rhoConst * PHIHYDcR, "Y") / dyC)
   ```

4. Compute actual density as `rhoConst + RHOAnoma`.
5. Compute `f` from `YC`.
6. Compare the geostrophic terms using the tutorial's exact equations:

   ```python
   v_g = dp_dx / (rho * f)
   u_g = -dp_dy / (rho * f)
   ```

7. Mask land, the equatorial singularity, and very small reference velocities.
8. Keep both sides in model coordinates for like-for-like balance checks.
9. Rotate both actual and geostrophic vectors consistently when geographic output
   is requested.
10. Produce the single-tile and global maps used by the tutorial.
11. Report normalized residuals by latitude and depth using area weighting.
12. Cross-check computed velocities against the official `geos_vel_compute` helper.
13. Store quantitative golden summaries and figure evidence in `references/`.
14. Include negative tests for wrong pressure field, missing density correction,
    incorrect grid metrics, unmasked equator, wrong staggering, and inconsistent
    rotation.

Before using that skill as the template, fix project-root discovery, offline cache
reuse, CMR pagination, time/NaN/unit validation, and the design-document
inconsistencies listed above.

Transport and budget skills should remain gated on Phil's review, especially for:

- Volume transport versus tracer residual transport.
- Exact diagnostic term lists and signs.
- Temporal sampling and snapshot requirements.
- Residual definitions, units, and tolerances.
- External benchmark values and acceptable deviations.
