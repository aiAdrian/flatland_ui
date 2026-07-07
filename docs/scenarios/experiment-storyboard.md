# Experiment storyboard

Working resource distilled from the FHNW study team's "Update Story Board" (WiP).
The study uses **three conditions** — **Recommendation-based**, **Co-Learning**
and **Director** — along the D4.1 reactive re-scheduling use-case steps. The
storyboard tables below detail the Co-Learning flow; the Recommendation flow is
the same steps with t1 decision support (WiP), and Director uses the autonomous /
goal-achievement supervisory flow. The original email screenshots / Miro board are
not embedded in the doc; only the tables below were recoverable.

## Key design decisions

- **Three conditions**: Recommendation-based · Co-Learning · Director.
- **Matched scenario difficulty across conditions** (confound control): each
  participant should not see the same scenario 3×, so we need **parallel,
  equally-hard scenarios** assigned to modes via Latin square. "Equally hard" =
  same *decision structure*, only the surface differs. See "Scenario difficulty"
  below.
- **Timing of decision support differs**: Recommendation at **t1** (at the
  incident); Co-Learning at **t3** (after the human's own idea) — and not
  "goal-based". Co-Learning still gets AI alternatives, just later. Director:
  no per-incident prompting — the human sets the directive up front and
  supervises goal achievement.
- **"Human goes first"** (Evaluative AI): the human formulates their own
  solution/hypothesis **before** the AI evaluates it.
- **Invented place/train names** so participants don't bring scenario expectations.
- **Reflection**: only **2 of 5** questions per incident (reduce burden).
- Open question: give the Recommendation group an Impact Analysis too, to avoid an
  apples-vs-pears comparison.

## Table 1 — per-scenario "Element" schema (must be defined up front)

| Element | Definition |
|---|---|
| Weak Signal | What is the early signal? |
| Proaktivitätsfenster | From when to when can one usefully act? |
| Relevante Cue-Kombination | Which information must be combined? |
| Plausible Lösungen | Which options are sensible? |
| Trade-off | What is the central goal conflict? |
| Impact Analysis | Which consequences does the AI show? |
| Outcome | What happens depending on the decision? |
| Gute Performance | Which indicators show good performance? |
| Schlechte Performance | What would late / local / consequence-blind behaviour be? |
| Reflection-Erwartung | Which reflection questions / which learning points should surface? |

→ This is the **scenario authoring schema** for the custom-scenario builder.

## Table 2 — Co-Learning storyboard (9 frames)

Columns: Frame · Use-Case-Schritt · übergeordnet · Ziel · detailliert ·
good-performance indicators · bad-performance indicators · **Log Daten** (empty,
to be defined) · **ICAP level** (ICAP engagement framework).

| # | Step | Goal | What happens |
|---|---|---|---|
| 1 | Schedule execution | establish baseline | stable operation, all trains on plan; no intervention |
| 2 | Monitoring | active overview | TN watches net, weather, sections, bottlenecks; spot early hints |
| 3 | Detection (weak signal by human) | trigger proactivity | an early signal emerges (rain, heavy freight on a grade, boarding delay); not yet critical |
| 4 | Human suggestion / hypothesis (Evaluative AI) | keep human expertise | TN enters their **own** re-scheduling idea first; AI only hints at the possibility |
| 5 | Impact Analysis | understand trade-offs | AI evaluates the **human's** solution: expected delays/stops/follow-on conflicts; offers alternatives — during operations |
| 6 | Human selects solution | decision sovereignty | keep / adjust / take an alternative |
| 7 | Execute (re-scheduling) | create effect | plan changes (route / order / speed / hold) |
| 8 | Feedback on outcome | feedback on decision | consequences become visible and are **recorded** |
| 9 | Reflection | learn cue→decision→consequence | reflection module, **2 of 5** questions |

## Mapping to our app — status & gaps

| Storyboard need | App today | Gap / action |
|---|---|---|
| 3 conditions (Recommendation, Co-Learning, Director) | all three built | study scope = three modes |
| Timing t1 vs t3 | Rec at incident; Co-Learning options ~t1 + reflection at end | move Co-Learning AI alternatives to **t3** (after human's idea) |
| Frame 3 weak signal | not modelled | needs scenario "Element" schema (Table 1) |
| Frame 4 human-first hypothesis | overrides exist, no explicit "formulate solution" step | add a **human-solution input** step |
| Frame 5 Impact Analysis (on human's solution) | what-if/scenarios partial | **§3.3 impact analysis** (backend) + impact panel; also for Rec group |
| Frame 8 recording | localStorage only | **per-frame logging** + central persistence/export ("Log Daten") |
| Frame 9 reflection 2-of-5 | shows all 5 | **configurable count** ✅ (implemented) |
| Performance indicators per frame | goal-achievement (run-level) | per-frame good/bad indicators |
| Invented names | idea noted | part of custom-scenario builder |
| ICAP level per frame | — | engagement tagging for logging |

## Scenario difficulty (must be matched across conditions)

Because the three conditions are compared per participant on *different* scenarios
(to avoid seeing the same situation 3×), the scenarios must be **of similar
difficulty** — otherwise difficulty confounds the mode effect.

Difficulty drivers in our setting:
- **Structural (hold constant)**: grid size, #trains, topology, #junctions on
  shared routes.
- **Situational (match these)**: cost of inaction (baseline delay/deadlocks if the
  human does nothing), length of the proactivity window, #trains affected by the
  disruption, reroute availability (a switch before the block), #plausible
  solutions / sharpness of the trade-off, ambiguity of the weak signal.

Matching & validation:
1. Author scenarios from one **template** (same decision structure; vary only
   names / corridor / which train).
2. **Calibrate by measurement**: run each candidate once with "do nothing" and
   once with a good policy → difficulty = cost-of-inaction + improvement
   headroom; keep only scenarios within a tolerance band. (App already provides
   building blocks: impact analysis = #affected; a baseline run = delay/deadlocks.)
3. **Counterbalance** (Latin square) so residual differences average out.

This belongs to the custom-scenario builder: author + measure difficulty, and the
"Element" schema (Table 1) already captures the structural part.

## Critical path for the experiment (updated)

1. **Custom-scenario builder** with the Table-1 element schema (weak signal,
   proactivity window, cues, plausible solutions, trade-off, impact, outcome,
   performance bands) + invented names.
2. **Guided frame flow (1–9)** with human-first solution input (frame 4) and
   Impact Analysis (frame 5).
3. **Per-frame logging** + central persistence/export.
4. **Reflection 2-of-5** configurable (done).
5. Recommendation-condition storyboard (still WiP in the study team's doc).
