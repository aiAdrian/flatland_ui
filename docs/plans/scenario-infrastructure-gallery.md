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

| Term (UI, German) | Code | Means |
|---|---|---|
| **Netz** | `network` | Topology only: grid, cells, switches, stations |
| **Betriebsprogramm** | `traffic` | Which trains run where, when, with which calls |
| **Störungslage** | `disruption` | What interferes: scripted, sampled, or random |
| **Szenario** | `setup` | The composition — the thing you actually launch |
| Strategien | *(keep `scenario` panel type)* | The policy-compare surface, **retitled** |
| Betriebsszenario (D4.1) | `operational_scenario` | The consortium's UC1.R-* catalogue |

**Do not rename the `scenario` panel type.** It is wired through
`panel-plugin-host`, the availability map, the widget catalog and saved layouts;
the guardrail against parallel flags applies to type keys too. Only the *title*
changes ("Strategien"), plus a comment saying why the key differs from the label.

---

## 2. Four layers, not two

The separation already exists in the backend — half-built and undocumented.
`disturbances.py` states it outright in its module docstring: a disturbance file
is *"the third layer of a premade setup, on top of the scene (what the network
and the missions are) and the plan (what every train is supposed to do)"*. And
`_PRESETS` entries already carry `path` + `plan` + `disturbances` + `session`.

| Layer | Fixes | Today |
|-------|-------|-------|
| **Netz** | topology, stations, capacity | ✓ scene JSON · pickled env · generated (seed + params) |
| **Betriebsprogramm** | trains, relations, departures, calls | ⚠️ **lives inside the Netz** (`scene.agents`) or in the `plan` file |
| **Störungslage** | what goes wrong, when, to whom | ✓ `fixtures/*/disturbances/` + `malfunction_rate` (+ the event budget, planned) |
| **Szenario (Setup)** | the composition + algorithm + pacing + layout + modes | ✗ exists only as prose in `_PRESETS` comments |

What the frontend shows of this: **one dropdown**, labelled Infrastructure,
mixing generated env, saved scenes and presets, with disturbance checkboxes
appearing underneath when the chosen entry happens to ship them
([app.component.html:401-460](../../frontend/src/app/app.component.html)). The
four layers are invisible, so "same infrastructure, different result" is not a
statement anyone can make precisely.

---

## 3. The real work: splitting Netz from Betriebsprogramm

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

- A Netz with no `trafficId` behaves exactly as today — its `agents` *are* its
  Betriebsprogramm, and the catalog shows it as "traffic: eigenes (n Züge)".
- A Netz with `trafficId` resolves the traffic from the traffic library, and the
  session builder uses that instead. One resolution point
  (`count_routable_agents` / the scene→env adapter), not a scattered change.
- Extracting the two PF–CH corridor variants into one Netz + two
  Betriebsprogramme is then a fixture change, and it is the acceptance test for
  the split.

---

## 4. What must be described per entry

Modelled on `WidgetMeta`: a machine-readable registry, a narrative doc, and an
in-app gallery rendering the registry. That pattern works; do not invent a second
one.

### 4.1 Netz

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

### 4.2 Betriebsprogramm

| Field | Why |
|---|---|
| `id`, `name`, `networkIds` | identity + which Netze it fits |
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

### 4.3 Störungslage

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

### 4.4 Szenario (Setup)

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
- **P3 — the Netz/Traffic split** (§3), with the two PF–CH corridor variants
  collapsing into one Netz + two Betriebsprogramme as the acceptance test.
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
2. **Where does the generated random environment fit?** It is a Netz with no
   file — a *recipe* (seed + params) rather than an artefact. Either a
   `kind: 'generated'` Netz whose "file" is its parameter set, or a fourth origin.
3. **Does a Setup pin the interaction mode, or list compatible modes?** Pinning
   makes a study condition one selectable entry; listing keeps the mode
   comparison inside one Setup — which the mode-layouts plan assumes.
4. **How much of the D4.1 catalogue do we instantiate?** Seven operational
   scenarios exist; we have material for perhaps two. Naming the gap in the
   gallery is more useful than quietly covering one.
