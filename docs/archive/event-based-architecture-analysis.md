# Event-based architecture (InteractiveAI) — analysis

> Decision aid: should the Flatland playground move to an event-based
> architecture like AI4REALNET's InteractiveAI? Relationship, motivation, and
> pros/cons of switching. Prepared for discussion with Adrian.

## What "event-based like InteractiveAI" actually means

InteractiveAI is **event-centric**: the central domain object is the **Event**
(incident), not the raw system state.

- **Event Service** — events with `id_event`, `criticality`, `start/end_date`,
  `data`, hierarchical via `parent_event_id`.
- **Context / Historic / Recommendation / Capitalization (feedback)** services
  around it.
- **Hypervision** — synthesises events into one interface; *"shifting focus from
  alarm monitoring to efficient task execution"*.
- Operator actions and accept/reject feedback are attached **to the event**
  (continuous learning / capitalization).

## Our current architecture (for comparison)

State-driven: the backend pushes **state snapshots** over WebSocket; the
notifications / scenarios / recommendations are **recomputed on demand from the
state** (`conflict_detector`, `NotificationManager`). A frontend `EventBusService`
exists for transient UI events, and the left "Event Feed" is already there — but
our "events" are **derived views without identity or lifecycle** (no stable
`id_event`, no active→acknowledged→resolved, no feedback linkage).

So we already have the **presentation** (feed, hypervision-style situation
summary) but not the **domain model**.

## Why one would switch (motivation)

1. **Consortium alignment** — InteractiveAI is the AI4REALNET reference HMI. An
   event-based model lets us share its **schema** (e.g. the Railway
   `MetadataSchema`) → comparable / interoperable / easier to feed back.
2. **Hypervision scales** — with rising complexity, event synthesis is more
   sustainable than scanning state (the project's own argument).
3. **Fits Co-Learning & the study** — an event is the natural unit of
   *incident → reflection → learning → capitalization*. The intervention log,
   reflection (§3.2) and surveys become clean when everything **hangs off the
   event** (including persistence / audit trail).

## Pros and cons of switching

| Aspect | Pro | Con |
|---|---|---|
| Alignment | Schema/concept compatible with InteractiveAI / AI4REALNET | The full platform is heavyweight (13+ containers, OperatorFabric, Keycloak) — adopting it as a *platform* is overkill |
| Domain model | Events as first-class: lifecycle, feedback, history → ideal for study & co-learning loop | Larger refactor: backend must **emit & manage** events with identity/lifecycle (today: detection only, no lifecycle) |
| UI | UI reacts to *meaningful events* instead of state diffs; feed / detail-in-context cleaner | Risk to working features ("don't break what works"); extra event-state handling in the frontend |
| Persistence | Event log = natural study dataset | Event-sourcing plumbing for a **single-user playground** is partly only a theoretical gain |
| Flatland fit | — | Time-stepped sim → mapping continuous state into **discrete events** (dedupe, resolution detection) is real design work |

## Recommendation: adopt the pattern, not the platform

No big-bang switch. The valuable, low-risk step is to **promote notifications to
first-class events**:

- stable `id_event`, `criticality`, **lifecycle** (active → acknowledged →
  resolved), `data` following the InteractiveAI **Railway schema**;
- attach operator actions + accept/reject + reflection **to the event id**
  (instead of loose localStorage entries);
- source them from our existing **`conflict_detector` / `EventBus`**, which also
  matches Adrian's additive `EventBus` / `SharedState` concept from the
  layout-designer prompt — i.e. **converging, not competing**.

This delivers consortium alignment + a study-grade event log + the co-learning
loop, **incrementally**, without replacing the working state engine. The full
event-sourcing / microservice architecture of InteractiveAI is only worth
targeting if **real interoperability with its Event Service** becomes a project
goal.

## Possible next steps

- (a) Keep this analysis as the decision basis (this document).
- (b) Plan the first incremental step: event schema + lifecycle, mapping
  `conflict_detector` → events.
- (c) Check whether real interop with InteractiveAI's Event Service is realistic
  (schema / endpoints).
