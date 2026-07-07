# Reusable LLM Prompt — Evolving the Flatland Dispatcher Interface

> Purpose: paste this into different LLMs (Claude, GPT, Gemini, …) to get
> **inspiring but well-grounded** ideas for new, modular UI elements ("tiles")
> that improve how the Flatland Dispatcher visualises network state and supports
> human-AI dispatching. It is self-contained — the CONTEXT block gives the model
> everything it needs.
>
> How to use:
> - Run the **whole prompt** for a broad sweep, or delete all but one
>   "FOCUS — …" block to go deep on a single region (center / left / right).
> - If the model accepts attachments, also attach `README.md`, a screenshot of
>   the current UI, and `docs/interaction-modes-brief.md` for extra grounding.
> - Run the same prompt in 2–3 models and compare — ideas that recur are usually
>   the robust ones; ideas that appear once are the interesting bets.

---

## ░ PROMPT (copy from here) ░

You are a senior product designer + data-visualisation specialist for
**safety-critical control-room software** (rail traffic management, air traffic
control, electrical grid operations, network operations centres). You combine
deep knowledge of established operational-visualisation practice with restraint:
every idea must earn its place on a busy dispatcher's screen.

### CONTEXT — the system you are designing for

**Product.** "Flatland Dispatcher — A Human-AI Teaming Playground." A
human-in-the-loop HMI for **railway dispatching** experiments, built on the
open-source **Flatland** multi-agent reinforcement-learning environment, as part
of the EU Horizon project **AI4REALNET**. A human dispatcher and an AI
(RL policies) co-operate to route trains on a grid network, resolve conflicts,
and minimise delay/deadlocks.

**Tech & design constraints (respect these in every idea).**
- Frontend: **Angular** (standalone components + signals), **SBB Lyne** design
  system / web components. Real-time updates via WebSocket.
- Visualisation today is hand-built SVG/Canvas; no heavy 3D. Keep tiles
  **modular and drop-in** — each should be a self-contained component that slots
  into one of the three layout columns without redesigning the whole screen.
- Data is **abstract/schematic**, not geographic — Flatland is a grid of rail
  cells, switches and stations, not a real map.

**Current 3-column layout.**
- **CENTER — network state.** Two views, toggleable/splittable:
  (1) **Map** — top-down schematic of the rail grid: cells, tracks, switches,
  stations, train agents with colour-coded delay, selectable agents, next-
  decision highlights. (2) **Marey diagram** ("graphic timetable" / stringline /
  Bildfahrplan) — time on one axis, track position on the other, one line per
  train; shows where/when trains meet, cross, wait, or conflict.
- **LEFT — notifications.** A list of system notifications (info / warning /
  error), e.g. predicted conflicts, deadlock risk, malfunctions, override risk;
  hovering a notification highlights the related train(s). Also: layer-visibility
  toggles and a KPI-priority filter (time / energy / routing weights).
- **RIGHT — AI & decisions.** Policy/scenario panel (compare alternative RL
  policies as "what-if" branches with KPI deltas), recommendations panel (AI
  suggests a policy/action, optionally with confidence + countdown), agent list,
  and an agent inspector (per-train detail: position, ETA, delay, deadline,
  next-decision options, malfunction state).

**Data available per train (so ideas can be concrete).** position & direction,
target, state (ready/moving/stopped/malfunction/done), speed, earliest
departure, latest arrival, ETA, delay, time-to-deadline, next decision point
with its discrete action options, malfunction-remaining. Per network: grid +
rail topology, elapsed/max steps, predicted conflicts, per-scenario KPIs
(total delay, deadlocks, completions, mean delay). Plus compressed historical
trajectories per train.

**Three human-AI interaction modes the UI must serve** (an element may behave
differently per mode):
- *Recommendation* — AI suggests **with** a recommended option; human decides.
- *Co-Learning* — AI offers **neutral** options; human decides, reflects, and
  runs "what-if" comparisons (convention: human-chosen steps drawn **blue**,
  AI-simulated steps **yellow**).
- *Director* — AI runs autonomously on high-level directives; human supervises
  via **global** goal/KPI achievement and can intervene ("adjustable autonomy").

### TASK

Propose **new or improved modular tiles** for this interface — elements we could
build and slot in individually — that visualise network state and support
human-AI dispatching **better than what exists today**. Treat the three columns
as three design surfaces:

1. **CENTER:** How should the **Marey diagram evolve**, and what other
   network-state representations belong here? (e.g. richer stringline encodings,
   conflict/headway visualisation, predicted-vs-actual overlays, congestion or
   throughput views, schematic topology alternatives, ways to fuse map + time).
2. **LEFT:** What should **notifications** become? (e.g. triage/prioritisation,
   predictive alerts with lead time, grouping & noise control, explain-the-alert,
   linking an alert to the exact place/time on the center views, acknowledgement
   & escalation, trust calibration).
3. **RIGHT:** How to present **policy, scenarios and recommendations** better?
   (e.g. comparing AI alternatives, showing AI uncertainty/confidence honestly,
   making trade-offs legible, what-if compare, mode-specific framing).

### WHAT "GOOD" LOOKS LIKE (so you don't give me generic dashboard advice)

- **Grounded:** name the established pattern or domain each idea borrows from
  (e.g. time-distance/stringline charts, marginal-strip sparklines, headway
  ribbons, Sankey for flow, control-room "alarm shelving", EWD/PERT, focus+
  context / fisheye, small multiples, brushing-and-linking). One concrete
  reference per idea — a real system, paper, or well-known technique.
- **Concrete to THIS data:** say which data fields it consumes and what a
  dispatcher reads off it in one glance.
