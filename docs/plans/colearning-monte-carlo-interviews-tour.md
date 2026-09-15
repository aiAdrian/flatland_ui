# Plan — Co-learning Monte Carlo Interviews (tour)

> **Status:** in progress · started 2026-09-15 · owner: Daniel Boos
> **Context:** CAS thesis *Evaluating AI-Based Co-Learning Extensions for Railway
> Traffic Management Using Monte Carlo Simulation* (iimt, Uni Fribourg, due
> 2026-11-10). Experts give Min / Most-Likely / Max estimates for the costs and
> benefits of a Co-Learning extension at TRL 9. The tour lets them *experience* the
> modules first, so the estimates rest on something seen rather than on text.

## 1. Purpose

One tour, pinned end to end (modes, layout, network, disturbance), that walks an
interviewee through all Co-Learning modules in the order of the thesis'
interaction flow, makes clear which surfaces are the new extension and which stand
for today's TMS, and ends on an overview that frames the estimation questions.

Not a study condition. Nothing here may change the User Study 2 experiments: every
behaviour is gated on the running tour (`TourContextService`, `demoActive`).

## 2. Grounding — thesis Tables 1 and 2

| Step | Loop | Actor | Thesis function | Surface in the tour |
|---|---|---|---|---|
| 1 | operational | TMS | detects conflict | notification + map |
| 2 | operational | AI | Risk & Impact Assessment | `impact` panel (affected train, reaches in / clears in) |
| 3 | operational | AI | Alternatives Module | neutral options in `impact`; `whatif-compare` for the effect of an action |
| 4 | operational | dispatcher | decides | option click |
| 5 | operational | TMS | executes | override applied, run continues |
| 6 | learning | AI | Reflection Module | `co-learning-reflection` ("Warum?", recap, questions) |
| 7 | learning | AI / TMS | Shift Summary | **after the episode** — debrief screen (WP2) |
| 8 | learning | dispatcher | Event Simulation (sandbox) | **after the episode** — debrief screen (WP3) |
| 9 | learning | AI | System Co-Learning | learning records + operator model (WP4) |

Kolb: 1–5 concrete experience, 6 reflection, 7–8 active experimentation; abstract
conceptualisation is not supported by the system (shown dashed on the closing page).

## 3. Built so far (2026-09-15)

- **Tour entry** `co-learning-monte-carlo-interviews` (`core/demo/tours.ts`): one
  mode, no survey, ~15 min.
- **Opening and closing pages** (`core/demo/tour-briefings.ts`,
  `features/tour-briefing`): topic, goal of the interviews (Min/ML/Max, TRL 9),
  procedure, "not the final widgets" caveat; closing page with Kolb cycle, both
  loops and the module table incl. prototype status.
- **German mode intro** for this tour (`ModeIntro.labels`/`note`, override via the
  briefing).
- **Layout preset** `preset-colearning-interview`: situation / notifications /
  trains left; Streckenspiegel · ZWL tabs centre (`minBodyHeight`) with the Fahrplan
  open below them; Impact, What-if, Reflection right.
- **One train name everywhere:** `TrainIdentityService` (IC_703, ICE_42, RE_18) is the
  name; the learning-record card, the impact, what-if, rationale and reflection panels
  and the sandbox texts (`{T<handle>}` placeholders) use it, the tour disturbance
  names no train.
- **Network:** PF–CH Walensee long approach, map starts on Ziegelbrücke–Walenstadt
  (`mapFocusCols`).
- **Tour disturbance** `interview-e1-breakdown-single-track` (E1 stops 12 steps in
  the single-track section at step 28 → E2 listed by the impact analysis for steps
  28–39). Lives in the preset's `tour_disturbances`: selectable by id, never listed in
  the experiment picker (`backend/tests/test_tour_disturbances.py`).
