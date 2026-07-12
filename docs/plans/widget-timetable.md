# Widget spec — Timetable (Fahrplan)

> Dated spec, 2026-07-12. A tabular departure/arrival board: one row per train,
> from-stop → to-stop keyed to the **same station labels as the map stations
> layer**, plus scheduled departure/arrival and current delay. Complements the
> map (where trains/stops are) and the Marey graphic-timetable (paths over time)
> by answering the plain question "**which train runs from where to where, and
> when?**" in a scannable list. Requested by danib after per-train start/end map
> markers proved illegible.

## 1 · Identity

- **Type / slug:** `timetable`
- **Kind:** Context — *"why, how bad, whom does it affect?"* It scopes the whole
  scenario's schedule and surfaces who is late. Not Event (not an alert feed),
  not Prediction (no what-if/forecast).
- **Granularity:** overview.
- **Reference (grounding):** the printed/segment **operator timetable board**
  (Fahrplan / departure board) — control-room practice; the tabular counterpart
  to the graphic timetable (Marey).
- **Source origin:** `Source: from-scratch, deliberately.` No algorithm — it is a
  presentation of data the store already exposes. The one non-trivial piece
  (station identity) is the **shared** `SessionStore.stations()` registry, reused
  by the map stations layer, not a second implementation.

## 2 · Promise

> Scan every train's origin → destination and schedule at a glance, and read a
> map stop's `S{n}` label straight into the board (and back).

Differentiation from existing widgets (checked in `widget-catalog.ts`):
- **Trains roster** (`agents`, context): grouped by *state*, shows live
  position/deadline/actions — operational "what is each train doing now". The
  timetable is the *schedule* keyed to station labels — "what is the plan".
- **Graphic Timetable** (`marey`, prediction): graphical time-distance lines.
  The timetable is the tabular board; complementary, not a duplicate.

## 3 · Per-mode behaviour

**Mode-invariant** (`ALL_MODES`). The schedule board is a reference/context view;
it does not brand the AI or offer options, so it reads identically in
Recommendation, Co-Learning and Director. (No `modeBehavior` switch — same
pattern as the Trains roster.) Delay emphasis is driven by data
(`delay` / `time_to_deadline`), not by mode.

## 4 · Backend / data

| Field | Source | Status |
| --- | --- | --- |
| train colour chip | `AgentColorService` (frontend) | exists |
| from-stop / to-stop label | `SessionStore.stations()` + `stationLabelForCell(initial_position \| target)` | exists (this change) |
| departure / arrival | agent `earliest_departure` / `latest_arrival` | serialized already |
| delay / state | agent `delay` / `state` | serialized already |
| **intermediate stops** (detail variant) | agent `waypoints` | **NOT serialized yet** — flagged extension |

**Basic variant needs no backend change.** The detail ("with intermediate
stops") variant needs one isolated addition: serialize `waypoints` in
`serialize_agent`. Kept as a separate variant per the variant-versioning model.

## 5 · Variants (modular, per danib's principle)

- **v1 · compact board** (this build): from → to, dep/arr, delay. `variantDefault`.
- **v2 · detailed with intermediate stops** (later): expands each row with the
  ordered `waypoints` and their time windows — the ECML core feature. Shares the
  same `role: 'timetable'`; gated on the `waypoints` serializer add.

## 6 · Open questions / risks

- **Station identity is per-cell, not per-city.** `stations()` labels each
  distinct endpoint cell; two adjacent platform cells of one ECML city get two
  labels. A real city grouping needs `city_positions` (backend, from
  `stations.pkl` / a generator hook) — deferred, noted on the map stations layer
  too. Acceptable for cross-referencing map ↔ board in v1.
- No names — labels are `S{n}` (shared with the map). Real names are a later
  layer once city data exists.

## 7 · Acceptance

1. Load ECML Scene 1. Enable the map **Stations** layer → stops show `S1…Sn`.
2. Open the Timetable tile → one row per train; each row's *from*/*to* shows the
   **same** `S{n}` labels as the map stops at those cells.
3. A train past its `latest_arrival` shows a non-zero, emphasised delay.
4. Toggling the map Stations layer does not change the board (independent), but
   the labels always match.

## 8 · Registration seams (checklist)

panel-plugin-host (ts + html `@case 'timetable'`), layout-designer palette entry,
`widget-catalog.ts` `WidgetMeta` (kind context, status first-cut, role
`timetable`, variantDefault). Not mode-restricted → no
`panel-mode-availability.ts` entry. Not in the default layout.
