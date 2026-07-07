# Scripted Events — Deterministic scenario events for User Study 2

> **Status:** Draft for discussion with FHNW Psy team
> **Context:** User Study 2 requires reproducible, scripted event chains
> (weather warnings, boarding delays, area blockages) that create "windows
> of proactivity." Our current demo uses only emergent conflicts from
> random malfunctions. This plan adds a **deterministic event layer** on top
> of the existing simulation, without replacing it.

---

## 1. Problem

The SBB protocol (User Study 2) defines a precise scenario script:

| Sim-time   | Event                                                       |
|------------|-------------------------------------------------------------|
| t = 3'     | Weather warning: heavy rain in north sector                 |
| t = 4-5'   | G1 (cargo) approaches rain area — risk of traction loss     |
| t = 5-8'   | **Window of proactivity**: reroute / stop / do nothing      |
| t = 8-12'  | Consequences play out (blockage or bottleneck)              |
| t = 8-18'  | P1 boarding delay (+3') → crosses P2 at single-track       |
| t = 18-30' | Cool-down: consequences become visible, scenario ends       |

Our demo has **none of this**: no weather, no named trains, no scripted
timing, no proactivity windows. Events are purely emergent from seed +
malfunction rate.

---

## 2. Design: ScriptedEventScheduler

A new backend module that fires deterministic events at fixed sim-steps,
independently of random malfunctions.

### 2.1 Event types

```
EventType = "warning" | "area_block" | "train_delay" | "capacity_reduction"
```

| Type                 | Grid effect                              | HMI effect                    |
|----------------------|------------------------------------------|-------------------------------|
| `warning`            | None (info only)                         | Notification + map highlight  |
| `area_block`         | `set_transitions(cell, 0)` for N cells   | Cells marked red on map       |
| `train_delay`        | Inject malfunction or reduce speed       | Train badge + notification    |
| `capacity_reduction` | Remove one direction's transitions       | Affected track shown dashed   |

### 2.2 Scenario config format

```json
{
  "name": "weather_north",
  "description": "Heavy rain blocks steep section, causes boarding delay",
  "time_ratio": 3,
  "trains": {
    "G1": { "handle": 0, "label": "G1 Cargo (schwer)", "role": "cargo" },
    "P1": { "handle": 1, "label": "P1 Regional Nord",  "role": "passenger" },
    "P2": { "handle": 2, "label": "P2 Interregio",     "role": "passenger" },
    "P3": { "handle": 3, "label": "P3 Regional Süd",   "role": "passenger" }
  },
  "events": [
    {
      "step": 9,
      "type": "warning",
      "severity": "medium",
      "label": "Wetterwarnung: Starkregen im Nordsektor",
      "highlight_cells": [[3,5],[3,6],[4,5],[4,6]],
      "icon": "cloud-rain"
    },
    {
      "step": 15,
      "type": "area_block",
      "cells": [[3,5],[3,6],[4,6]],
      "duration": 80,
      "severity": "high",
      "label": "Steile Sektion gesperrt (Nässe/Traktionsverlust)",
      "revert": true
    },
    {
      "step": 25,
      "type": "train_delay",
      "agent_handle": 1,
      "delay_steps": 12,
      "severity": "medium",
      "label": "P1: Boarding-Verzögerung (+3 Min, Starkregen)"
    },
    {
      "step": 40,
      "type": "warning",
      "severity": "high",
      "label": "P2 nähert sich Eingleisigkeit — Kreuzungskonflikt erwartet",
      "highlight_cells": [[8,12],[8,13]],
      "related_agents": [1, 2]
    }
  ]
}
```

### 2.3 Backend architecture

```
backend/app/core/
├── scripted_events.py          ← NEW: ScriptedEventScheduler
├── scenario_configs/           ← NEW: JSON scenario definitions
│   ├── weather_north.json
│   ├── switch_failure.json
│   └── capacity_bottleneck.json
├── scenario_runner.py          ← MODIFIED: call scheduler.tick(step)
├── conflict_detector.py        ← unchanged
└── notification_manager.py     ← MODIFIED: accept scripted notifications
```

