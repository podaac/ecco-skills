# ECCO Skills — Science Verification & Validation (V&V) Protocol

> **Why this document exists.** Early in this project the AI repeatedly reported high
> confidence in science that was wrong (missing density factor, `hFac` double-count,
> curl's second rotation, single-face section masks). External adversarial AI
> evaluations caught them. The lesson: **the AI's confidence is not evidence.**
> Internal coherence feels like correctness but isn't. This protocol makes correctness
> depend on *independent evidence the user or Phil can see*, not on the AI's say-so.
>
> The user is trusting the AI on science they don't themselves check. That trust is only
> safe if every science result carries verification that doesn't route through the AI's
> judgment. **Goal: verify as much as possible without Phil; involve Phil only for the
> "tough" judgment calls that have no ground-truth to check against.**

---

> **Current status of every skill lives in [`docs/verify-status.md`](verify-status.md)** —
> this doc is the *protocol* (the rules); that one is the *scorecard* (where each skill
> stands today). Update the scorecard whenever a skill's verification status changes.

## Core rule

**Nothing is "correct" because the AI believes it.** A science result is trustworthy
only when it carries independent evidence. Every science skill must record that evidence
in its `references/` before it is called "done." No evidence → not done, regardless of
how reasonable the code looks.

---

## The verification ladder (strongest / most independent first)

Apply as many rungs as apply to each skill. Higher rungs are more independent of the
AI's reasoning, so they count for more.

### Rung 1 — Match the official ECCO implementation *(highest value)*
ECCO ships real, expert-written helpers. Where one exists for the quantity, the skill
computes it **and** calls the official helper, and asserts agreement to a tolerance.
Divergence = the skill is wrong, no opinion required.

| Quantity | Official reference |
|----------|--------------------|
| Geostrophic velocity | `ecco_po_tutorials.geos_vel_compute` *(in the tutorial helper module, NOT `ecco_v4_py`)* |
| Section volume transport | `ecco_v4_py.calc_section_vol_trsp` |
| Section masks | `ecco_v4_py.get_section_line_masks` |
| Global map plotting | `ecco_v4_py.plot_proj_to_latlon_grid` |
| LLC grid object | `ecco_v4_py.get_llc_grid` |

*(Confirm each helper's existence and signature in the installed version before relying
on it — `geos_vel_compute` is NOT in `ecco_v4_py` 1.8.1; it's in the separately-obtained
`ecco_po_tutorials.py`. Verify at build time, don't assume.)*

### Rung 2 — Reproduce the tutorial's published result
The ECCO PO tutorials print concrete numbers/figures. A skill built from a tutorial must
reproduce them within a stated tolerance on the same input, **as an automated test** —
not a number the AI eyeballs and declares good. Record the exact input granules
(ShortName + date + concept-id), the expected value, and the tolerance.

### Rung 3 — Conservation / closure oracle
Because ECCO is a free-running MITgcm solution, heat/salt/volume/momentum budgets close
to ~1e-10 by construction. That's physics, not the AI. A budget that doesn't close is
provably wrong. (Residual must be defined with units/normalization — see the "needs Phil"
register for tolerances.)

### Rung 4 — Physical sanity bounds
Order-of-magnitude and sign checks against known ocean values (e.g. volume-mean potential
temperature ≈ 3.5 °C, ocean volume ≈ 1.34e18 m³, velocities O(0.01–1 m/s)). Cheap, catches
gross errors. Bounds themselves are first-guesses until Phil confirms (register below).

### Rung 5 — Internal cross-checks
Compute the same quantity two independent ways and compare (e.g. transport via flux
diagnostics vs residual-velocity reconstruction; geostrophic vs actual model velocity).
Agreement is evidence; disagreement localizes the bug.

### Rung 6 — Automated regression suite (with teeth)
Every behavior above is locked in by an automated test that is **proven to fail when the
fix is reverted**. A green suite that can't catch a reintroduced bug is theater. Current
suites: `ecco-common/tests/` (loader/cache/access, 13 tests) and each calc skill's
`scripts/test_validation.py` (negative + positive guards). Run all via
`.claude/skills/run_all_tests.py`.

### Rung 7 — Standing adversarial review *(process, not one-off)*
The external-AI evals have been the highest-yield check in this project. Keep them.
**Before any science skill is called "done," it gets an independent adversarial pass** —
another AI instance instructed to *disprove* it against the tutorials and installed
helpers. Findings are logged (see `docs/eval*.md`), fixed, and re-tested. This is a
required gate, not an optional extra.

---

## What the AI CANNOT verify alone → the "needs Phil" register

Some things have no ground-truth file to diff against; the authority is a human
oceanographer. The AI must **flag these, not paper over them with a confident default.**
Maximize Rungs 1–7 first; escalate to Phil only what genuinely needs judgment:

1. **Benchmark target values & tolerances** — e.g. Atlantic MOC ~17 Sv, Drake ~140 Sv,
   acceptable residual/rtol/atol per skill, and whether the Rung-4 sanity bounds are
   right. *(Currently AI-inserted placeholders.)*
2. **Flux-decomposition grouping** — 3-term vs 4-term; which physical grouping is meant.
3. **Budget term lists & signs** — exact advective/diffusive/forcing terms per budget,
   z-star handling, residual definition/units.
4. **"Does this answer the actual scientific question?"** — a skill can be a provably
   correct implementation of a calculation that doesn't address the user's real intent.
5. **Ekman-transport comparison target** — no ECCO tutorial exists for Ekman transport, so
   there's no reference number/helper; the comparison to the model (ageostrophic residual
   vs raw upper-ocean velocity) is a physical-intent call. `compute-ekman-transport` is
   deferred pending this.

Rule of thumb: **if verification requires knowing what's *physically intended* rather
than what's *numerically correct*, it's a Phil question.** Everything else, verify
independently.

---

## How results are communicated (calibrated, not confident)

The AI must report **evidence and its absence**, never bare "this is correct ✓":

- ✅ **Verified:** *"matches `calc_section_vol_trsp` to 0.02% and reproduces the MHT
  tutorial's 1.2 PW; regression test added."* — trustworthy, here's the evidence.
- ⚠️ **Unverified:** *"derived from the equations but NOT yet checked against a helper or
  tutorial — treat as unverified."* — so the user knows exactly what rests on AI
  reasoning alone.
- 🔴 **Needs Phil:** a judgment call from the register above; do not guess a default.

The failure mode this protocol fixes: the AI previously sounded equally confident about
verified facts and unchecked reasoning. Tone is not evidence.

---

## Definition of "done" for a science skill

A calculation skill is **done** only when, in its `references/`:
1. Every applicable ladder rung has been run and its result recorded (with the exact
   input granules and tolerances).
2. Rung 1 (official-helper match) is satisfied wherever a helper exists, or its absence
   is explicitly justified.
3. A teeth-verified regression test exists.
4. It has passed a Rung-7 adversarial review.
5. Any residual reliance on unverified AI reasoning is labeled ⚠️, and any judgment calls
   are in the "needs Phil" register — not silently defaulted.

Absent any of these, the skill is **in progress**, and must be described that way (no
"done"/"correct" claims).

---

## Honest limits

This protocol makes it *much harder* for a science error to survive, and makes residual
risk *visible*. It does **not** guarantee physical truth — "provably matches the official
ECCO method and tutorials" is the realistic bar, not "guaranteed right." Claiming
certainty would repeat the original overconfidence in new clothing.
