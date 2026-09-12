# Scenario & Infrastructure Gallery — four layers, one catalog

> **Status:** plan, ready to implement. Dated 2026-09-02.
> **Why now:** the mode layouts and the sampled event budget
> ([mode-layouts-three-zones.md](mode-layouts-three-zones.md)) both assume you can
> *name* the environment a run happened in. Today "Infrastructure" is one dropdown
> that silently bundles four independent things, so nobody can say which variable
> they changed between two runs — which for a study is the whole question.
> **Companions:** [scenario-variants.md](scenario-variants.md) (the variant axes
> this formalises) · [widget-catalog.md](widget-catalog.md) + `core/widgets/widget-catalog.ts`
> (the catalog/gallery pattern being copied) · [data-provenance.md](../reference/data-provenance.md)
> (the provenance vocabulary) · [railway-scenarios.md](../scenarios/railway-scenarios.md)
> (the D4.1 operational scenarios a setup instantiates).

---

## 1. First: "scenario" means three different things

The word is already load-bearing in three unrelated places:

| Where | What it actually means |
|-------|------------------------|
| Panel `type: 'scenario'`, `/scenario-policies`, `_invalidate_scenario_forecasts` | **Policy alternatives** — which algorithm drives, not which situation |
| [scenario_presets.py](../../backend/app/core/scenario_presets.py), `scenario_preset_id` | **The environment** — Olten, PF–CH corridor |
| [railway-scenarios.md](../scenarios/railway-scenarios.md) | **D4.1 operational scenarios** — UC1.R-1-004 "Re-scheduling at infrastructure malfunction" |

A gallery called "Scenarios" that does not settle this is unusable. Proposed
vocabulary, and it is a prerequisite, not a nicety:

| Term (UI) | Code | German | Means |
|---|---|---|---|
| **Network** | `network` | Netz | Topology only: grid, cells, switches, stations |
| **Traffic** | `traffic` | Betriebsprogramm | Which trains run where, when, with which calls |
| **Scenario** | `disruption` | Störungsszenario | What interferes: scripted, sampled, or random |
| **Layout** | `layout` | Layout | Which panels the operator sees, in which zone |
| **Mode** | `mode` | Modus | Recommendation / Co-Learning / Director |
| **Setup** | `setup` | Aufbau | The composition — the thing you actually launch |
| **Tour** | `tour` | Tour | A guided sequence of modes over one Setup, to *teach* |
| **Experiment** | `experiment` | Experiment | The same shape, to *measure* — §4.7 |
| Strategies | *(keep `scenario` panel type)* | Strategien | The policy-compare surface, **retitled** |
| Operational scenario (D4.1) | `operational_scenario` | — | The consortium's UC1.R-* catalogue |

**English is the source language**, per
[i18n-strategy.md](i18n-strategy.md): "keys and base copy are authored in
English […] German is added as a translation". The German column is the
translation, not a second vocabulary.

> **Corrected 2026-09-12 (danib).** An earlier draft of this table reserved
> **Scenario** for the composition and called the disruption layer
> *Störungslage*. Reversed, for two reasons. *Störungsszenario* is what the
> domain already calls a set of things going wrong, and it is the word danib
> reached for unprompted when listing the layers — a vocabulary nobody has to be
> taught beats one that is merely consistent. And a composition is better named
> for what it is: an **Aufbau**, the thing you set up before a run. The cost is
> that `scenario_preset_id` in the API now names an *Aufbau*, not a Szenario;
> that rename is P2 work, not a reason to keep the worse word.
>
> **The code key stays `disruption`,** not `scenario`, even though the UI word is
> Szenario — otherwise `scenario` would be a panel type *and* an entity key at
> once, which is the collision this whole section exists to remove. German label
> ≠ code key is already the pattern here: the policy panel keeps `type:
> 'scenario'` while its label becomes "Strategien".

**Do not rename the `scenario` panel type.** It is wired through
`panel-plugin-host`, the availability map, the widget catalog and saved layouts;
the guardrail against parallel flags applies to type keys too. Only the *title*
changes ("Strategien"), plus a comment saying why the key differs from the label.

---

## 2. Eight entities in four levels, not two