**`ScriptedEventScheduler`** core logic:

```python
class ScriptedEventScheduler:
    def __init__(self, config: dict, env: RailEnv):
        self.events = config["events"]
        self.train_labels = config.get("trains", {})
        self._original_transitions: dict[tuple, int] = {}
        self._active_blocks: list[dict] = []
        self._env = env

    def tick(self, step: int) -> list[dict]:
        """Called every sim step. Returns list of triggered events."""
        triggered = []
        # Fire new events
        for ev in self.events:
            if ev["step"] == step:
                self._apply(ev)
                triggered.append(ev)
        # Revert expired blocks
        for block in list(self._active_blocks):
            if step >= block["step"] + block["duration"]:
                self._revert_block(block)
                self._active_blocks.remove(block)
        return triggered

    def _apply(self, ev: dict):
        if ev["type"] == "area_block":
            for cell in ev["cells"]:
                r, c = cell
                orig = self._env.rail.get_full_transitions(r, c)
                self._original_transitions[(r, c)] = orig
                self._env.rail.set_transitions((r, c), 0)
            self._active_blocks.append(ev)
        elif ev["type"] == "train_delay":
            # Inject artificial malfunction
            agent = self._env.agents[ev["agent_handle"]]
            mh = agent.malfunction_handler
            mh.malfunction_down_counter = ev["delay_steps"]
        # "warning" and "capacity_reduction": handled by HMI only or partial block

    def _revert_block(self, ev: dict):
        for cell in ev["cells"]:
            r, c = cell
            orig = self._original_transitions.get((r, c))
            if orig is not None:
                self._env.rail.set_transitions((r, c), orig)
```

### 2.4 Integration in ScenarioRunner

In `scenario_runner.py`, after each `env.step(actions)`:

```python
triggered = self._event_scheduler.tick(step)
for ev in triggered:
    self._notification_manager.add(
        kind="warning" if ev["severity"] != "high" else "error",
        title=ev["label"],
        message=ev.get("description", ""),
        related_element=ev.get("related_agents"),
    )
```

### 2.5 API additions

New endpoint to expose active/upcoming events to the frontend:

```
GET /sessions/{id}/events
→ { "active": [...], "upcoming_warnings": [...], "train_labels": {...} }
```

### 2.6 On/off toggle (an- und abschaltbar)

Scripted events müssen jederzeit komplett abschaltbar sein — z.B. für die
freie Demo, für Kontroll-Conditions ohne Events, oder wenn man nur die
emergenten Random-Malfunctions testen will.

**Muster:** identisch zum bestehenden `malfunctionsEnabled`-Toggle in den
Session Settings (`app.component.ts`, persistiert in localStorage unter
`flatland_ui_session_settings_v1`).

- Neuer Toggle `scriptedEventsEnabled` (default: aus) in den Session Settings,
  direkt neben dem Malfunctions-Toggle
- Wenn aus: `ScriptedEventScheduler` wird gar nicht erst instanziiert bzw.
  `tick()` ist ein No-op → keine Events, keine Notifications, keine Overlays
- Persistiert wie alle anderen Settings; überlebt Reset/Reload
- Greift erst beim nächsten Session-Neustart (wie die anderen Env-Settings),
  weil das Event-Script an die Session/das Grid gebunden ist
- Später (Phase 2): pro-Szenario wählbar, welches Event-Script geladen wird —
  der globale Toggle bleibt als Master-Schalter darüber

Backend: `create_session` / `reset`-Payload bekommt ein optionales Feld
`scripted_events: { enabled: bool, config: "weather_north" }`. Fehlt es oder
`enabled=false`, läuft die Session wie heute (rein emergent).

---

## 3. HMI: Where do warnings appear?

### 3.1 Options considered

