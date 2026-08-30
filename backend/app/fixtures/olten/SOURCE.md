# Olten — source and licence

Three scenario variants of a real Swiss network (Olten), taken verbatim from
[`flatland-association/flatland-scenarios`](https://github.com/flatland-association/flatland-scenarios),
**MIT licensed**, path `scenario_olten/data/<variant>/serialised_state/<variant>.pkl`.

| File | Upstream variant |
|---|---|
| `olten.pkl` | `olten` — the undisrupted timetable |
| `olten_disrupted.pkl` | `olten_disrupted` |
| `olten_partially_closed.pkl` | `olten_partially_closed` — the variant the WP4 orchestrator playground runner loads |

Copied 2026-08-28. Verified to load and run under the pinned `flatland-rl==4.2.6`
(the upstream files were generated with 4.0.6 / 4.1.0), which settles the open
question in `docs/plans/flatland-ecosystem-reuse-plan.md` §W8: Olten does **not**
require the 4.3.0 bump.

Not copied, because nothing renders it yet: each variant's `position_to_latlon.pkl`
(a lat/lon mapping per cell) and the recorded trajectories under `event_logs/`.