- **Earns the pixels:** state the decision it improves and what it replaces or
  de-clutters. Prefer fewer, sharper elements over more chrome.
- **Mode-aware where relevant:** note if/how it differs across Recommendation /
  Co-Learning / Director.
- **Honest about AI:** if it shows AI output, show uncertainty and make override
  trivial; avoid automation-complacency traps.

### OUTPUT FORMAT

For **each region** give **3–5 tile ideas**, ranked by impact-to-effort. Use:

> **[Region] Tile name** — one-line promise.
> - *Inspired by:* <pattern / real system / reference>
> - *What it shows / data used:* …
> - *Decision it improves:* …
> - *Replaces / declutters:* …
> - *Interaction:* … (hover, brush, drill-in, link to other views)
> - *Mode differences:* … (if any)
> - *Effort:* S / M / L, and the riskiest unknown.
> - *Sketch in words:* a 2–3 sentence description precise enough to mock up.

End with a short **"3 bets I'd build first"** section and **"1 contrarian idea"**
that challenges the current map-+-Marey framing.

Be specific and opinionated. No generic "add a dashboard" advice. If a current
element is already good, say so and leave it alone.

## ░ END OF PROMPT ░

---

## Optional add-ons you can paste under the prompt

**To push for more rigour:** "For your top 3 ideas, add a failure-mode note: how
could this visualisation mislead a tired dispatcher at 3am, and how do you guard
against it?"

**To get build-ready output (for Claude Code / engineers):** "For the single
highest-impact CENTER idea, specify it as an Angular standalone component:
inputs (signals), the SVG/Canvas structure, the data transform from the train/
KPI fields listed, and the interaction events it emits."

**To compare models fairly:** run the prompt unchanged in each model, then ask a
final model: "Here are design proposals from three LLMs (pasted below).
De-duplicate, cluster by theme, and rank by impact-to-effort for a real-time
rail dispatching HMI."

---

## ░ MINI-ROUND FOLLOW-UP PROMPT (build-ready) ░

> Use after the first round, once you've picked a tile to build. Paste this into
> 1–2 strong models (GPT-5.5-pro, Claude Opus 4.8, or Gemini Pro). Replace
> `<TILE>` with the chosen idea (e.g. "Conflict-aware Marey" or "Triage'd
> notification column"). The point is a spec Claude Code can implement directly —
> the model is secondary, the spec is the product.

You previously proposed UI tiles for the **Flatland Dispatcher**, a human-in-the-
loop railway-dispatching HMI (Angular standalone components + signals, SBB Lyne,
real-time WebSocket; abstract Flatland grid; three modes Recommendation /
Co-Learning / Director; what-if convention human=blue, AI-simulated=yellow).

Take **one** tile — **`<TILE>`** — and turn it into a **build-ready spec** for an
Angular standalone component. Be concrete and implementation-level:

1. **Component contract:** name, inputs (as signals), outputs/events it emits, and
   which shared store signals it reads (e.g. selected train, brushed time window,
   interaction mode).
2. **Data transform:** exactly which fields it consumes — per train
   (`position, direction, speed, delay, eta, time_to_deadline, earliest_departure,
   latest_arrival, next_decision.options, malfunction_remaining, state`), per
   network (rail topology, predicted conflicts, per-scenario KPIs:
   `total_delay, deadlocks, completions, mean_delay`), compressed trajectories —
   and the transform from those into what's drawn.
3. **Render structure:** SVG vs Canvas, the element hierarchy, and how it updates
   on each WebSocket tick without re-rendering everything (respect throttling).
4. **Interaction & states:** hover / select / brush / drill-in; empty, loading,
   and error states; keyboard access.
5. **Mode behaviour:** how it differs across Recommendation / Co-Learning /
   Director (and where it shows a *recommended* option vs *neutral* options vs
   *none*).
6. **Failure modes:** how this visualisation could mislead a tired dispatcher at
   3am, and the specific guardrail against each.
7. **Smallest first version:** the minimum slice worth shipping, and what to defer.

Output as a spec, not prose. Assume an engineer (or a coding agent) implements
directly from it. Flag any data we'd need that probably isn't available yet.

## ░ END MINI-ROUND ░

---

## ░ REFERENCES & USE-CASE FOLLOW-UP PROMPT ░

> Paste under a model's first-round answer (works well for Opus, GPT-5.5-pro,
> Gemini). Sonar gives citations natively; this makes the *non-web* models put
> their grounding and concrete scenarios on the record too. Ask for it explicitly —
> otherwise they stay abstract.

For your **top 3 tile ideas**, add two things to each:

1. **Grounding references (be specific and verifiable):** name the standard,
   paper, product, or control room the pattern comes from — e.g. "EEMUA 191",
   "ISA-18.2", "UIC Code 406 blocking-time", "Tufte, *Envisioning Information*",
   "SBB RCS-Dispo", "ETCS Level 2". Prefer named, checkable sources over vague
   "control-room practice". If you are not sure a source exists, say so rather
   than inventing a citation — a fabricated reference is worse than none.
2. **A concrete use-case walkthrough (a 4–6 step scenario):** a specific
   dispatching moment on a Flatland grid where this tile changes the outcome.
   Format: *Situation → what the dispatcher sees on the tile → the decision they
   make → what they'd have done without it → the measurable difference
   (delay/deadlocks/arrivals)*. Use concrete train IDs, cells, and step numbers.

Keep each tile to ~8 lines. Do not re-explain the tile from scratch — only add
the references and the walkthrough. Flag any reference you are not confident is
real.

## ░ END REFERENCES & USE-CASE ░
