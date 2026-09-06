# Cities = Stations — surfacing Flatland's cities as named stations

> **Status (re-checked 2026-09-06): P1 done, for a different consumer than
> planned; P2/P3 still open.** Two things changed since 2026-08-19:
>
> 1. **The capture problem (§1 point 2, §2) is solved** —
>    `backend/app/core/station_aware_env.py` (`StationAwareRailEnv`) and
>    `backend/app/policies/goal_based_policies/stations.py`
>    (`resolve_stations()`) now exist, committed in `a31ee7c` ("First
>    implementation for the Director mode"). They capture exactly the
>    `agents_hints` data this plan's §2 describes (`city_positions`,
>    `train_stations`), by a different mechanism than proposed (subclassing
>    `RailEnv` and overriding `_call_rail_generator`, not wrapping the
>    `rail_generator` callable in `env_factory.py` — see §2b below) and for a
>    different consumer: **Director connection-planning**
>    (`app/api/sessions.py:1097,1189` call `resolve_stations()` to build
>    `planned_connections()`), not the map/timetable UI this plan intended.
>    Frontend `StationRef` (`frontend/src/app/core/models.ts:178`) is still
>    purely mission-derived and knows nothing of this. **§1 and §2 below are
>    historical — read them for the "why", not as an open TODO.**
> 2. **§5's naming question now has upstream evidence**, from researching
>    `flatland-rl` 4.3.0's own `stations_links.py` and the canonical
>    `flatland-scenarios` JSON format — see the rewritten §5.
>
> **What's still actually open: P2 (serializer field) and P3 (frontend
> rendering)** — nothing serializes `Station`/`resolve_stations()` output to
> the frontend today (`grep stations backend/app/core/serializer.py` → no
> hits), and nothing renders station markers. The
> [Pearl-Chain Journey Strip](widget-agent-inspector-pearl-chain.md) (spec'd
> 2026-09-06) would consume exactly this once it lands — see §8.
>
> **Original context (still true):** Flatland's `sparse_rail_generator` builds
> the map around **cities** — every train starts and ends in one, rail-pairs
> within a city are roughly platforms. This plan surfaces that as named
> stations, feeding richer train info ("Bern→Zürich") and a future `city` role
> in the visual-encoding registry ([[visual-encoding-registry]]).

---

## 1. Problem (verified in code, 2026-07-05)

1. **Config exposure is already done.** `max_num_cities`,
   `max_rails_between_cities`, `max_rail_pairs_in_city` are full config fields —
   `backend/app/models/session.py:10-12`, wired through
   `backend/app/api/sessions.py:159-161`, with UI in
   `frontend/src/app/app.component.html:503-507` ("Rail Generator" settings).
   Nothing to do here.
2. **The per-city data is generated but discarded.** Flatland's
   `sparse_rail_generator`'s closure returns an `agents_hints` dict —
   `{ city_positions, train_stations, city_orientations }` (confirmed in the
   installed package, `flatland/envs/rail_generators.py:276-280`). `RailEnv.reset()`
   reads this into a **local variable** only to hand it to `line_generator` /
   `timetable_generator` (`rail_env.py:309-322`) — there is **no
   `env.agents_hints` attribute afterward**. Nothing in `backend/` reads or
   stores it (`grep agents_hints|city_positions|train_stations` → no hits
   outside the Flatland package itself).
3. **The serializer sends raw coordinates only.** `serialize_agent` in
   `backend/app/core/serializer.py:147-168` sends `position`, `direction`,
   `initial_position`, `initial_direction`, `target` — grid cells, no station
   identity. `serialize_env` (lines 176-192) has no `stations[]` array.
4. **The frontend has nothing to render.** No station/city markers in
   `flatland-map.component.ts/html`, no origin→destination label in
   `agent-inspector` or `left-sidebar`. The visual-encoding registry
   (`app.component.html` ~line 404) only has `authorship` built; `city` is a
   reserved placeholder with no data behind it yet.

**Consequence:** this is a genuine 3-layer gap (capture → serialize → render),
not a one-field addition. The capture point is the non-obvious part, since
Flatland throws the data away by design.

---

## 2. Core idea — capture at generation, not at reset

`agents_hints` only exists for the instant between the rail generator running
and the line/timetable generators consuming it, inside `RailEnv.reset()`. We
don't control that internal call. So: **wrap the `rail_generator` passed into
`RailEnv`** (a callable) so our wrapper both calls the real generator *and*
stashes the returned `optionals` dict on something we do control (e.g. an
attribute on the env-building service in `env_factory.py`, keyed by session id) —
before `reset()`'s internal logic ever discards it.

This keeps Flatland itself untouched (no monkey-patching of `RailEnv`, no fork)
— only our own generator wrapper changes.

### 2b. How it was actually built (2026-09-06)

