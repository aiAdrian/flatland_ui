# Cities = Stations — surfacing Flatland's cities as named stations

> **Status:** Draft for feedback (no implementation yet)
> **Context:** Flatland's `sparse_rail_generator` builds the map around
> **cities** — every train starts and ends in one, rail-pairs within a city are
> roughly platforms. Today cities are only generation *parameters* (max count,
> spacing); the generator's per-city data is discarded before it ever reaches
> the frontend. This plan surfaces it as named stations, feeding richer train
> info ("Bern→Zürich") and a future `city` role in the visual-encoding registry
> ([[visual-encoding-registry]]). Backend + frontend; respects the CLAUDE.md
> guardrail "gate presentation in the frontend, don't reshape payloads" —
> except here the payload genuinely needs a new field, since the data doesn't
> exist in it today.

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

## 4. Phased rollout

- **P1 — capture prototype (backend only, no API contract change yet).** Wrap
  the rail generator, log/assert the captured `city_positions` /
  `train_stations` shape matches expectations for a couple of seed/config
  combos. Verifies §2 works before committing to a schema. Throwaway-safe: if
  the wrapper approach doesn't pan out, nothing downstream depends on it yet.
- **P2 — serializer + API contract.** Add `Station` model + `stations[]` +
  per-agent station ids (§3). Existing frontend fields unchanged, so this is
  additive/non-breaking for anything not yet reading the new fields.
- **P3 — frontend rendering.** Station markers on `flatland-map`; origin→target
  label ("City 2 → City 0") in `agent-inspector` / train tooltips, using
  numeric city ids until naming (§5) lands.
- **P4 — naming + `city` visual-encoding role.** Only once P1–P3 are stable:
  decide the naming scheme (§5) and register `city` as a real role in the
  registry ([[visual-encoding-registry]]), producing the "Bern→Zürich"-style
  copy the original note envisioned.

Each phase is independently useful and revertable; P1 in particular is
deliberately a spike, not committed code.

---

## 5. Open question — where do station names come from?

Flatland gives positions and orientations, **not names**. Options, undecided:

1. **Deterministic synthetic names** — seeded list of city names (e.g. Swiss
   station names) assigned by city index at env-build time, stable per seed.
   Simple, no schema growth, but names are cosmetic/arbitrary, not meaningful.
2. **Numeric only** ("City 0", "City 1"), skip naming entirely — cheapest, but
   loses the "Bern→Zürich" narrative value that motivated this in the first
   place.
3. **User/study-configurable name list** — ties into the custom scenario
   builder ([[custom-scenario-builder]] / `docs/plans/scenario-variants.md`),
   where a named topology could be part of a scenario definition rather than
   generated ad hoc. Bigger scope, but avoids a second naming mechanism later
   if the scenario builder is going to need named stations anyway.

**Draft leaning:** start with (2) for P3 (cheap, unblocks rendering), decide
between (1) and (3) only when picking up P4 — by then the scenario-builder
plan may have already settled the question.

---

## 6. Guardrails

- No change to Flatland itself; only our own generator wrapper in
  `env_factory.py`.
- Additive API contract only — don't remove or reshape existing
  `position`/`target` fields; `origin_station_id`/`target_station_id` are new,
  optional fields.
- Don't couple this to the visual-encoding registry's `city` role until P4 —
  P1-P3 should work with plain numeric ids so the two efforts stay
  independently sequenceable.
- Keep existing tests green (`backend/tests/`); add coverage for the generator
  wrapper (P1) and the new serializer fields (P2).

---

## 7. Related

- [[visual-encoding-registry]] — reserves the `city` role this plan eventually
  feeds.
- [[custom-scenario-builder]] — may subsume station naming (§5 option 3) if it
  lands first.
