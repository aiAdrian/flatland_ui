# Interaction modes — one union carrying two axes

> **Discussion paper, not a decision.** It argues that `InteractionMode` conflates
> two independent things, and sketches one way out. The proposal in §5 is a
> starting point for the conversation, not a plan of record — §7 lists the
> alternatives that were set aside and the questions I could not answer. If you
> have a better cut, this document is the thing to argue with.
>
> **Grounded in a read of `frontend/src/` on 2026-08-23** (31 files touch
> `InteractionMode`; the widget catalog holds 36 entries, 14 of which declare no
> mode-specific behaviour at all) and in the automation-taxonomy literature cited
> in §2. Companion of
> [interaction-framework.md](interaction-framework.md) (§3 already models
> `allocation` as its own concept) and
> [interaction-modes-brief.md](interaction-modes-brief.md) (the authoritative
> mode spec).

## 1. The observation

`InteractionMode` is a three-valued union — `recommendation` (WP 3.1),
`co-learning` (WP 3.3), `director` (WP 3.4) — and is treated as a **level of
automation**. Checked against the automation taxonomy it does not hold up.

In the Timpe & Kolrep (2002) scheme, who owns each function:

| Mode | Monitoring | Generating | Selecting | Implementing |
|---|---|---|---|---|
| Recommendation | H/C | H/C | **H** | C |
| Co-Learning | H/C | H/C | **H** | C |
| Director | H/C | C | C | C |

**Recommendation and Co-Learning sit on the same level** (≈ level 5, Decision
Support). Their one difference — the AI ranks the options, or presents them
unranked (`optionPresentation: 'recommend' | 'neutral'`) — is in Parasuraman,
Sheridan & Wickens (2000) a question of *type* (which information-processing
stage is automated), not of *level*.

And what actually makes Co-Learning Co-Learning — neutral options, the
reflection module, what-if compare, learning where the other party is reliable —
is **not a property of that axis at all**.

## 2. The two axes

**Axis A — autonomy level / function allocation.** Who performs Monitoring,
Generating, Selecting, Implementing. Sheridan & Verplank (1978); Timpe & Kolrep
(2002); Parasuraman, Sheridan & Wickens (2000). Adjustable autonomy is *movement*
along this axis.

**Axis B — collaboration goal.** What the interaction is designed to achieve:
**perform** (get this decision right now) or **co-learn** (build calibrated
trust). Wäfler's finer split — learning *from* / *with* / *about* each other —
lives here; Stadelmann, Merkt & Barr (2026) define co-learning narrowly as the
*about* case (same task, same performance measure, goal = knowing when the other
is reliable).

The structural move is Shneiderman's (2022): what looks like one slider —
automation versus human control — is two dimensions, which is why an
upper-right quadrant exists at all. Same move, one level down.

## 3. What the separation makes visible

|  | goal: **perform** | goal: **co-learn** |
|---|---|---|
| **advisory** | `recommendation` | `co-learning` |
| **supervised** | `director` | ⬜ *not expressible* |
| **autonomous** | `director` | ⬜ *not expressible* |

The empty cells are the point. *"I supervise an autonomous run **and** we learn
about each other"* cannot be said today — although a supervisor override during
an autonomous run is a **stronger** learning signal than a click in a
recommendation list: rare, expensive, highly informative. Sparse-but-high-value
signals in Director are exactly what the co-learning work wants.

## 4. Why the conflation happened

Not sloppiness — **double duty**. The same three names serve two purposes with
opposite requirements:

| | needs | consumes |
|---|---|---|
| **Experiment** | few, fixed, comparable conditions | named points |
| **Prototype** | free movement between ways of working | a space |

A space needs more than one dimension. The single-axis model serves the
experiment and cannot serve the prototype. Much of the conceptual friction
probably comes from this double use rather than from the taxonomy itself.

