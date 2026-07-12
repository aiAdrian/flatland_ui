# Delegation record — Widget Gallery fixture-backed live previews

**Date:** 2026-07-11 · **Delegated to:** GLM 5.2 · **Review + live-verify:** Claude (Opus 4.8)
· **Branch:** `explore_db`

Goal: the Widget Gallery (`/widgets`) live previews currently render the real
component but **empty** (no session → "No active recommendations" etc.). Make them
show **populated examples** via lightweight **fixtures** — no static screenshot
assets (they go stale). User decision: "Live-Preview mit Fixture-Daten".

---

## The brief (give this to GLM 5.2 verbatim)

```md
# Auftrag: Fixture-Daten für die Widget-Gallery-Previews

Repo `flatland_ui-playground`, Branch `explore_db` (Angular standalone + signals,
SBB Lyne; Backend FastAPI + Flatland). Rein Frontend.

## Ziel
Die Widget-Gallery (`/widgets`, `features/widgets-gallery`) hat schon eine opt-in
**Live-Preview**, die die echte Komponente via `<app-panel-plugin-host [panel]="…">`
rendert — aber ohne Session sind die Previews leer. Speise die Preview mit einem
**Fixture-Bundle**, sodass die echten Komponenten befüllte Beispiele zeigen. Keine
statischen Screenshot-Assets.

## Zuerst lesen
- `frontend/src/app/features/widgets-gallery/widgets-gallery.component.ts`
  (`previewPanel`, `isLive/toggleLive` — bestehende Live-Preview-Logik, NICHT brechen).
- `frontend/src/app/core/session.store.ts` — die zu speisenden Signale.
- `docs/reference/data-provenance.md` — was echt/gemockt ist (Kontext).

## Ansatz (pragmatisch, weil `/widgets` eine isolierte Route ohne echte Session ist)
1. Neuer Service `core/gallery-fixture.service.ts` (`providedIn: 'root'`) oder eine
   private Methode in der Gallery-Komponente mit `seed()` / `clear()`.
2. `seed()`: **nur wenn `store.session()` null ist** (auf `/widgets` erwartet), setze
   ein Fixture-Bundle in die Store-Signale (exakte Namen aus `session.store.ts`):
   - `session` (Fake-SessionInfo — nötig, weil viele Panels darauf gaten),
   - `state` (SessionState mit ein paar Agents + Counts, für Situation-Summary/Trains/Agent-Inspector/Impact-Zählungen),
   - `scenarios` (2–3 `ScenarioOption` mit `kpiDeltas` + genau eines `isRecommended:true`),
   - `recommendations` (2–3, je mit `scenarioId` auf ein Szenario),
   - `notifications` (2–3 `AppNotification`),
   - `impact` (1–2 betroffene Züge),
   - `decisionLog` (2–3 `DecisionLogEntry`; nutze das bestehende Append oder set),
   - `coLearningFeedback` (1–2 `CoLearningEntry`, gern mit rationale/hypothesis),
   - Learning Records: 1–2 via `LearningStore.addRecord(...)` (aus `core/learning-store.service.ts`).
3. `clear()`: alle geseedeten Signale auf leer/null zurücksetzen **und**
   `LearningStore.clear()` — damit die echte App nie verschmutzt wird.
4. In der Gallery-Komponente: `seed()` in `constructor`/`ngOnInit`, `clear()` in
   `ngOnDestroy`. Guard: wenn beim Betreten schon eine echte Session läuft, NICHT
   seeden und NICHT clearen (echte Session gewinnt).
5. Die bestehende opt-in Live-Preview bleibt; sie zeigt jetzt einfach befüllte Daten.
   Schematischer Fallback bleibt unverändert.

## Karte/Marey (`flatland-map`, `toggle-view`, `marey`)
Brauchen echte Grid-Geometrie/Trajektorien — schwer sauber zu fixturen. **Nicht
schlecht faken.** Wenn ein kleines valides Grid-Fixture einfach ist, gern; sonst diese
zwei/drei so lassen (Schematic reicht) und die Daten-Panels priorisieren.

## Harte Regeln
- Fixtures sind klar als „gallery fixture / test data" kommentiert; sie leben in der
  Gallery/dem Fixture-Service, nicht in Produktionspfaden.
- **Nicht anfassen**: `_recordTrajectory`, scenario-refresh-throttling,
  `_recoverPolicyAndRetry*`, der echte Session-/Play-Flow, die Countdown-/`bus.emit`-Pfade.
- Angular standalone + signals; Lyne; keine Hardcoded-Farben (`npm run lint:styles` grün).
- Kein Leak: nach Verlassen von `/widgets` müssen die Store-Signale wieder leer sein
  (in einer echten Session darf nichts von den Fixtures auftauchen).

## Verifikation
- `cd frontend && ng build` clean; `npm run lint:styles` grün; `backend/tests/` unberührt.
- Argumentiere, dass `clear()` in `ngOnDestroy` das Leak verhindert (kein Browser in
  deiner Session nötig — die Live-Verifikation im Browser macht der Reviewer).

## Abgabe
Kleiner Diff: neuer Fixture-Service + Gallery-Wiring (+ ggf. minimal SCSS). Kurze
PR-Notiz mit den geseedeten Signalen und explizit, dass `clear()` das Leak verhindert.
Karte/Marey-Status vermerken (fixturiert oder bewusst schematisch belassen).
```