| Option | Description | Pro | Con |
|--------|-------------|-----|-----|
| **A) Notifications panel** (existing, left sidebar) | Warnings appear as notifications like malfunctions do today | No new UI; consistent | Gets buried among other notifications; no spatial context |
| **B) Dedicated "Lage" panel** (new, left sidebar) | New collapsible section above notifications: "Lagebild / Situation" | Clear separation; matches dispatcher mental model | More UI complexity; left sidebar already has 3 sections |
| **C) Map overlay** (center pane) | Warning zones drawn directly on the Flatland map with colored regions | Immediate spatial awareness; very visual | Can clutter the map; hard to dismiss |
| **D) Combined: Map overlay + notification toast** | Zone highlight on map + brief toast notification with action hint | Best of both; spatial + textual | Most implementation effort |

### 3.2 Recommendation: Option D (combined) — in zwei Phasen

**Phase 1 — Quick win (für erste Tests):**
- Scripted events erzeugen `AppNotification` mit `kind: 'warning'`
- Bestehender Notifications-Bereich in der linken Spalte zeigt sie an
- Notifications bekommen ein neues optionales Feld `highlightCells` — wenn
  gesetzt, werden die Zellen auf der Karte mit einem farbigen Overlay markiert
- Kein neues Panel nötig

**Phase 2 — Für die Studie:**
- Neues **"Lagebild"-Panel** oben in der linken Spalte (über Notifications):
  - Zeigt aktive Warnungen und Sperrungen als kompakte Karten
  - Jede Karte hat: Icon, Titel, betroffene Züge, Countdown bis Event
  - Klick auf Karte → Kamera zentriert auf betroffene Zone
  - Karten verschwinden wenn Event revertiert oder abgelaufen
- Map-Overlay: betroffene Zellen bekommen eine halbtransparente Farbfläche
  - Gelb = Vorwarnung (noch befahrbar)
  - Rot = gesperrt (nicht befahrbar)
  - Orange gestrichelt = Kapazität reduziert

### 3.3 Left sidebar layout (Phase 2)

```
┌─────────────────────────┐
│  Situation summary      │ ← bestehend (KPIs, Uhr)
├─────────────────────────┤
│  ⚠ Lagebild         [2] │ ← NEU: aktive Warnungen/Sperrungen
│  ┌───────────────────┐  │
│  │ 🌧 Starkregen Nord │  │    - Countdown: "Sperrung in 2 Min"
│  │   G1, P1 betroffen│  │    - Klick → Kamera zentriert
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ 🚧 Steile Sektion  │  │    - Status: "gesperrt seit 1:20"
│  │   gesperrt         │  │    - "Aufhebung in 4 Min"
│  └───────────────────┘  │
├─────────────────────────┤
│  Notifications       [5] │ ← bestehend (Malfunctions, Deadlocks)
├─────────────────────────┤
│  Trains              [8] │ ← bestehend (Agent-Liste)
└─────────────────────────┘
```

### 3.4 Map overlay rendering

In `flatland-map` component, new layer:

```typescript
// Render event zones on the Flatland grid
renderEventZones(events: ScriptedEvent[]) {
  for (const ev of events) {
    if (!ev.highlight_cells) continue;
    for (const [r, c] of ev.highlight_cells) {
      const color = ev.type === 'area_block' ? 'rgba(220,38,38,0.25)'  // red
                  : ev.type === 'warning'    ? 'rgba(234,179,8,0.25)'  // yellow
                  :                            'rgba(249,115,22,0.25)'; // orange
      this.drawCellOverlay(r, c, color);
    }
  }
}
```

---

## 4. Train naming

The protocol requires named trains (G1, P1, P2, P3). We map Flatland handles
to labels via the scenario config's `trains` field.

**Frontend changes:**
- `AgentDTO` gets optional `label?: string` and `role?: string`
- Left sidebar, notifications, recommendations all show label instead of
  "Train 0" when available
- Agent color service assigns role-based colors (cargo = brown, passenger = blue)

**No backend model change needed** — labels are purely a frontend/config concern,
passed through the `/events` endpoint.

---

## 5. Proactivity windows

The protocol's core experimental construct. A proactivity window is the time
between a **warning** event and the corresponding **consequence** event.