Worth stating plainly: the product vision (high automation *with* appropriate
controllability — Shneiderman's upper-right) has **one** target, where the
autonomy level does not vary. The three modes are measurement conditions, not
three product operating modes. Reading them as the latter invites exactly this
confusion.

## 5. One proposal (arguable)

Keep `InteractionMode` as a **named preset over the two axes** rather than as the
primitive:

```ts
export const MODE_PRESETS: Record<InteractionMode, {
  autonomyLevel: 'advisory' | 'supervised' | 'autonomous';
  collaborationGoal: 'perform' | 'co-learn';
}>
```

- The union survives, so the CLAUDE.md guardrail holds — **no parallel flag**.
- Every existing `interactionMode()` call keeps working.
- New gating asks the axis it actually means.
- The experiment consumes presets; a prototype consumes axes.
- The empty cells become reachable without touching the experiment.

`interaction-framework.md` §3 already reserved this seam: `allocation` is
modelled as its own concept, *"not baked into `InteractionMode`, so that dynamic
reallocation becomes a runtime change of the same structure rather than a
refactor."*

**Already in the tree:** `core/widgets/widget-mode-axes.ts` — the Widget
Gallery's single entry point into mode semantics, with `MODE_PRESETS` as
documentation. It changes nothing semantically today; it is the place the split
would land.

## 6. Does this collide with widget `kind`?

No. Three different objects of classification:

| classifies | axis |
|---|---|
| an **interface element** (what does the widget show/do?) | `kind` — function class in the loop |
| a **function allocation** (who owns which stage?) | A |
| an **interaction purpose** (what is this session for?) | B |

A widget has no autonomy level; an allocation has no granularity.

**But the framework does leak.** `interaction-framework.md` §2 gives Decision
Support "mode-framings": Assessment (neutral) → Co-Learning, Recommendation
(ranked) → Recommendation, suppressed → Director. Those framings are **axis B**,
attached to a mode that claims to be axis A. Binding the framing to
`collaborationGoal` instead would remove the leak — `kind` then keeps saying what
the widget does, and the framing comes from the collaboration axis.

## 7. Alternatives set aside, and open questions

Set aside — pick them up if you disagree:

- **Leave it alone.** Defensible: three conditions is what the experiment needs,
  and every model is wrong somewhere. Cost: the prototype's "switch dynamically"
  requirement stays unbuildable, and the empty cells stay invisible.
- **Make Co-Learning a cross-cutting layer instead of an axis.** Co-learning is
  a *mechanism* available at every level; what differs per level is the
  granularity of the learning signal (dense per-decision in Recommendation,
  reflective in Co-Learning, sparse-but-strong in Director). This is close to the
  proposal and may be the better framing — it treats B as a capability rather
  than a coordinate. It does not by itself give the prototype an axis to move on.
- **Three or more axes.** Reversibility / depth of intervention is a serious
  candidate (how fast and how consequence-free can the human take back control).
  It hides inside "supervised" today.

Genuinely open:

- Is *perform vs co-learn* an opposition or a weighting? Probably the latter —
  then B is not a switch but a dial, and the grid above is a simplification.
- How many steps does axis A need in practice? Timpe has ten; the experiment
  tolerates three. Which three, and why those?
- If a prototype allows movement in the space: **who moves?** Human, system, or
  negotiated? That is adjustable autonomy as a question of meta-allocation, and
  we have not designed it.
- Does per-agent (rather than per-session) allocation break the model? Policy is
  global per session today (CLAUDE.md guardrail); per-agent autonomy would make
  "the" autonomy level a distribution rather than a value.

## 8. What would change my mind

- If someone shows that Recommendation and Co-Learning **do** differ on axis A in
  a way that matters operationally, the whole argument weakens.
- If the empty cells turn out to be uninteresting in practice — nobody wants
  supervised co-learning — the split buys expressiveness nobody spends.
- If the experiment design needs the modes to be *atomic* for statistical
  reasons, resolving them into axes may create more analysis problems than it
  solves.

## 9. Related

- [interaction-framework.md](interaction-framework.md) §2 (kind), §3 (allocation), §4 (Human-in-Control)
- [interaction-modes-brief.md](interaction-modes-brief.md) — authoritative mode spec
- [design-system-independence.md](design-system-independence.md) — same document shape, but a decision rather than a discussion
- `frontend/src/app/core/widgets/widget-mode-axes.ts` — the seam in code

**References.** Sheridan, T. B., & Verplank, W. L. (1978). *Human and Computer
Control of Undersea Teleoperators.* MIT. · Timpe, K.-P., & Kolrep, H. (2002).
Taxonomie des Berliner Zentrums Mensch-Maschine-Systeme. · Parasuraman, R.,
Sheridan, T. B., & Wickens, C. D. (2000). A Model for Types and Levels of Human
Interaction with Automation. *IEEE Trans. SMC-A* 30(3), 286–297. · Shneiderman,
B. (2022). *Human-Centered AI.* Oxford University Press. · Stadelmann, T.,
Merkt, N., & Barr, R. (2026). The stochastic nature of ML and high-consequence AI.
