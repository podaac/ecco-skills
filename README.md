# ECCO Skills

**Ask ocean-science questions of [ECCO](https://ecco-group.org/) — and get answers you can actually trust.**

ECCO is a global ocean "state estimate": a physics-faithful reconstruction of the ocean from 1992–2017 (temperature, salinity, currents, sea level, and more). Getting a *correct* number out of it is surprisingly easy to get wrong — the data lives on an unusual grid with rules that trip up even careful code.

**ECCO Skills** are guardrails that let an AI assistant do these calculations the right way. You ask a question in plain language; the assistant runs a vetted, step-by-step recipe and shows its work — including the evidence that the answer is right.

> **Status:** early but real. A tested data/environment foundation plus **five fully validated science calculations** — ocean heat content, geostrophic balance, thermal wind, wind-stress curl + Ekman pumping, and steric height — all built and independently error-checked. More (ocean transports, budgets) are designed and gated on domain-expert review. See [Build status](#build-status).

---

## Skills

Each skill is a self-contained guardrail (guidance + vetted code + verification evidence). They compose bottom-up: the **science** skills chain the **data** and **grid** skills through the shared `ecco-common` library.

| Skill | Kind | What it does | Scientist Verified |
|-------|------|--------------|--------------------|
| `ecco-setup` | 🌱 environment | Surveys the machine's Python, builds an isolated project-local `.venv` (3.11–3.12, pip only, no conda), installs the scientific stack — and **verifies** it works (imports + a real `ecco.get_llc_grid` smoke test). Has a standalone *verify mode* to health-check an existing environment without rebuilding. | ⏳ Pending |
| `ecco-common` | ⚓ shared library | The building blocks every skill imports: data loaders, on-demand cache, direct NASA-CMR download, plotting, and Level-1 grid primitives (`grid_ops`). Not invoked directly. | ⏳ Pending |
| `load-grid` | 🌊 data | Loads the LLC90 grid geometry (cell areas, distances, partial-cell fractions, masks, rotation angles) and builds the `xgcm` grid object. | ⏳ Pending |
| `load-field` | 🌊 data | Downloads/caches any ECCO field (temperature, salinity, velocity, density/pressure, SSH, fluxes, stress) for chosen month(s)/day(s). | ⏳ Pending |
| `plot-ecco-field` | 🌍 visualization | Renders any field to a PNG — single tile, all 13 tiles, or a geographically-correct stitched global map. | ⏳ Pending |
| `compute-ocean-heat-content` | 🌡️ science | Global volume-weighted ocean heat content, and its change between two months. | ⏳ Pending |
| `compute-geostrophic-balance` | 🌡️ science | Geostrophic velocities from the pressure field, on the native grid. | ⏳ Pending |
| `compute-thermal-wind` | 🌡️ science | Vertical current shear from the horizontal density structure, plus velocity reconstruction from a level of no motion. | ⏳ Pending |
| `compute-curl` | 🌡️ science | Vertical curl of a vector field (wind-stress curl) and the implied Ekman pumping, compared to the model's vertical velocity. | ⏳ Pending |
| `compute-steric-height` | 🌡️ science | Steric height anomaly from density, with a thermosteric/halosteric decomposition; compared to sea-surface height. | ⏳ Pending |

*"Scientist Verified" = a domain oceanographer has personally signed off on the calculation. All science skills are already **AI-verified** — cleared the full verification ladder including an independent adversarial "try to disprove it" review (see [`docs/verify-status.md`](docs/verify-status.md)) — but none has had a human-expert review yet, hence all ⏳ Pending. Designed but not yet built: section transports, tracer budgets, flux decomposition, Ekman transport, normalized-difference — most gated on domain-expert input.*

---

## What you can ask

You don't need to know Python, the grid, or where the data lives. You ask; the assistant picks the right recipe, runs it in order, and narrates each step.

| You ask… | What you get back |
|----------|-------------------|
| **"How much has global ocean heat content changed between January 2000 and January 2010?"** | The change in ocean heat content (in Joules), with a sanity-check trail — plausible temperature range, ocean-volume benchmark — so you can see it's trustworthy. |
| **"Compute the geostrophic velocities for January 2008."** | Ocean current velocities implied by the pressure field, verified to match the official ECCO tutorial result *and* the model's own currents. |
| **"For January 2015, if I only knew the ocean's density, how well could I reconstruct the deep currents?"** | Currents reconstructed from the density structure via thermal wind (integrated from a level of no motion), shown *alongside* how much they differ from the model's real currents — so you see both the estimate and its limits. |
| **"Where does the density structure control the vertical shear of the currents in January 2010?"** | The thermal-wind shear (how the current changes with depth), and where it does — and doesn't — explain the real flow. |
| **"Where is the wind driving surface water down into the ocean (Ekman pumping) in January 2010?"** | The wind-stress curl and the Ekman pumping velocity it drives, checked against the model's own vertical velocity — showing where the wind pumps water down (subtropical gyres) vs up (subpolar, Southern Ocean). |
| **"How much of sea level is set by the ocean's density (steric height) in January 2000?"** | Steric height anomaly — the part of sea-surface height from the water column's temperature/salinity structure — split into thermosteric (temperature) and halosteric (salinity) contributions, and compared to the model's actual sea-surface height. |
| **"Show me a global map of sea-surface temperature for June 2000."** | A publication-quality world map (PNG) of the field for that month, correctly stitched across the whole globe. |
| **"Map the salinity at 1000 m for March 2005 (and plot any calculation's result too)."** | A PNG of any field at any depth — as a stitched global map, a single LLC tile, or all 13 tiles laid out. The same plotting also renders a calculation's *output* (e.g. the geostrophic-speed or Ekman-pumping maps above). |

Any month (or pair of months) in 1992–2017 works — swap the dates above for whatever period you care about. Each answer comes with its reasoning and a ✅ / ⚠️ verdict — never just a bare number. Ocean transports across a section and heat/salt budgets are [designed and coming](#build-status).

**Curious how a question turns into an answer?** See [`docs/USAGE.md`](docs/USAGE.md#what-actually-runs-when-you-ask-a-question) for the exact step-by-step each question triggers.

---

## Getting started

- **Just want to use it?** Point an AI assistant (e.g. Claude Code) at this repository and ask one of the questions above. The assistant handles the setup and runs the skills for you.
- **Want to run the skills yourself** (developer / analyst)? See **[`docs/USAGE.md`](docs/USAGE.md)** — it covers the one-time setup (a free NASA Earthdata login and an isolated Python environment) and the exact commands.

You'll need a free **[NASA Earthdata Login](https://urs.earthdata.nasa.gov/)** the first time data is downloaded — the setup guide walks through it.

---

## What makes these trustworthy

This project's whole reason for existing is *correctness you can verify* — not "the AI says so." Two commitments make that real:

1. **Teach, don't just compute.** Every skill narrates its reasoning as it runs — which data it's using and *why that one*, what each step does, and what the checks came back as. A number with no explanation is both a missed learning opportunity and a trust risk.

2. **Report evidence, not confidence.** Nothing is called "correct" because the AI believes it. Every science calculation is checked against independent evidence — the official ECCO tutorial code, published reference values, the model's own conservation laws, physical sanity bounds, and an adversarial "try to disprove it" review — before it's considered done. Results are reported as ✅ verified / ⚠️ unverified / 🔴 needs an expert.

The full protocol is in [`docs/verify.md`](docs/verify.md); the current per-calculation scorecard is [`docs/verify-status.md`](docs/verify-status.md).

---

## Build status

| Capability | Status |
|------------|--------|
| Environment setup & data access (download, caching, grid handling) | ✅ working, tested |
| Field maps / visualization | ✅ working |
| **Ocean heat content** (and its change over time) | ✅ **done** — fully validated |
| **Geostrophic velocities** | ✅ **done** — matches the official ECCO result and the model's own currents |
| **Thermal wind** (vertical current shear from density + velocity reconstruction) | ✅ **done** — matches ∂/∂z of geostrophy and the model's currents; adversarially reviewed |
| **Wind-stress curl + Ekman pumping** | ✅ **done** — rotation matches the official ECCO helper; Ekman pumping tracks the model's vertical velocity |
| **Steric height** (thermosteric/halosteric split) | ✅ **done** — reconstructs sea-surface height spatially; adversarially reviewed |
| Section transports, tracer budgets, flux decomposition, Ekman transport | 🔜 designed, not yet built (gated on domain-expert review) |

This is a tested foundation with **five validated science calculations** and a planned path for the rest (the remaining calculations need domain-expert sign-off on benchmarks and conventions before they're built).

---

## For developers & maintainers

- **[`docs/USAGE.md`](docs/USAGE.md)** — install, credentials, running skills, running tests, repository layout, and technical notes (Python version, the `xgcm` pin, data access).
- **[`docs/design.md`](docs/design.md)** — the detailed spec and **living source of truth**: skill architecture, calculation recipes, grid details, gotchas, and the validation framework.
- **[`docs/verify.md`](docs/verify.md)** / **[`docs/verify-status.md`](docs/verify-status.md)** — the science verification protocol and per-skill scorecard.
- **[`docs/roadmap.md`](docs/roadmap.md)** — the build sequence, phase by phase.
- **[`docs/questions-for-phil.md`](docs/questions-for-phil.md)** — open science-judgment calls awaiting a domain oceanographer.

This project originated in an ECCO User Working Group discussion and is under active early development. The design docs are kept deliberately candid and in-sync with reality — including a frank record of science errors caught by review, because that honesty is the point of the verification protocol.

---

## License

Licensed under the Apache License, Version 2.0 — see [`LICENSE`](LICENSE). Copyright 2026 California Institute of Technology.