`StationAwareRailEnv` in `backend/app/core/station_aware_env.py` takes a third
route not considered above: subclass `RailEnv` and override
`_call_rail_generator` — "the same method `RailEnv` overrides from
`AbstractRailEnv`, so this is the class hierarchy's own extension point rather
than a patch" (its own docstring). It also solves a problem this plan's §2
didn't anticipate: **what-if forking loses the attribute.** `scenario_runner`
branches go through `RailEnvPersister.save` → `load_new`, which reconstructs a
plain `RailEnv` — so `station_hints` additionally gets indexed by a SHA-256
fingerprint of the rail grid (`remember_station_hints`/`station_hints_for`),
letting a fork recover its parent's hints by grid content instead of by
identity. Note for whoever picks up P2/P3: **on `flatland-rl` 4.3.0 this
fingerprint hack becomes mostly redundant** — `RailEnvPersister` now
round-trips `stations_links` natively (`flatland/envs/persistence.py:325-326,
398-399`; see [`flatland-43-upgrade.md`](flatland-43-upgrade.md) §10). Don't
port the fingerprint mechanism to a `stations_links`-based rewrite without
checking whether it's still needed first.

The actual `Station` dataclass (`backend/app/policies/goal_based_policies/stations.py`)
combines **four** sources, not the single generator-hints path §2 envisioned —
`resolve_stations()` tries, in order: an ECML-fixture pickle (challenge
scenarios) → an Infrastructure-Builder scene's explicit `stations[]` (see §5) →
live generator hints (§2) → agent-mission cells as a catch-all fallback. All
four converge on the same `Station(id, name, stop_cells, center, source)`
shape. **This is the data model to reuse for P2's serializer field** —
don't re-derive §3 below from scratch; adapt `resolve_stations()`'s output
instead, it already handles the multi-source problem §3 assumed away.

---

## 3. Data model

Backend, new serializer field (additive, doesn't touch existing agent/env
fields):

```python
class Station(BaseModel):
    id: str
    position: tuple[int, int]
    orientation: int          # from city_orientations
    platforms: int            # len(train_stations[city_id])
    name: str | None = None   # None until naming (see §5) is decided
```

`serialize_env` gains `stations: list[Station]`. Per-agent, extend with the
station id (not full duplication of position data):

```python
class Agent(BaseModel):
    ...
    origin_station_id: str | None
    target_station_id: str | None
```

Resolve `origin_station_id` by matching `initial_position` against
`train_stations[city]` entries at capture time (§2); no Flatland API call
needed at serialize time, just a lookup built once per session.

---

## 4. Phased rollout (updated 2026-09-06 — P1 done)

- ~~**P1 — capture prototype.**~~ **Done**, via `StationAwareRailEnv` +
  `resolve_stations()` (§2b) — but wired only to Director connection-planning,
  not to serialization. Treat P1 as "reuse, don't rebuild": the next step is
  P2 adapting `resolve_stations()`'s output, not a fresh capture mechanism.
- **P2 — serializer + API contract (open).** Add a `stations[]` field to
  `serialize_env` (`backend/app/core/serializer.py` — currently has none) from
  `resolve_stations()`'s `Station(id, name, stop_cells, center, source)`
  (§2b), plus per-agent `origin_station_id`/`target_station_id` (§3). Existing
  frontend fields unchanged — additive/non-breaking.
- **P3 — frontend rendering (open).** Station markers on `flatland-map`;
  origin→target label in `agent-inspector` / train tooltips. `StationRef`
  (`frontend/src/app/core/models.ts:178`) today is mission-derived only and
  needs to switch to consuming the new `stations[]` field once P2 lands.
- **P4 — naming + `city` visual-encoding role.** §5 is now resolved in
  principle (embedded name for scenes, translation table for generated
  networks) — P4 is implementing that, not deciding it. Register `city` as a
  real role in the registry ([[visual-encoding-registry]]) once P2/P3 ship.

P2/P3 are independently useful and revertable, same as originally planned.

---

## 5. Where do station names come from? (resolved, 2026-09-06)

Flatland gives positions and orientations, **not names** — confirmed against
both potential upstream sources, so this is not a "not implemented yet"
question, it's "upstream deliberately doesn't model this":

- **`flatland-rl` 4.3.0's own `stations_links.py`** (shipped 2026-08-10, see
  [`flatland-43-upgrade.md`](flatland-43-upgrade.md) §10) *does* add a
  `Station.name: str` field — but it's auto-generated Excel-column-style
  (`A, B, ..., Z, AA, AB, ...`, per the "fix city naming overflow" commit in
  the 4.3.0 changelog), a stable internal identifier for the gate/link graph
  (gates are named `A.N`, `A.S`, …), not a human-assigned name. Don't mistake
  adopting `stations_links` for solving naming — it solves §1/§2's capture
  problem (see the status note above), not this one.