The separation already exists in the backend — half-built and undocumented.
`disturbances.py` states it outright in its module docstring: a disturbance file
is *"the third layer of a premade setup, on top of the scene (what the network
and the missions are) and the plan (what every train is supposed to do)"*. And
`_PRESETS` entries already carry `path` + `plan` + `disturbances` + `session`.

But three layers were never the whole model. What the operator sees (Layout),
how they work (Mode) and how a person is walked through it (Tour, or an
Experiment — §4.7) are entities too — each is data somewhere in the repo already, each is currently
hardcoded or half-expressed, and each is something a person picks on the start
screen. Written out, the model has four levels:

| Level | Entity | Fixes | Today |
|---|---|---|---|
| **World** | **Network** | topology, stations, capacity | ✓ scene JSON · pickled env · generated |
| | **Traffic** | trains, relations, departures, calls | ⚠️ **lives inside the Network** (`scene.agents`) or in the `plan` |
| | **Scenario** | what goes wrong, when, to whom | ✓ `fixtures/*/disturbances/` + `malfunction_rate` (+ the event budget, planned) |
| **Run** | **Setup** | the world composition + algorithm + pacing + seeds + baseline | ✗ exists only as prose in `_PRESETS` comments |
| **Session** | **Layout** | which panels, in which zone | ◐ `layout-presets.ts` — real data, but not in this catalog |
| | **Mode** | who decides: Rec / Co-L / Director | ✓ `InteractionMode`, chosen *after* the start |
| **Guidance** | **Tour** / **Experiment** | a sequence of modes over one Setup — to teach, or to measure (§4.7) | ✗ Tour hardcoded in three places; Experiment does not exist |

Each level consumes the one above it: a Setup names a Network, a Traffic and a
Scenario; a Tour names a Setup plus a Layout and a sequence of Modes. That is
also the order in which a person decides — and the reason the start screen
currently confuses (§11).

What the frontend shows of this: **one dropdown**, labelled Infrastructure,
mixing generated env, saved scenes and presets, with disturbance checkboxes
appearing underneath when the chosen entry happens to ship them
([app.component.html:401-460](../../frontend/src/app/app.component.html)). The
layers are invisible, so "same infrastructure, different result" is not a
statement anyone can make precisely.

---

## 3. The real work: splitting Network from Traffic

`InfrastructureScene` carries `agents` with start and target
([scene.model.ts:14-28](../../frontend/src/app/features/infrastructure-builder/models/scene.model.ts)),
and the backend derives `number_of_agents` from them
([sessions.py:231](../../backend/app/api/sessions.py)). Network and traffic are
married. The cost is already visible in the fixtures: `pf-ch-corridor` and
`pf-ch-corridor-stops` are shipped as **two networks** although only the
intermediate calls differ. Without the split the catalog grows multiplicatively —
every traffic variation forks a whole network.

**Approach — additive, not a migration.** A scene keeps its `agents` (existing
scenes must keep working, and the builder writes them). Add an optional
`traffic` reference:

```ts
interface InfrastructureScene {
  …
  agents: InfrastructureAgent[];      // stays: the scene's own default traffic
  trafficId?: string;                  // NEW: overrides agents when set
}
```

- A Network with no `trafficId` behaves exactly as today — its `agents` *are* its
  Betriebsprogramm, and the catalog shows it as "traffic: eigenes (n Züge)".
- A Network with `trafficId` resolves the traffic from the traffic library, and the
  session builder uses that instead. One resolution point
  (`count_routable_agents` / the scene→env adapter), not a scattered change.
- Extracting the two PF–CH corridor variants into one Network + two
  Traffic entries is then a fixture change, and it is the acceptance test for
  the split.

---

## 4. What must be described per entry

Modelled on `WidgetMeta`: a machine-readable registry, a narrative doc, and an
in-app gallery rendering the registry. That pattern works; do not invent a second
one.

### 4.1 Network

| Field | Why it is on the card |
|---|---|
| `id`, `name`, `thumbnail` | identity |
| `source`, `license` | Olten = flatland-association (MIT), PF–CH = Gleisschema, Demo = generated seed 42. Provenance is already a repo discipline |
| `origin` | `fixture` (in the repo) · `local` (this browser only) · `generated` |
| `size` | grid w×h, track cells, stations, switches |
| `topology` | single-track sections, passing loops, parallel routes, cities |
| **`affords`** | **which decisions this network even permits: `hold` · `reroute` · `reorder`** |
| `bottlenecks` | the contended cells/sections, named (e.g. "cols 96–101") |
| `geo` | lat/lon mapping where it exists (Olten) |
| `knownLimits` | e.g. Flatland's shortest path puts every train on row 0 where a parallel track exists |

