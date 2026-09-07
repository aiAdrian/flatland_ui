# Widget spec — Pearl-Chain Journey Strip (Agent Inspector extension)

> `docs/plans/widget-<id>-<slug>.md`, id = the existing `agent-inspector` panel
> type this rides on, slug = `pearl-chain`. Written 2026-09-06 from the
> 2026-09-05 conversation that surfaced the idea — see that discussion for the
> original framing ("click a train in Timetable → see where it's going").
> Follows [`widget-authoring-process.md`](../reference/widget-authoring-process.md)'s
> eight-section template.
>
> **Per the create-widget skill's Step 0 ("prefer extending an existing entry
> over inventing a new one"):** this is **not a new panel**. `agent-inspector`
> is already `shipped`, `kind: context`, `granularity: detail`
> (`frontend/src/app/core/widgets/widget-catalog.ts` — `type: 'agent-inspector'`).
> This spec adds one feature to it. No new `type`, no new
> `panel-plugin-host` case, no new palette entry, no new `widget-catalog.ts`
> row — only that existing row's `description`/`promise` text changes once
> shipped. That is why this lives as its own plan doc rather than as an entry
> in [`widget-catalog.md`](widget-catalog.md) (whose A–E groups are backlog
> *candidates* for new widgets, not enhancements to shipped ones).

---

## 1. Identity
- **Name:** Pearl-Chain Journey Strip
- **`kind`:** context *(inherited from `agent-inspector` — not reclassified)*
- **`granularity`:** detail *(inherited)*
- **Default zone:** right *(inherited — no change)*
- **Panel `type`:** `agent-inspector` *(extension of the existing type, not a
  new one)*
- **Catalog id (if any):** none new — rides on `agent-inspector`'s existing
  row in `widget-catalog.ts`