- **The canonical `flatland-scenarios` JSON format** (`scenario_generator/`,
  the authority per CLAUDE.md) — checked directly against
  `example_1_scenario.json`: **station entries carry no name at all**, only
  `{id, r, c}`. Names live one level up, on `lines` (`"name": "Direct"`) and
  `timetables` (`"name": "IC 1.1"`), referencing stations by numeric
  `stationId`. So even the format we're supposed to align to doesn't give a
  station a name — confirms this is genuinely our own HMI concern to solve,
  not something to wait for or import.

**What we already have, and what's still missing:**

- Our own **Infrastructure-Builder scene format** *does* carry a real,
  human-assigned name per station today —
  `frontend/src/app/features/infrastructure-builder/models/scene.model.ts:6-12`
  (`Station { id, name, x, y }`), and the backend already consumes it:
  `stations_from_scene()` in `stations.py:147-173` reads `station.get("name")`
  straight from the scene dict. **Option 3 below is therefore already half
  built** — for scenes, not for generated/ECML networks.
- For **generated networks** (`sparse_rail_generator`) and the **ECML
  fixture**, naming is still hard-coded `S1, S2, …` by sort order
  (`_stations_from_cities` in `stations.py:73-103`) — no real name exists or
  is asked for.

Options, now grounded rather than speculative:

1. **Deterministic synthetic names** — seeded list of names (e.g. Swiss
   station names) assigned by city index at env-build time, stable per seed.
   Simple, no schema growth, cosmetic/arbitrary but at least stable and
   readable.
2. **Numeric only** ("S1", "S2" — what exists today for generated networks),
   skip naming entirely — cheapest, loses the "Bern→Zürich" narrative value.
3. **A name per station, embedded in the document that defines the
   network** — already the pattern for Infrastructure-Builder scenes (see
   above); extend the same idea to `flatland-scenarios`-format exports by
   adding an optional `name` to each `stations[]` entry (additive — unknown
   fields don't break upstream consumers, and matches our own scene shape).
   Right fit **when name and geometry are authored together as one artefact**
   — one scenario, one map, names picked once.
4. **A separate translation table** (station id / cell → display name,
   its own small document) decoupled from the geometry. Right fit **when one
   physical network is shared across many scenario variants** — exactly the
   ECML case (`stations.py:7-9`: "which scenes it exists in" — one
   `city_positions`/`train_stations` pickle, many scenes/timetables on top).
   A translation table lets names be swapped per study condition (e.g.
   anonymised "Station A" vs. real "Zürich HB" for a survey arm) without
   touching or duplicating the shared geometry.

**Recommendation:** not a single winner — **(3) for scenes** (already the
shape we have, just needs the same idea applied when exporting to the
`flatland-scenarios` JSON format in [W7 of
`flatland-ecosystem-reuse-plan.md`](flatland-ecosystem-reuse-plan.md)), **(4)
for generated/ECML networks** (only place a shared-geometry problem actually
exists). Don't build a single unified naming mechanism that tries to cover
both — the two cases have genuinely different lifecycles.

---

## 6. Guardrails

- No change to Flatland itself; the capture mechanism is
  `StationAwareRailEnv` (§2b), already in place — don't add a second one.
- Additive API contract only — don't remove or reshape existing
  `position`/`target` fields; `stations[]` and
  `origin_station_id`/`target_station_id` are new, optional fields.
- Don't couple this to the visual-encoding registry's `city` role until P4 —
  P2/P3 should work with plain station ids so the two efforts stay
  independently sequenceable.
- Keep existing tests green (`backend/tests/`); add coverage for the new
  serializer fields (P2). `backend/tests/test_station_aware_env.py` already
  covers P1 (§2b) — extend it, don't duplicate it.

---

## 7. Related

- [[visual-encoding-registry]] — reserves the `city` role this plan eventually
  feeds.
- [[custom-scenario-builder]] — may subsume station naming (§5 option 3) if it
  lands first.
- [`flatland-43-upgrade.md`](flatland-43-upgrade.md) — the `stations_links`
  upstream data model referenced in §5, and the reason `StationAwareRailEnv`'s
  fork-fingerprint hack (§2b) may be droppable post-upgrade.
- [`flatland-ecosystem-reuse-plan.md`](flatland-ecosystem-reuse-plan.md) W7 —
  the `flatland-scenarios` JSON export this plan's §5 option 3 (embedded
  name) should target.

---

## 8. Consumer waiting on this (2026-09-05, spec'd 2026-09-06)

**[`widget-agent-inspector-pearl-chain.md`](widget-agent-inspector-pearl-chain.md)** —
a "Perlschnur"/pearl-chain per-train journey strip, spec'd as an extension of
`agent-inspector` (not a new widget — that spec explains why it isn't in
`widget-catalog.md`). It needs exactly P2/P3's output (a sequence of named
stops between origin and target) for its *full* version — but that spec also
defines a **degraded v1 that ships now**, using only data already serialized
(`agent.next_decision`), with honest "next waypoint" framing instead of
implying real stations. Not a reason to reorder this plan; just a downstream
reason P2/P3 has an actual consumer beyond the map.