`affords` is the field that matters most and the one that exists nowhere today.
It is currently buried in prose: in the single-track corridor **reroute is not
available at all**, so the only realistic action is hold
([guided-demo-scenario.md](../scenarios/guided-demo-scenario.md)). A network
without an alternative route reduces Recommendation mode to a yes/no question —
that belongs on the card in large type, not in a footnote in another document.

### 4.2 Traffic (Betriebsprogramm)

| Field | Why |
|---|---|
| `id`, `name`, `networkIds` | identity + which Networks it fits |
| `trains` | count, categories/roles (cargo · regional · IR) |
| `relations` | origin → destination per train |
| `departureSpread` | `latest_departure_max`; 0 means "all on the map from step 1" |
| `speedProfile` | uniform / mixed |
| **`intermediateCalls`** | **yes/no — decides whether connections exist at all** |
| `plannedConnections` | the count (Olten 171 · corridor 66 — already known, in a preset comment) |
| `hasPlan` | authored route plan vs. shortest path |
| `conflictFreeSolvable` | is a conflict-free plan possible at all |

`intermediateCalls` is the twin of `affords`: without calls there are no train
pairs meeting at a station, `planned_connections` finds nothing, and every
connection-based measure is flat — half of E1's trade-off axes have no data.

### 4.3 Scenario (what interferes)

| Field | Why |
|---|---|
| `id`, `name`, `compatibleWith` | identity + which Betriebsprogramm(e) it references |
| `kind` | `scripted` (fixed steps) · `budget` (sampled, §7 of the layouts plan) · `rate` (random malfunctions) |
| `events` | count, types, windows, targets |
| `reproducible` | which seed pins it; `rate` is the only non-reproducible kind |
| `decisionWindow` | the window of proactivity it opens, in steps |
| `isControl` | **"keine Störung" is an entry, not the absence of one** |

The control condition exists today only as "tick nothing", which makes it
invisible and unnameable in an analysis. It gets a card.

### 4.4 Setup (the composition)

| Field | Why |
|---|---|
| `id`, `name`, `purpose` | study · research · dev/demo — the three anchors from [scenario-variants.md](scenario-variants.md) §4 |
| `networkId`, `trafficId`, `disruptionId` | the composition |
| `policy` | which algorithm drives the AI side (never WoZ) |
| `pacing` | `max_episode_steps`, expected wall-clock minutes |
| `layoutPresetId` | the recommended layout ([layout-presets.ts](../../frontend/src/app/core/layout/layout-presets.ts)) |
| `modes` | which interaction modes it is meant for |
| `seeds` | which are pinned, which are drawn per run |
| `expectedDecisions` | roughly how many decision moments to expect |
| **`operationalScenario`** | **which D4.1 scenario it instantiates (UC1.R-1-004 …)** |
| **`baseline`** | **KPIs of one no-intervention run** |
| `status` | draft · validated · used-in-study-N |

The last two are what make the gallery worth opening.

- **`operationalScenario`** is the same grounding discipline every widget carries,
  and it is what connects a run to the WP4 validation campaign instead of leaving
  the mapping in someone's head.
- **`baseline`** answers the question you actually have while picking: *what does
  doing nothing cost here?* Without it, a card lists parameters; with it, it
  states a situation. See §6.

---

### 4.5 Layout

Already real data — `core/layout/layout-presets.ts`, four presets plus
"Guide Mode · Light", each with a one-sentence `purpose` and, since 2026-09-11,
a declared `zone` per column. It belongs in this catalog because a person picks
it on the start screen next to the world layers, and because the same
fixture-vs-localStorage split applies (§7).

| Field | Why |
|---|---|
| `id`, `name`, `purpose` | identity + the sentence that says what it is for — **already written, today only visible as a hover tooltip** |
| `columns[].zone` | left / center / right — the three-zone contract |
| `panels[].type` | which widgets, in which order |
| `modes` | which Modi it suits — see the caveat below |
| `origin` | `fixture` (in the repo) · `local` (this browser only) |
| `preview` | a thumbnail; a layout is chosen by how it looks |