```json
{
  "step": 9,  "type": "warning",    "label": "Wetterwarnung...",
  "proactivity_window": { "until_step": 20, "options": [
    { "id": "reroute_g1", "label": "G1 auf Ausweichroute umleiten",  "action": "reroute", "agent": 0 },
    { "id": "stop_g1",    "label": "G1 im Bahnhof anhalten",         "action": "stop",    "agent": 0 },
    { "id": "do_nothing",  "label": "Abwarten (G1 fährt links weiter)" }
  ]}
}
```

**HMI integration:**
- During the window, the Lagebild card shows a countdown and the options
- In **Recommendation mode**: AI highlights its preferred option
- In **Co-Learning mode**: options shown neutrally, no ranking
- If the window expires without action → default consequence fires
- The chosen option (or "no action") is logged as a proactivity event

---

## 6. Interaction with existing systems

| System | Impact |
|--------|--------|
| **Random malfunctions** | Keep running alongside scripted events. Set `malfunction_rate: 0` in study scenarios if unwanted noise |
| **Impact panel / auto-pause** | Scripted events trigger the same conflict detection → auto-pause works |
| **Recommendations** | Recommender sees blocked cells → suggests reroutes naturally |
| **Co-Learning log** | Proactivity decisions logged as `CoLearningEntry` with new `source: 'scripted_event'` |
| **Policy / what-if** | Forked envs include scripted events (scheduler cloned with env) |
| **Survey** | Add "cognitive engagement" items after each vignette (see protocol) |

---

## 7. Implementation phases

### Phase 1 — MVP for internal testing (2-3 weeks)

- [ ] `scriptedEventsEnabled` toggle in Session Settings (default off), persisted like `malfunctionsEnabled` — master on/off switch
- [ ] `ScriptedEventScheduler` class with `tick()`, `_apply()`, `_revert()` (no-op when disabled)
- [ ] JSON scenario config loader
- [ ] Integration in `scenario_runner.py` step loop
- [ ] Events → existing notifications (no new UI panel)
- [ ] One test scenario: `weather_north.json`
- [ ] Train labels in `AgentDTO` (frontend display)
- [ ] Basic cell highlighting on map (colored rectangles)

### Phase 2 — Study-ready (3-4 weeks after Phase 1)

- [ ] "Lagebild" panel in left sidebar
- [ ] Proactivity window UI (countdown + options)
- [ ] Mode-aware option presentation (Rec vs. Co-Learning)
- [ ] 3 scenario configs (weather, switch failure, capacity)
- [ ] Vignette rotation system (within-subject, randomized)
- [ ] Structured log export (JSON per vignette, not just localStorage)
- [ ] Cognitive engagement questionnaire after each vignette

### Phase 3 — Polish (2 weeks before study)

- [ ] Difficulty calibration across scenarios
- [ ] Training mode (simplified scenario for familiarization)
- [ ] Map overlay refinements (animation, legend)
- [ ] Dry-run with 2-3 test participants

---

## 8. Open questions for discussion

1. **Zellen-Identifikation:** Wie identifizieren wir die "steile Sektion" oder
   "Nordsektor" auf einem zufällig generierten Grid? Optionen:
   - a) Feste Zellen-Koordinaten, die zum Seed 42 passen
   - b) Dynamische Erkennung ("die Zellen links oben" = Topologieanalyse)
   - c) Handkuratierte Szenarien mit fixem Rail-Layout (kein Random-Generator)

2. **Szenario-Anzahl:** Das Protokoll spricht von 3 Szenarien und 2 Vignetten
   pro Condition. Brauchen wir 3 oder 6 verschiedene Event-Scripts?

3. **Wizard-of-Oz Fallback:** Falls Implementierung nicht rechtzeitig fertig —
   kann ein Testleiter Events manuell auslösen? (Admin-Panel mit "Fire Event"
   Button)

4. **Timing:** 10 Realminuten = 30 Sim-Minuten. Unser `time_ratio: 3` in der
   Config steuert das. Aber: stimmt unser Step-zu-Minuten-Mapping?

5. **Map-Overlay vs. realistischer Look:** Sollen gesperrte Zellen einfach rot
   eingefärbt werden, oder wollen wir realistischere Darstellungen (Wetter-
   Icons, Baustellensymbole)?
