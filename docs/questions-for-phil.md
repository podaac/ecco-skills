# Questions for Phil — ECCO Skills science-judgment calls

Hi Phil — a short list of decisions we can't make without you. These are the items that
require knowing what's *physically intended*, not just what's *numerically correct*.
Everything we could verify independently (against the official ECCO tutorial helpers and
the model's own diagnostics) we already have — so this list is deliberately short, and is
what's left after squeezing out everything that didn't actually need your judgment.

**Context on how we're building:** each calculation is verified against ground truth
before we call it done — e.g. our geostrophic-velocity skill reproduces the tutorial's own
`geos_vel_compute` to <1e-9 m/s *and* independently matches the model's actual velocities
at 200 m (corr 0.998). Ocean heat content reproduces the tutorial's published ocean
surface area exactly. Where a tutorial helper or a physical cross-check exists, we don't
need to ask you. The questions below are the ones with **no ground-truth to check against**
— only your expertise.

Each question notes **what it unblocks** so you can prioritize.

---

## 1. Validation benchmark values & tolerances
*Unblocks: transport, MOC, and any skill we validate against observations.*

To claim a result is trustworthy we compare it to accepted real-world values. We've put
**placeholder** numbers in as reminders — they are AI guesses, **not** to be trusted:

- Atlantic MOC at 26°N ≈ 17 Sv (RAPID)?
- Drake Passage transport ≈ 140 Sv?
- Global OHC uptake ≈ 10²² J/yr order of magnitude?

**What we need from you:**
- For each calculation we'll build (MOC/overturning, section transports, OHC trend,
  Ekman transport), what published value should we check against, and **what deviation is
  acceptable** (e.g. ±2 Sv? ±10%)?
- Preferred reference/citation for each number.
- Sanity-check our physical bounds: e.g. we currently flag global volume-mean potential
  temperature outside **2–6 °C** as suspicious (it comes out 3.59 °C). Reasonable, or too
  tight/loose? Same question will arise for velocity and transport magnitudes.

---

## 2. Flux decomposition — which grouping do you want?
*Unblocks: the flux-decomposition skill (velocity × tracer into mean/eddy parts).*

Your original note wrote the decomposition with **three** terms:

> `v·T = v̄·T′ + v′·T̄ + v′·T′`  *(dropping the mean–mean `v̄·T̄`)*

The full algebraic identity has **four** terms: `v·T = v̄·T̄ + v̄·T′ + v′·T̄ + v′·T′`
(overbar = time mean, prime = deviation). Which do you actually want?

- **(a)** the flux *anomaly* `v·T − v̄·T̄` (i.e. the three terms you wrote), or
- **(b)** the time-mean eddy decomposition `mean(v·T) = v̄·T̄ + mean(v′·T′)` (mean-advective
  + eddy correlation; the two cross terms vanish under time-averaging), or
- **(c)** the full 4-term instantaneous split?

The term list, the code, and the physical interpretation all depend on this. If it's (b),
also: what averaging window defines the "mean" (full record? annual? a climatology)?

---

## 3. Budget term lists, signs, and residual definition
*Unblocks: the volume / heat / salt budget skills (the "does it close?" calculations).*

ECCO closes budgets to ~machine precision *if assembled with exactly the right terms*.
We can follow the ECCO v4 budget tutorials, but we want your confirmation on the parts
that are easy to get subtly wrong:

- **Which terms** to sum for each budget (heat, salt/freshwater, volume) — the exact
  advective (`ADVx/y/r_*`), diffusive (`DFxE/yE/rE/rI_*`), and surface-forcing terms,
  **and their signs/convention**.
- **z\* / free-surface handling** — how to treat the time-varying vertical coordinate in
  the volume and tracer budgets.
- **Residual definition** — we want to report "the budget closes" meaningfully. What
  should the residual be *normalized by*, and in what units, so a number like "1e-10" is
  actually interpretable? What residual counts as "closed" vs "a problem"?
- Salt vs salinity vs freshwater: which budget(s) do you actually want, and any
  convention gotchas (e.g. virtual salt flux vs real freshwater flux)?

---

## 4. Scientific-fit check (ongoing, not one-time)
*Applies to every skill.*

A skill can be a *provably correct implementation* of a calculation that still doesn't
answer the question a researcher actually has. As we build each one, we'd like a quick
gut-check from you that the calculation — as scoped — is genuinely useful for the science
you had in mind, and that we haven't computed something technically right but beside the
point.

Specific near-term ones where your steer would help:
- For "does geostrophy hold?", is comparing geostrophic velocity to the model's actual
  velocity via a normalized difference (binned by latitude/depth) the comparison you want,
  or is there a more useful diagnostic?
- Which sections/regions matter most for transports (the Atlantic focus you mentioned —
  specific latitudes? specific straits)?

---

## What is NOT blocked (so you know the state of play)

Already built and independently verified — **no input needed**:
- **Ocean heat content** (volume-weighted; reproduces tutorial ocean-volume/area, warming
  trend right sign & magnitude).
- **Geostrophic velocity** (matches the official tutorial helper *and* the model's actual
  velocities).
- The data/environment plumbing (download, caching, grid handling) — all machine-tested.

We can keep building anything that has a tutorial helper or physical cross-check to verify
against while these questions are open. The four above are the gates for budgets,
transports, the decomposition, and observational benchmarking.
