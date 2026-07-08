# Widget spec — Link Map (ZWL)

> Additional widget alongside the shipped `marey` (Graphic Timetable) widget —
> not a replacement. Ports code from
> [`flatland-association/flatland-hmi`](https://github.com/flatland-association/flatland-hmi)
> (MIT license) rather than building a parallel algorithm from scratch, per
> CLAUDE.md's "reuse, don't reinvent" rule.

## 1. Identity
- **Name:** Link Map (ZWL)
- **`kind`:** prediction
- **`granularity`:** overview-detail
- **Default zone:** center
- **Panel `type`:** `link-map`
- **Catalog id (if any):** new — no existing backlog id fits; not B2 (B2 is
  conflict-ribbons on the *existing* Marey's cell-based y-axis, from-scratch UI
  per its own spec). Proposed id: **B4**.
- **Source(s):** flatland-hmi (flatland-association), MIT license.
- **Grounding reference:** flatland-hmi's own three-view HMI —
  [`ZWL.md`](https://github.com/flatland-association/flatland-hmi/blob/main/ZWL.md):
  "Map" (grid), "Link Map" (linearized station-to-station view),
  "ZWL"/`marey` (time-space diagram) built on top of the Link Map's
  station/link linearization. This *is* the reuse target — not a paper or
  consortium deliverable, a sibling open-source Flatland HMI. Reuse, don't
  reinvent: port `extract_link_map()` rather than re-deriving a linearization
  algorithm from our own `marey_topology.py` cell classifier.

## 2. Promise
Read train movements over time against a **station/link-linearized** y-axis
(gate-to-gate topology) instead of raw cell rows/cols — clearer for networks
with switches/diamonds where the existing Marey's per-cell classification
gets visually noisy.

## 3. Per-mode behaviour
V1 mirrors `marey`'s own scope: same in all three modes, no mode-specific
branching. (Conflict/forecast overlays, if ported later per B2's spec, would
introduce per-mode framing then — out of scope for this port.)

- **Recommendation (WP 3.1):** Same rendering as Co-Learning/Director — a
  read/inspect widget, no accept/reject surface of its own.
- **Co-Learning (WP 3.3):** Same.
- **Director (WP 3.4):** Same.

## 4. System interaction
- **Data in:**
  - New store signal `store.linkMap` (grid / mapping / levels), fed by a new
    endpoint.
  - Existing `store.history()` / trajectory signals for agent positions
    (already consumed by `marey-chart.component.ts`) — reused, not duplicated.
- **Actions out:** none in V1 (read-only view); hover/select mirrors
  `marey-chart`'s existing `store.setAgentHoverAgents` pattern if wired.
- **Backend table:**

| Field / capability | Available now | To build (flagged) |
|--------------------|:-------------:|:------------------:|
| Agent trajectory points `(i,t,r,c)` | ✓ (`session.store`, existing Marey history) | |
| `flatland.envs.stations_links` types (`StationsLinks`, `Fibre`, `Link`, `Station`, `Gate`, `Pin`) | | ✓ — merged into `flatland-rl` main 2026-07-05 ([PR #441](https://github.com/flatland-association/flatland-rl/pull/441)), **not yet on PyPI** (latest release 4.2.6). Requires pinning `flatland-rl` to a git commit. |
| Stations/links generation for our envs (SparseRailGenerator emitting `StationsLinks`) | | ✓ — verify our env/scenario setup actually populates this attribute after the dependency bump; may need scenario-builder wiring. |
| Link-map linearization algorithm (`extract_link_map()` + ~15 helpers) | | ✓ — **port** from flatland-hmi's `backend/app/link_map.py` into `backend/app/core/link_map.py`, with attribution comment (MIT). Do not re-derive from `marey_topology.py`. |
| New endpoint exposing `{grid, mapping, levels, incompleteCells}` | | ✓ — e.g. `GET /{id}/hmi/link-map`, following existing `models/hmi.py` conventions. |
| Frontend rendering (SVG polyline paths, grid→link-map coordinate transform) | | ✓ — port the *pure* transform logic from flatland-hmi's `marey.component.ts` (~170 lines) and `link-map.component.ts` (~115 lines); do **not** port their `StateService`/`RendererService`/`ControllerService` RxJS layer — rewrite against our `SessionStore` signals per CLAUDE.md (standalone + signals). |

## 5. Allocation & accountability touchpoints
- **Loop stage:** context (an alternate read of the current/planned situation,
  not a decision or notification surface in V1).
- **Owner per mode (`allocation`):** human owns interpretation in all three
  modes (read-only widget, no actuation).
- **Decision events emitted:** none in V1.

## 6. Acceptance scenario
Load a scenario whose rail network was generated with the updated
`SparseRailGen` (stations/links present). Open the Link Map widget: it renders
the same set of agents/timesteps as the existing Graphic Timetable widget, but
positioned along the station/link-linearized y-axis instead of raw
row/col. Toggling between the two widgets shows the same train order and
crossing structure, confirming the linearization preserves topology.
**Success criterion (Q1):** a network with ≥2 switches/diamonds shows
visually cleaner (fewer overlapping) stringlines on the Link Map than on the
existing Marey for the same run — a concrete, inspectable difference
justifying the "additional version," not a duplicate.

## 7. Effort & changes
- **Effort:** L (>400k tokens / 3–5+ days) — dependency bump + backend port +
  new endpoint + new signals-based frontend component + full registration.
- **Files / seams to touch:**
  - `backend/requirements.txt` — pin `flatland-rl` to the post-PR-#441 git
    commit.
  - `backend/app/core/link_map.py` — new, ported `extract_link_map()` +
    helpers, attribution header.
  - Backend scenario/env setup — verify/wire `StationsLinks` generation.
  - New endpoint in the existing `hmi` router + `models/hmi.py` schema
    additions.
  - `frontend/src/app/features/link-map/link-map.component.{ts,html,scss}` —
    new standalone + signals component.
  - `core/session.store.ts` — new `linkMap` signal + `refreshLinkMap()`
    (mirror `refreshForecasts()`'s throttling; do not refetch every WS tick).
  - Registration checklist (all 5 applicable seams — see below).
  - `backend/tests/` — new test for the link-map endpoint + ported algorithm.

## 8. Open questions / risks
1. **Dependency risk:** pinning `flatland-rl` to a git commit (not a PyPI
   release) is an unreleased-code dependency. Revisit the pin once a new
   PyPI release ships with `stations_links`.
2. **Env coverage:** does every scenario-builder path in this repo populate
   `StationsLinks`, or only `SparseRailGenerator`-built envs? If some
   scenarios don't, the widget needs an explicit empty/unsupported state (no
   silent blank chart).
3. **Redundancy with B2:** B2 ("Conflict-aware Marey") plans conflict
   ribbons on the *existing* Marey's cell-based y-axis. If Link Map's
   linearized y-axis turns out clearly better for readability, a follow-up
   decision (not in this spec) is whether B2's overlays should target this
   widget's y-axis instead — track separately, don't conflate now.
4. This is an explicit **reuse decision**, not a from-scratch build: the
   linearization algorithm and the coordinate-transform logic are ported from
   flatland-hmi (MIT); only the RxJS/state-service plumbing is intentionally
   *not* ported, replaced with our signals pattern.