## Review checklist (for the reviewer afterwards)

- Live: `/widgets`, toggle Live preview on Recommendations / Impact / Scenario /
  Decision-Log / Co-Learning Reflection → populated. No console errors.
- **Leak test:** leave `/widgets`, start a real Guided Demo → none of the fixture
  data appears; store is clean.
- `lint:styles` + `ng build` green; backend tests untouched.

## Outcome — reviewed & live-verified (2026-07-11)

Built by GLM 5.2. New: `core/gallery-fixture.service.ts` (`seed()`/`clear()`, guarded by
`session() === null` and a `_seeded` flag). `learning-store.service.ts` gained a
non-destructive `resetToPersisted()`. Gallery wired via `ngOnInit`/`ngOnDestroy`.

**Good divergence from the brief (accepted):** the brief said clean up with
`LearningStore.clear()` — which also wipes `localStorage`, destroying the operator's
real confirmed preferences. GLM instead seeds fixture records as `'once'` (in-memory,
never persisted) and clears via `resetToPersisted()` (reloads localStorage untouched).
Correct call — avoids real-data loss.

Live verification (in-app browser):
- Fixtures seed on `/widgets` (session `gallery-fixture-session`, 3 scenarios, 2 recs,
  3 notifications, 2 impact, 3 decision-log, 1 co-learning, 1 learning record, 4 agents).
- Live previews render **populated**: Recommendations (full scored card), Notifications
  (3 events), Situation Summary (1/4 arrived · 3 active · 1 delayed · 1 malfunction).
- **Leak test PASS:** after leaving `/widgets`, `session()` null + all seeded signals
  empty; a pre-seeded **real** persisted learning record survived in both the store and
  localStorage, while the fixture `'once'` record was discarded. No real-data loss.
- `ng build` clean, `lint:styles` green, no console errors.

**Impact gap — FIXED (Claude, 2026-07-11).** Root cause: `impact-panel` built its display
list (`_stable`) *only* from its own backend fetch (`_rebuildStable` in `_fetchImpact`'s
`next`), not from the seeded `store.impact()` signal — and against the fake session that
fetch 404s. Fix: added a reactive `effect(() => this._rebuildStable(this.store.impact()))`
so the stabilised display syncs with `store.impact()` from **any** source (live poll *or* a
pre-seeded fixture). The poll still rebuilds synchronously inside `_fetchImpact` for its
engage/countdown logic (kept intact); `_rebuildStable` writes `_stable` not `store.impact`
(no loop) and its merge is idempotent (redundant poll-path rebuild is harmless). This is
also a genuine production robustness win — any source that sets impact now displays.
Verified live: the Impact gallery preview shows **DISRUPTION CONFLICTS 2** (Train 0 MEDIUM,
Train 2 HIGH) with options. Map/Marey remain deliberately schematic (need real geometry).

## Status

**Done & verified** — fixtures populate the data-panel previews (incl. Impact after the
fix), leak test passes, real persisted preferences preserved. Only Map/Marey stay
schematic by design.
