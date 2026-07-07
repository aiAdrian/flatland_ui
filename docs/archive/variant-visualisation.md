# Visualising variants / alternatives — options & recommendation

Synthesis of how to show **decision variants** (what-if alternatives) beyond the
single time-distance (Marey) diagram. Grounded in the Zettelkasten, AI4REALNET,
and literature.

## Guiding principles
- **Evaluative AI** (Miller 2023): present **evidence for/against options + the
  trade-offs between any set of options** — don't push a single "best". Variants
  should *compare*, not prescribe.
- **Supertool, not chat** (Shneiderman; interaction-paradigms note): overview →
  zoom/filter → details-on-demand. Show variants as an overview first, details on
  click. Direct manipulation over conversation for a dispatcher.
- **Show uncertainty** (uncertainty-visualisation note): outcome ranges, not false
  point precision (e.g. a delay band per option).
- **Consistent visual grammar** (visual-vocabulary note): always render variants
  the same way so they're quick to read.

## Options

| Representation | Strength | Weakness | Fit |
|---|---|---|---|
| **Small multiples** (mini-map/mini-Marey per variant) | scannable, scales to ~3 | little detail each | top for "up to 3 options" |
| **Overlaid paths** (one map/Marey, old=blue / new=yellow, §3.3) | direct, spatial | clutters at >2 | chosen variant vs actual |
| **Branching tree** (TraceRL-style: state → branches w/ KPI outcome) | shows "what leads where", drill-down | complex, space-hungry | later / exploration |
| **KPI comparison table / parallel coordinates** | trade-offs across many KPIs at a glance | not spatial | complement (Evaluative AI) |
| **Diff / delta view** (only what changes: which trains reroute) | minimal cognitive load | not the whole picture | strong for interventions |
| **Outcome band / fan** (delay distribution per option) | honest uncertainty | needs distribution data | medium |
| **Map overlay** (alternative routes on the network) | intuitive "where it goes" | no time axis | good beside the Marey |

## AI4REALNET references
- **agent-as-a-service / TraceRL (A3S)**: branching decision trees with a live
  agent; **blue/yellow** convention (T3.1 EnliteAI): human=blue, AI-simulated=yellow.
- **T2.3 explainability dashboard**: statistical agent-vs-expert comparison
  (Wilcoxon) — KPI comparison as its own surface, not only spatial.

## Literature
- Branching-trajectory viz — show expert / sub-optimal / branch simultaneously
  (arXiv:2411.11327).
- Small multiples with collapse/expand of branches (arXiv:2605.10257).
- What-if over a prediction horizon in train dispatching (Springer 2007,
  10.1007/978-3-540-72432-2_20).
- Critical take on decision-viz tools (arXiv:2307.08326, "From Information to Choice").

## Recommendation for this app
Combine layers (don't cram variants into the Marey):
1. **Overview**: small multiples (mini-map or mini-Marey per variant) **+ a KPI
   comparison strip** — fits "up to 3 recommendations, no explanation".
2. **Detail-on-demand**: click a variant → **old/new overlay (blue/yellow)** on map
   *and* Marey + a **diff** (which trains reroute/hold).
3. **Framing**: Evaluative-AI style (evidence / trade-offs), especially in
   Co-Learning — don't highlight a single "best".
4. Show **uncertainty** instead of a single number where possible.

This also reframes the Marey: it stays *one* detail view; variant comparison lives
better in small multiples + KPI table + map overlay. Relates to the recommender
roadmap (dual-path §3.3) and the Marey-rethink note.
