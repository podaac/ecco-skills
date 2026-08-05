# ECCO Skills

**Ask ocean-science questions of [ECCO](https://ecco-group.org/) — and get answers you can actually trust.**

ECCO is a global ocean "state estimate": a physics-faithful reconstruction of the ocean from 1992–2017 (temperature, salinity, currents, sea level, and more). Getting a *correct* number out of it is surprisingly easy to get wrong — the data lives on an unusual grid with rules that trip up even careful code.

**ECCO Skills** are guardrails that let an AI assistant do these calculations the right way. You ask a question in plain language; the assistant runs a vetted, step-by-step recipe and shows its work — including the evidence that the answer is right.

> **Status:** early but real. The foundations plus **two fully validated calculations** — ocean heat content and geostrophic balance — work today. More (ocean transports, budgets, and other diagnostics) are designed and on the way. See [Build status](#build-status).

---

## What you can ask

You don't need to know Python, the grid, or where the data lives. You ask; the assistant picks the right recipe, runs it in order, and narrates each step. Today's built calculations:

| You ask… | What you get back |
|----------|-------------------|
| **"How much has global ocean heat content changed between these two months?"** | The change in ocean heat content (in Joules), with a sanity-check trail — plausible temperature range, ocean-volume benchmark — so you can see it's trustworthy. |
| **"Compute the geostrophic velocities for this month."** | Ocean current velocities implied by the pressure field, verified to match the official ECCO tutorial result *and* the model's own currents. |
| **"If I only knew the ocean's density, how well could I reconstruct the deep currents?"** | Currents reconstructed from the density structure via thermal wind (integrated from a level of no motion), shown *alongside* how much they differ from the model's real currents — so you see both the estimate and its limits. |
| **"Where does the density structure control the vertical shear of the currents?"** | The thermal-wind shear (how the current changes with depth), and where it does — and doesn't — explain the real flow. |
| **"Show me a global map of sea-surface temperature."** | A publication-quality world map (PNG) of the field, correctly stitched across the whole globe. |

Each answer comes with its reasoning and a ✅ / ⚠️ verdict — never just a bare number. More questions (transports across a section, heat/salt budgets, Ekman pumping, steric height) are [designed and coming](#build-status).

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
| **Thermal wind** (vertical current shear from density + velocity reconstruction) | ⚠️ built & cross-checked against the model's own currents; final adversarial review pending |
| Section transports, tracer budgets, Ekman pumping, steric height | 🔜 designed, not yet built (some await domain-expert review) |

This is **not yet** a general-purpose ECCO system — it's a tested foundation with a few validated calculations and a planned path for the rest.

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