- **Source(s):** [DB] (owner's research line / control-room practice) — no
  AI4REALNET deliverable names this; it is not part of D3.1/D3.2's widget
  families.
- **Grounding reference:** SBB's own passenger "journey result" pearl-chain —
  the idiom Lyne itself encodes for timetable connection results (past/
  present/future stops as a bead sequence, disruption highlighted). This is a
  real, established control-room/passenger-information practice, not a
  generic-dashboard invention — but note it is a *presentation* idiom, not an
  AI4REALNET algorithm; there is nothing to "reuse, don't reinvent" here in
  the CLAUDE.md §Cross-reference sense (checked 2026-09-05: no AI4REALNET repo
  covers per-train route visualisation).
- **Source origin:** `from-scratch, deliberately`. Lyne ships the visual idiom
  internally (`node_modules/@sbb-esta/lyne-elements/core/styles/mixins/pearl-chain-bullet.scss`)
  but that path is **not** in the package's public `package.json` `exports`
  map (confirmed by inspection, 2026-09-05) — `@use`-ing it directly would be
  an undocumented-API dependency that silently breaks on a Lyne bump. Build
  the strip with existing app/Lyne **tokens** (`--sbb-color-primary`, the grey
  scale, `--sbb-color-error` for disruption) instead, per
  [`design-system.md`](../reference/design-system.md)'s token-vs-internal-API
  distinction. This is the one deliberate from-scratch decision this spec
  makes — stated here per guardrail #3, not by omission.

## 2. Promise
See where the selected train has been, is now, and is headed — as one
compact horizontal strip — without leaving Agent Inspector or opening the
Marey chart.

Not a duplicate of existing views: Track Layout (Map) is spatial/2D, Timetable
is tabular, Graphic Timetable/Marey is a time-distance diagram **across all
trains** (conflict focus). This is the missing **compact single-train
sequence** view — and it is the direct payoff of a selection path that
already exists: clicking a row in Timetable already selects the train and the
map already highlights it (`frontend/src/app/features/timetable/timetable.component.ts:119`);
Agent Inspector already opens for that selection but today shows only two raw
coordinate pairs (`@ (x,y)` position, `→ (x,y)` target —
`agent-inspector.component.html:24-28`) with nothing in between.

## 3. Per-mode behaviour
No mode-specific branching — matches the parent widget exactly
(`agent-inspector`'s catalog entry is `availableModes: 'all'`, `ALL_MODES`,
"Same in all modes — no mode-specific branching"). The strip is purely
read-only situational awareness, not a decision surface, so there is no
Assessment/Recommendation framing question to answer (this is not a
Decision-Support widget).

- **Recommendation (WP 3.1):** shown, identical to Co-Learning/Director.
- **Co-Learning (WP 3.3):** shown, identical.
- **Director (WP 3.4):** shown, identical. (The *existing* next-decision
  override buttons in `agent-inspector` may already be gated differently in
  Director — out of scope here; this spec only adds the read-only strip
  above them.)

## 4. System interaction
- **Data in:** the selected agent's route as an ordered sequence of stops
  between origin and target, plus which of them are already passed (for
  past/current/future colouring).
- **Actions out:** none for v1 (read-only). Optional nice-to-have, not
  required: clicking a bead recentres the map on that cell — left open, see §8.
- **Backend table:**

| Field / capability | Available now | To build (flagged) |
|---|:---:|:---:|
| `agent.position`, `agent.target` (raw coordinates) | ✓ | |
| `agent.next_decision` (single next waypoint/switch) | ✓ | |
| **Named, ordered stop sequence per agent** (the actual pearl-chain content) | | ✓ — **blocked on [`cities-stations-plan.md`](cities-stations-plan.md) P2/P3**, not this spec's own work. P1 (capture) is done (`StationAwareRailEnv`/`resolve_stations()`) but wired only to Director connection-planning; nothing serializes `stations[]` or `origin_station_id`/`target_station_id` to the frontend yet. |
| Past/current/future segment state per stop | | ✓ — derivable frontend-side from live `position` vs. the stop sequence once the above exists; no separate backend field needed |
| Station **names** for the beads | | ✓ — separate question, see [`cities-stations-plan.md`](cities-stations-plan.md) §5 (embedded name for scenes, translation table for generated/ECML networks); until resolved, beads show `S1`/`S2`-style labels like the rest of the app |

**This is the actual constraint on shippability, not effort:** there is no
v1 of the *full* pearl-chain (named stops) before P2/P3 land. Two ways
forward, not mutually exclusive — see §7.

## 5. Allocation & accountability touchpoints
- **Loop stage:** context (situational awareness only — not a decision point).
- **Owner per mode (`allocation`):** n/a — nothing is decided or acted on here.
- **Decision events emitted:** none. This does not feed the accountability
  seam / interaction log; it is pure read-only context, same category as
  `situation-summary`.

## 6. Acceptance scenario
Operator clicks train `T7` in the Timetable widget while any train other than
`T7` is currently selected. Agent Inspector switches to `T7` and its
Pearl-Chain strip renders: a greyed-out bead for the origin, a highlighted
bead for `T7`'s current position, one or more upcoming beads toward the
target, and the target bead at the end — no separate lookup in Marey or the
map is needed to answer "how far along is this train, and what's next for
it?"

**Measurable success criterion (Q5 — study value):** in a usability check,
time-to-answer "how many stops remain for train T7" drops to a single glance
at Agent Inspector, measured against the baseline task of cross-referencing
Timetable + Marey to answer the same question today.

## 7. Effort & changes
Two shippable scopes, not one:

- **Degraded v1 (ships now, no backend change) — Effort S.** A one-or-two-bead
  strip using only `agent.position` → `agent.next_decision` → `agent.target`
  (all already serialized). Honest framing: label it "next waypoint", not
  "next station" — these are decision points/switches, not real stops, and
  presenting them as stations would overstate precision Flatland doesn't
  have. Files: `agent-inspector.component.html/.ts/.scss` only. No new seams
  (§ header note).
- **Full v1 (named stops) — Effort M, but sequenced *after*
  [`cities-stations-plan.md`](cities-stations-plan.md) P2/P3, which is its own
  separate S–M effort this spec does not re-scope.** Same three files, plus
  consuming the new `stations[]`/`origin_station_id`/`target_station_id`
  serializer fields once they exist.

**Recommendation:** do the degraded v1 first if there is appetite — it is
cheap, ships independently, and gives the Pearl-Chain a concrete reason to
exist in the app before the station-naming work is scheduled. Do not block on
P2/P3 unless the honest "next waypoint, not station" framing is judged not
worth shipping on its own.

## 8. Open questions / risks
- **This is the deliberate from-scratch decision** (§1 Source origin) —
  Lyne's own pearl-chain mixins are internal, not public API; we re-implement
  the visual with tokens rather than importing them.
- **Flatland has no real "stations" in the SBB sense** (confirmed against
  both `flatland-rl` 4.3.0's `stations_links.py` and the canonical
  `flatland-scenarios` JSON format — neither models human station names, see
  `cities-stations-plan.md` §5). The degraded v1's beads are decision
  points/switches; communicate this distinction in the UI copy so it doesn't
  imply false precision to a study participant.
- **Click-to-recentre-map on a bead** — left open as a nice-to-have, not
  required for either scope above.
- **Does this belong in `widget-catalog.md` at all?** Current call: no — it's
  an enhancement to a shipped widget's *content*, not a new catalog
  candidate. Revisit if the full v1 turns out to change `agent-inspector`'s
  `granularity` or availability story enough to warrant its own row.

## Related
- [`cities-stations-plan.md`](cities-stations-plan.md) §8 — names this widget
  as the consumer waiting on P2/P3; keep both docs' cross-references in sync
  if either changes.
- [`design-system.md`](../reference/design-system.md) — the token-vs-internal-API
  reasoning behind not importing Lyne's pearl-chain mixins.
