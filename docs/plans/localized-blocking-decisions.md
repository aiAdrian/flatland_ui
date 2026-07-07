# Localized blocking decisions — hold the affected, not the world

> **Status:** Concept + prototype. In Co-Learning the guided-demo holds the
> affected trains (STOP) on a new conflict instead of globally pausing; the
> rest of the network keeps running, and the human releases them by deciding
> (option buttons). Recommendation mode keeps the old gentle global pause. The
> reflection panel now also opens automatically once a decision is resolved
> and nothing else is pending (§6.3) — in addition to the manual trigger.
> Still open: event-type-dependent scope (area/sector), the autonomy agreement
> panel (§5.3), post-decision outcome feedback (§6.2), the explicit two-step
> confirm, and the end-of-scenario sandbox (both §8).
> **Origin:** Came out of the question "when do I have to find a solution and get
> feedback?" The realisation: today the decision moment auto-resolves, so a
> passive human gets a fully AI-driven run — a *disguised director mode*. The fix
> is a real decision the human must make. But blocking must be **local**, not a
> global freeze.

---

## 1. The problem

The current auto-pause has a **decision countdown that applies the recommended
option itself** if the human doesn't act (`impact-panel._autoDecide`). So:

- A passive human still gets a complete, AI-decided run → the human is optional.
- We can never demonstrate that **human + AI beats either alone**, because the
  human can be left out and nothing breaks.

This matches the theory (Stadelmann/Wäfler; calibrated trust): passive oversight
is psychologically impossible — the human needs **genuine agency**, or they just
rubber-stamp.

## 2. Why a global pause is wrong

Freezing the whole simulation while the human thinks is unrealistic: in real
operations the network keeps moving; a dispatcher resolves *one* situation while
everything else runs. So blocking must be **localized**.

## 3. The idea: localized blocking

At a blocking decision event:

- **No global stop.** The simulation keeps running.
- The **affected trains (or area) are held locally** — safe default = Hold
  (STOP) — until the human decides.
- The human **releases** them by accepting a recommendation or making a proposal
  (option / KPI / policy / track block). Their action replaces the hold.
- The AI does **not** decide for them — the affected trains simply wait.

### The elegant side effect: real pressure, no fake countdown

Because the world keeps moving, the held trains **accrue delay** and the context
can change (another train approaches the bottleneck…). That is *realistic* time
pressure — the cost of inaction becomes **visible** instead of being silently
optimised away by the AI. Crucially, normal operations usually **do afford time
to think** — it isn't that fast — so "the world moves but you have room to
deliberate" is the right model, not a stopwatch.

## 4. Reuses what already exists

- Per-train hold = existing `setOverride(STOP)`.
- Detection = the impact/conflict panel (affected trains already listed).
- Feedback before deciding = the what-if-override endpoint (already built).
- We **remove** the global auto-pause + auto-apply countdown and replace it with
  "hold the affected, let the rest run, wait for the human".

## 5. Design decisions (agreed)

1. **Scope is event-type-dependent.** Local train conflicts → hold the affected
   trains. Weather / regional problems → block an **area / sector**. The blocking
   scope is a property of the event type (ties into scripted events and
   heterogeneous tracks).
2. **Safe default while waiting = Hold (STOP)** the affected trains — prevents
   them from entering the conflict; the accruing delay is the natural pressure.
3. **No auto-decide** (pure agency) — the trains wait until the human acts.
   - **Longer-term idea — a negotiated human–AI autonomy agreement:** which
     incident types the AI may resolve on its own vs. which require the human.
     Configurable **dynamically in a panel, like the KPI sliders**. This is
     adjustable autonomy / Levels of Automation made explicit and operator-set.
4. **Global play continues** while affected trains are held; allow a **manual
   full-stop on demand** when the human wants to freeze everything.

## 6. When does feedback come?

Three stages at a blocking decision:

1. **Before** the decision — what-if feedback (**built**): hovering an option
   forward-simulates it and shows the consequence ("Hold → +3 steps; Reroute →
   deadlock risk") before committing (`what-if-override` endpoint).
2. **After** the decision — outcome: did it play out as predicted? (**not
   built** — see §9.1 below, the explicit confirm step is a related gap.)
3. **Reflection** (**built, first pass**) — once a decision is implemented and
   nothing else is pending, the reflection panel opens automatically
   (*in addition to* the manual "Reflect now" trigger, which stays available
   any time). Scoped to Co-Learning; only triggers via the impact-panel's
   `applyOption()` today — direct map/agent-inspector overrides don't (yet)
   trigger it.

## 7. This redefines "A-mini"

A was "guarantee a conflict." With localized blocking it becomes "**guarantee a
blocking decision the human must resolve**, scoped to the affected trains/area" —
a scripted event flagged `blocking: true` that (a) reliably occurs and (b) holds
the affected resources until the human decides.

## 8. Two noted extensions (direction, not yet built)

From refining the Co-Learning decision loop further:

**a) Explicit two-step confirm.** Today, hover = preview (what-if feedback) and
click = commit, in one motion. The refined design wants these split into two
distinct steps: see the AI's impact analysis for your chosen option, *then* an
explicit "Confirm" action applies it. This makes the "propose → get feedback →
commit" loop visible as three separate moments instead of two, and creates a
natural place to change your mind after seeing the consequence, before it's
locked in.

**b) End-of-scenario sandbox.** At the end of a Co-Learning run, a sandbox
screen lets the human replay the run's key decisions and see the impact of
each across the whole simulation — not just the single forward-sim at the
moment of choice (§6.1), but a full look-back over the decisions that mattered
most. This is the "what if I had chosen differently" idea from
`interaction-modes-brief.md` §3.3 (human-chosen = blue, AI-simulated = yellow
on the Marey), but scoped to a **post-hoc, run-wide review** rather than a
single what-if at decision time. Buildable from what already exists — the
`coLearningFeedback` intervention log (step + handle + choice), the
what-if-override endpoint, and stored trajectories — but is a standalone new
UI (a list of key decisions → pick one → compare), not a small addition.

## 9. Connections

- [scripted-events-plan.md](scripted-events-plan.md) — events carry the blocking
  scope (train vs. area) and the `blocking` flag.
- [recommendation-reliability.md](recommendation-reliability.md) — this is the
  substantive version of "guarantee a decision moment".
- [heterogeneous-tracks.md](heterogeneous-tracks.md) — area blocking + track
  costs make the reroute decision a real trade-off.
- Adjustable autonomy / LoA — the autonomy agreement (§5.3) is the operator-set
  control variable.

## 10. Open questions

1. How is the autonomy agreement (§5.3) represented and edited — a per-incident-
   type slider/toggle panel next to the KPI filter?
2. Area/sector blocking: how is a "sector" defined on the grid (curated regions,
   or a radius around an event)?
3. What does the held-train UI look like (waiting indicator, accruing-delay
   badge, "release by deciding")?
4. Does holding ever become unsafe (e.g., a held train blocks others)? Then the
   hold itself is a decision with consequences — surface that too.