- **Module badges** "Co-Learning" on the new panels (`panel-shell`).
- **Guide strip** (`features/tour-guide`, `core/demo/tour-guide.service.ts`): the nine
  steps, ticking themselves from store signals; the panel of the current step is
  outlined, its badge pulses, it opens and scrolls into view (vertically only).

Verified in the browser: 1–3 tick at the conflict, 4–5 after the decision, 6 and 9
after reason + "Nur diesmal". Frontend spec 2/2, backend 3/3, type check and colour
lint clean.

## 4. Decisions

- **Tour-scoped, not mode-scoped.** Co-Learning in the experiments stays as it is;
  badges, guide, map focus, debrief only exist while this tour runs.
- **What-if during the run is Risk & Impact Assessment** ("impact of action on
  affected trains", Table 1), not Event Simulation. Event Simulation is the sandbox
  after the episode.
- **Mock vs. real** for the first interview round:

| Step | First round | Why |
|---|---|---|
| 7 Shift Summary | **real** | builder and data exist (Director review) |
| 8 Event Simulation | **mock with real numbers** | the idea "replay it differently" carries; an interactive sandbox is 2–3 days |
| 8b never-experienced high-risk case | **mock with real numbers** | same method, one more card |
| 9 AI learns | **real** | learning records + operator model exist |
| 9b feedback into TMS algorithms | **mock** (explainer) | real retraining is out of reach and not needed |

## 5. Work packages

### WP1 — Debrief frame "Nach der Schicht" (≈ ½ day)
- When the live steps are done the guide offers **"Schicht beenden"** →
  `store.endShift()`; `episodeDone` opens it as well.
- `shiftScreenOpen` also opens for a tour whose briefing has a debrief; the slot
  renders `app-tour-debrief` instead of the Director review.
- Guide continues on the debrief: 7 → 8 → 9, ticked as each section is opened.
- "Zur Übersicht" → `finishDemoMode()` → closing page.
- **Done when:** the tour runs from conflict to closing page without the toolbar's
  "Finish tour" shortcut, and the experiments' Co-Learning condition never shows the
  debrief.

### WP2 — Step 7 Schichtbilanz, real (≈ 1–1½ days)
- Reuse `buildShiftReview` (KPIs, `selectReflectionMoments`, confirmed / one-offs).
- Co-Learning replaces Director's strategy choices with **interventions**: human
  decisions from `decisionLog` with step, train, action, stated reason, response.
- No Director plan verification, no AI workload line.
- **Done when:** a shift with one decision shows KPIs, the decision with its reason
  and the moment selection trace.

### WP3 — Step 8 Event-Simulation, mock with real numbers (≈ ½–1 day)
- Precompute outcomes offline with the **same branch helpers the what-if endpoint
  uses** (`api/overrides.py` `_branch_run` / `_kpis_from_result`) at the tour conflict
  (step 28): *Halten* vs. *Weiterfahren* (and the current course).
- Commit a generator script + its JSON fixture, so the numbers are reproducible and
  can be regenerated when the scenario changes.
- Cards: "Ihre Entscheidung" (from the decision log) next to the alternatives, delay
  / arrivals / deadlocks, clearly labelled "vorberechnet".
- 8b: a never-experienced case (e.g. W1 breaks down head-on in the single-track
  section), same method, one card.
- **Reuse target for the real sandbox later:**
  [`AI4REALNET/agent-as-a-service-trace-rl`](https://github.com/AI4REALNET/agent-as-a-service-trace-rl)
  (A3S restore / simulate-forward) — the in-repo fork (`RailEnvPersister` clone, as in
  `director/verify`) is the interim path. Decision stated here, not by omission.

### WP4 — Step 9 KI lernt, real (≈ ½ day) + 9b explainer (≈ 2 h)
- Learning records, value profile and "Präferenzen speichern" from the Director
  review's part 3.
- 9b: explainer card "So würde das Modell aktualisiert" — marked as concept.

### WP5 — Verification
- Unit spec for the Co-Learning branch of the review builder.
- Browser run: full tour to the closing page; experiments' Co-Learning condition
  unchanged.

**Order:** WP1 → WP2 → WP4 → WP3. Total ≈ 3–4 days. A real sandbox (8) adds ≈ 2–3 days.

## 5b. Progress and findings (2026-09-15, evening)

- **WP1 done:** "Schicht beenden" in the guide; `shiftScreenOpen` also opens for a
  tour with `debrief`; `app-tour-debrief` walks 7 → 8 → 9, each ticked on "Weiter",
  and hands over to the closing page.
- **WP2 done:** `interventionsFrom` in `core/shift-review.ts` (unit spec
  `shift-review-interventions.spec.ts`); the debrief lists interventions with reason
  and response, system holds, and the moment selection.
- **WP4 done:** learning records, value profile, "Präferenzen speichern"; each tour
  runs under its own operator id (`freshOperatorProfile`), restored when the tour ends
  — this closes the cross-interviewee risk below.
- **WP3 done:** `backend/scripts/generate_sandbox_outcomes.py` →
  `frontend/src/app/core/demo/sandbox-outcomes.generated.ts`. Delay is measured
  against the undisturbed run of the plan (the latest-arrival windows are too wide to
  show a few steps). Decision step, affected train, release step and reroute action
  all come from the impact analysis, not from hand-picked values.
- **Finding — holding costs more than proceeding.** A sweep over breakdown steps and
  trains showed "hold until clear" behind "proceed" in almost every case: Flatland lets
  the follower close up behind the blockage anyway, so an early hold only loses
  ground. In the tour incident: hold +30, proceed +26, hold without release → two
  trains never arrive. A useful, non-obvious lesson for step 8.
- **Novel case chosen from the sweep:** E2 breaks down in the single-track section
  (step 34, 20 steps) while W1 approaches head-on. Hold and proceed cost the same
  (+40); the reroute the impact analysis offers leads into a gridlock — no train
  arrives. That is the "never experienced high-risk case" (8b).

- **WP5 done (browser, 2026-09-15):** full tour from the opening page to the closing
  page — guide ticks 1–6 and 9 during the run, "Schicht beenden" opens the debrief, 7 →
  8 → 9 tick on "Weiter", "Ihre Wahl" marks the variant matching the logged decision,
  "Zur Übersicht" lands on the closing page. Frontend specs 5/5, type check and colour
  lint clean. The footer's survey button is hidden for a tour with a debrief.

## 6. Risks and open questions

- ~~**Operator profile carries across interviewees.**~~ Resolved in WP4: the tour runs
  under its own operator id. The backend persists profiles to
  `backend/data/operator-profiles.json` (`OperatorModelStore`, written on a confirmed
  learning, on "Präferenzen speichern" and on reset), so an interview that confirms a
  reason or saves leaves an `interview-<timestamp>` entry there — harmless, but worth
  clearing before a study export.
- **Offered reroute can gridlock.** The impact analysis offers a reroute that the
  simulator shows ends in a gridlock (8b). Fine as a teaching case; worth raising with
  whoever owns `recommenders/phase1_proximity.py`.
- **Thin summary.** One conflict per run gives a one-line shift summary; an optional
  fixture "Beispielschicht" (~10 incidents) would show aggregation and clustering.
- **Header overflow below ~1100 px** shifts the app sideways (pre-existing); run
  interviews on a wide window.
- **Mixed language / naming** in the existing panels ("Disruption Conflicts",
  "Train 1" vs. "E2" vs. "ICE_42"). The debrief shows "ICE_42 (E2)" to bridge the
  timetable name and the scene name; the learning-record card still says "Zug 1" and
  has English labels (DELAY, CONNECTION, RIPPLE).

## 7. Out of scope

Real sandbox (WP3 real), anonymised knowledge sharing and clustering of similar
situations (Reflection module), retraining the TMS algorithms, the header overflow.