**The caveat that shapes everything else.** The saved-layout path does not
consult `panel-mode-availability`, so a preset naming `recommendations` surfaces
it in Co-Learning and Director too. Until the mode-scoped resolver exists
([mode-layouts-three-zones.md](mode-layouts-three-zones.md) P1), `modes` is a
label, not a gate — which is why "Guide Mode · Light" is deliberately
mode-neutral.

### 4.6 Tour

The guided walk. Today it is hardcoded in three unconnected places:
`SessionStore.demoSequence` (the three modes), `MODE_INTROS`
([core/demo/mode-intro-configs.ts](../../frontend/src/app/core/demo/mode-intro-configs.ts),
already data-driven and calling itself "the seam a future Experiment Designer
would write to"), and `guidedDemoEnvOpts()` (seed 42). The "▶ Director Demo"
button is a fourth: a degenerate tour with one mode and no survey, added as a
stopgap.

| Field | Why |
|---|---|
| `id`, `name`, `description` | identity; the description is what the start screen shows |
| `modes` | the sequence — `['recommendation','co-learning','director']` today, `['director']` for the Director demo |
| `setupId` | which Setup it runs on |
| `layoutId` | which Layout it runs in — this is what makes "the same tour in the old and the new layout" a choice rather than a code change |
| `intros` | per-mode intro copy (today `MODE_INTROS`) |
| `surveyAfterEachMode` | the study instrument, on or off |
| `eventSeedPerMode` | **whether the Szenario is re-drawn per mode.** Decided 2026-09-02: yes, same budget, different seed, order counterbalanced — otherwise a participant meets the same incident three times and mode 3 measures recall ([mode-layouts-three-zones.md](mode-layouts-three-zones.md) §7). The Tour is where that policy belongs, because it is the only entity that knows there *is* a sequence |
| `expectedMinutes` | what a facilitator has to budget |

Making this an entity is what turns the start screen's first card into a real
choice: **Original** (today's tour in the hardcoded layout), **Guide Mode Light**
(the same tour in the new zone layout), later the target version — and the
Director demo stops needing a button of its own.

### 4.7 Experiment — and why it is not a bigger Tour

A Tour and an Experiment have the same *shape*: a sequence of Modes over one
Setup. They are still two entities, because what they optimise for pulls in
opposite directions.

| | **Tour** | **Experiment** |
|---|---|---|
| Optimises for | **understanding** | **measurement** |
| Audience | first-time visitor, webinar, a colleague | a participant, facilitated |
| Order of modes | fixed, for narrative — contrast is the point | **assigned** per participant (Latin square) |
| Explanation | as much as helps; intro screens may differ per mode | uniform for everyone, or it becomes a variable |
| Repeating it | fine, encouraged | **contamination** — the second run measures recall |
| Data captured | incidental | **the entire point**: decisions, timings, survey, seeds |
| Who chooses | the person at the screen | the facilitator; the participant is handed a session |
| Succeeds when | the person can say how the modes differ | the data is analysable and citable |

**Why not one entity with a `study: true` flag.** The fields that differ are
exactly the ones that must not be optional-and-forgotten. With a flag, someone
runs a study with an un-counterbalanced order, no participant id and unpinned
seeds, and nothing objects. Model it as a discriminated union instead — one
shared shell, two variants — so the compiler asks for what a study needs:

```ts
type GuidedRun =
  | { kind: 'tour';       id; name; description; setupId; layoutId;
      modes; intros; expectedMinutes }
  | { kind: 'experiment'; id; name; setupId; layoutId;
      modeAssignment;      // per participant, not a fixed list
      participantId;
      capture;             // decision log, survey, timings — declared, not implied
      seeds;               // pinned; eventSeedPerMode from §7 of the layout plan
      conditionOf }        // which study, which arm
```

**The consequence for the start screen** (§11): these are not two doors of equal
weight. A Tour is pressed by the person in front of the screen. An Experiment is
*prepared* by a facilitator and *handed* to a participant, who should not be
choosing anything — which is why the third card is the facilitator's door, not
the participant's.

**Where the Tour ends and the Experiment begins is also where the survey
changes meaning.** `features/survey/` exists and adapts to the mode already; in
a Tour it is a demo prop, in an Experiment it is an instrument, and the same
component serving both is fine only as long as the *entity* says which it is.

## 5. Composition is constrained, not free

Arbitrary crossings are invalid by construction: a plan references agent handles,
a disturbance references trains. `select_disturbances()` already raises on ids
that do not belong to the chosen preset
([scenario_presets.py:230-244](../../backend/app/core/scenario_presets.py)), and
the UI clears disturbance ticks whenever the infrastructure choice changes
([app.component.ts:756-762](../../frontend/src/app/app.component.ts)) — both are
ad-hoc guards around a rule nobody wrote down.

Write it down as declared compatibility. The back-reference field even exists
already and nothing reads it: `parse_disturbance()` keeps `scenario` from the
file ([disturbances.py:70-77](../../backend/app/core/disturbances.py)).

- Each layer declares what it fits (`networkIds`, `compatibleWith`).
- The gallery offers a **Setup** as the unit; swapping a layer offers only
  declared-compatible alternatives.
- Validation runs server-side at session creation, with the existing error path.

This keeps the multiplicative explosion out of the UI while still allowing the
one thing a study needs: *same everything, one layer swapped.*

---

## 6. The baseline run

Per Setup, one recorded no-intervention run: arrived %, mean delay, conflicts,
deadlocks — stored beside the Setup, regenerated by a script, not computed live.

It gives three things at once: a readable card ("doing nothing costs 14 min mean
delay, 2 trains never arrive"), a sanity check that the Setup still behaves as
described after a dependency bump, and the comparison denominator every KPI in
the shift review is implicitly measured against anyway.

Generated by a small CLI (`scripts/`), committed as JSON next to the fixtures, so
a changed baseline shows up as a reviewable diff. A Setup whose baseline drifts
silently is a Setup nobody can cite in a paper.

---

## 7. Where it lives

- **Catalog owner: the backend.** Unlike the widget catalog (pure frontend
  metadata), the data is in `backend/app/fixtures/`. `list_presets()` is the
  existing seam and grows into four listings (`/networks`, `/traffic`,
  `/disruptions`, `/setups`) or one `/catalog` payload. Keep the current
  `/scenario-presets` response as a compatibility shim until the welcome dialog
  is migrated.
- **Gallery route `/scenarios`**, alongside `/widgets` and `/algorithms`. There is
  no Angular router: galleries are `showXGallery` getters sniffing
  `window.location` plus a branch at the top of the shell
  ([app.component.ts:134-146](../../frontend/src/app/app.component.ts),
  [app.component.html:1-14](../../frontend/src/app/app.component.html)). Follow
  that pattern; do not introduce a router for one screen.
- **Two origins, visibly.** Fixtures live in the repo and are reviewable; scenes
  built in the Infrastructure Builder live in `localStorage` and are not — the
  same objection [layout-presets.ts](../../frontend/src/app/core/layout/layout-presets.ts)
  raises about saved designs ("lives in one browser, nobody can diff it"). So:
  an `origin` badge on every card, and a **"promote to fixture"** action that
  exports a local scene into `backend/app/fixtures/` with its metadata. For a
  study that is not convenience, it is a precondition for citability.
- **The welcome dialog becomes a picker into the catalog** rather than a second,
  divergent list. One source of truth, two renderings (full gallery, compact
  picker) — same relationship as widget catalog ↔ designer palette.

---

## 8. Sequencing

- **P0 — vocabulary.** Rename in docs + UI labels ("Strategien" for the policy
  panel, "Szenario" reserved for the composition). Type keys untouched. Cheap,
  and everything after it reads wrong without it.
- **P1 — describe what exists.** Metadata for today's fixtures (§4) in the
  backend catalog, `/scenarios` gallery rendering it read-only, `origin` badges.
  No behaviour change, no split yet — the catalog first documents reality.
  This alone answers "which variable did I change?".
- **P2 — Setups as first-class entries.** The composition layer over the existing
  presets, `operationalScenario` mapping, welcome dialog reads the catalog.
- **P3 — the Network/Traffic split** (§3), with the two PF–CH corridor variants
  collapsing into one Network + two Traffic entries as the acceptance test.
- **P4 — baselines** (§6) + the generating script.
- **P5 — promote-to-fixture** for locally built scenes.

P1 and P2 are the ones that pay immediately; P3 is the structural one and can
wait until a second traffic variation is actually needed.

---

## 9. Guardrails

- **Do not rename panel `type` keys** (`scenario` stays). Labels change, keys do
  not — saved layouts and the availability map are keyed on them.
- Existing scenes without `trafficId` must keep working unchanged; the field is
  optional and resolved at one point.
- `list_presets()` keeps its current response shape until the welcome dialog is
  migrated; the catalog is additive next to it.
- Metadata is descriptive, never behavioural: `affords`, `plannedConnections`,
  `conflictFreeSolvable` describe a fixture, they must not become inputs that
  change how the env is built.
- Baselines are generated by a committed script, never hand-edited — a
  hand-tuned baseline is worse than none.
- Backend catalog additions need coverage in `backend/tests/`, including the
  compatibility validation path.

---

## 10. Open questions

1. **Is `affords` derived or declared?** Declared is honest and cheap;
   derived (from the topology: does an alternative route exist between any
   conflict pair?) is harder but cannot go stale. Draft: declare now, derive
   later and diff the two.
2. **Where does the generated random environment fit?** It is a Network with no
   file — a *recipe* (seed + params) rather than an artefact. Either a
   `kind: 'generated'` Network whose "file" is its parameter set, or a fourth origin.
3. **Does a Setup pin the interaction mode, or list compatible modes?** Pinning
   makes a study condition one selectable entry; listing keeps the mode
   comparison inside one Setup — which the mode-layouts plan assumes.
4. **How much of the D4.1 catalogue do we instantiate?** Seven operational
   scenarios exist; we have material for perhaps two. Naming the gap in the
   gallery is more useful than quietly covering one.

---

## 11. The start screen is this model's front door

Where a person first meets the model — and today it shows the model upside down.
Four dials (Layout, Infrastructure, disturbances, grid) come first, three start
buttons come last, and six lines of prose explain how the buttons differ. The
intent is the *first* question, not the last. Three further problems, all
symptoms of the same thing:

- **Settings that do nothing stay visible.** Pick a preset and the backend
  ignores width, height and train count entirely ("when set, the env is loaded
  from file and all generation params above are ignored", `models/session.py`) —
  the fields remain, and remain editable.
- **"Infrastructure" is one word for four entities** (§2). The start screen is
  where that conflation first hits a person.
- **The Modus does not appear at all.** The central axis of the playground is
  chosen *after* starting, from the header.

### The three doors, and the entity each one picks

The cards are the model's four levels, entered at three depths:

| Card | Picks | Level | For whom |
|---|---|---|---|
| **Introduction** | a **Tour** | Guidance | first contact, the December webinar |
| **Build your own** | Network · Traffic · Scenario · Layout (· Mode) | World + Session | us, Adrian, colleagues |
| **Experiments** | a prepared **Experiment** over a saved Setup | Run | study facilitation |

**On the middle card's name** (danib, 2026-09-12: "Standard? Konfiguration?").
Recommendation: **Build your own** — it names what the person does, and it makes
the relation to the third card legible: the middle door *composes* a Setup, the
right-hand door *runs* one that was saved and named. That also supplies the
middle card's missing action: **"Save as setup"**, the same promote-to-fixture
move as §7 and the bridge from ad-hoc to citable. `Custom setup` is the
acceptable alternative.

`Standard` would be actively misleading — this is the path with the *most*
decisions, not the default one. `Configuration` is accurate and cold, and says
what the software does rather than what the person does.

### Two rules that follow from the model

1. **Show only the entities the chosen door needs.** The grid fields belong to
   exactly one case — "Build your own" with a generated Network — and nowhere else.
2. **End with one sentence, not a start button alone.** *"Du startest: Olten,
   52 Züge, Szenario 'Südeinfahrt', Layout Guide Mode Light, Modus
   Recommendation."* Naming the resolved composition before the run is the most
   direct answer to "how does a person know what they can choose": they see the
   result of choosing, before committing to it.

A small thing with leverage: every Layout preset already carries a `purpose`
sentence, and every Szenario a `description`. Both are rendered today only as a
hover tooltip. The descriptions exist — they are simply invisible.

**Open:** which door matters for the December webinar? If it is *Einführung*,
the Tour entity (§4.6) is the first thing to build and the other two cards can
stay as they are for now.
