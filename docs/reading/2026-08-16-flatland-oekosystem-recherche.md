# Recherche: das Flatland-Ökosystem, vollständig durchgesehen

*Aufgenommen 2026-08-16. Belegband zum Plan
[`flatland-ecosystem-reuse-plan.md`](../plans/flatland-ecosystem-reuse-plan.md).*

**Arbeitsteilung der beiden Dokumente:** der Plan hält **Entscheidungen** —
was wir nehmen, in welcher Reihenfolge, mit welchem Aufwand. Dieses Dokument hält
die **Belege und die Herkunftsgeschichten**: was tatsächlich in den Repos steht,
warum manche Dinge heißen, wie sie heißen, und was geprüft und verworfen wurde.
Wer nur wissen will, was zu tun ist, liest den Plan. Wer wissen will, warum, oder
wer die Recherche nachvollziehen will, liest das hier.

**Umfang:** 2 AI4REALNET-HMI-Repos im Detail, 14 Repos der
`flatland-association`, 43 Repos der AI4REALNET-Org, das installierte
`flatland-rl`, ein Deliverable-PDF.

---

## Teil 1 — Warum das überhaupt aufgerollt wurde

Ausgangspunkt war eine schmale Frage: was können wir aus `T3.4-with-HMI` und
`T3.3-3.4-HMI` nehmen? Beim Nachsehen zeigte sich, dass die Antwort von einer
größeren Frage abhängt, die CLAUDE.md bis dahin falsch beantwortete — **wer für
was die Referenz ist**. Daraus wurde eine vollständige Durchsicht.

Die drei Sätze, die am Ende stehen:

1. Mehrere unserer geplanten Features warten auf Fähigkeiten, die unser
   installiertes Flatland **schon hat**.
2. Es gibt ein Schwesterprojekt mit **exakt unserem Stack**.
3. Die Fahrplan-Autorenebene ist **upstream gelöst** — das AI4REALNET-Zeichenbrett
   ist ein Fork davon.

---

## Teil 2 — Die beiden AI4REALNET-HMI-Repos

### Reifegrad, ehrlich

`T3.3-3.4-HMI` ist eine PyQt-Referenz-HMI: eine Datei `app_new.py` mit 2016
Zeilen, plus Widgets. Die interessant klingenden Module sind **leere Hüllen**:

| Datei | Zustand |
|---|---|
| `src/logging/InteractionTracker.py` | alle Methoden `pass` / `return {}` |
| `src/logging/EnvHistory.py` | Liste anhängen, mehr nicht |
| `src/utils/controller_reference.py` | `get_actions()` gibt `randint(0,5)` zurück |
| `src/utils/solution/solution_translation.py` | `encode`/`decode` sind `pass` |
| `src/negotiation/NegotiationProxy.py` | 616 Bytes, `perform_negotiation()` ist `pass` |

`get_solution_suggestions()` liefert fünf fest verdrahtete Strings („Reroute via
alternate track", „Apply speed reduction", …). Der Director-Modus ist laut README
ausdrücklich WIP. **Es gibt dort keine Algorithmen zu holen.**

Beide Repos bestehen aus je einem einzigen „Initial commit" von **Julia
Stadelmann (`julia.stadelmann@fhnw.ch`), 26.03.2026** — gesquashte Code-Dumps.
Autorschaft innerhalb der Dateien ist damit nicht rekonstruierbar.

### Was dort trotzdem etwas taugt: die Interaktionsstruktur

Aus den Screenshots (`src/imgs/`) und `app_new.py` gelesen:

- **Analyse-Triple.** Das Lösungsfenster zeigt `RISK ASSESSMENT` / `NUMBER OF
  ACTIONS` / `IMPACTED TRAINS` als große Label-über-Wert-Blöcke, darunter eine
  Tabelle `Train | Delay` mit menschenlesbaren Werten („2 min delay", „90 sec
  delay"). Unser `models/hmi.py` kennt keines dieser Felder.
- **Prognose vs. Wirklichkeit im gleichen Fenster.** Das Incident-Review benutzt
  dieselbe Fensterstruktur wie die Vorab-Analyse — nur sind die Verzögerungen
  nicht mehr prognostiziert, sondern tatsächlich eingetreten.
- **Herkunft im Titel.** „*Formulated* Solution Analysis – Train 6" gegenüber der
  KI-erzeugten Variante.
- **Zwei gleichrangige Wege bei einer Störung:** *Solution Generation* (KI
  schlägt vor) neben *Formulate Solution* (Mensch formuliert selbst) — der
  Co-Learning-Kern aus Brief §3.3 als zwei Buttons.
- **Accept / Reject / Adjust.** Der dritte Verb fehlt unserem
  `recommendations-panel`.
- **On-map / off-map.** Der einzige permanente Sidebar-Block trennt Störungen
  danach, ob der Zug sichtbar ist; dieselbe Markierung taucht in der
  Incident-Liste wieder auf (`Train 7 - off-map - 13:55:41`). Wir kennen
  `off-map` als Agentenzustand, gruppieren aber nie danach.

**Die fünf Reflexionsfragen im Wortlaut** (`SelfReflectionWindow.QUESTIONS`):

> „Did the solution arrive as expected?" (Ja/Nein) · „What happened?" · „What
> would you change next time?" · „What general insights do you draw from this?"
> · „How can you measure success?"

Bemerkenswert: `reflection_module.png` ist **kein** PyQt-Screenshot, sondern ein
Design-Mockup **auf Deutsch** — „Reflexion / Lass uns reflektieren", eine Frage
pro Karte, großer „Weiter"-Button. Die einzige Stelle in beiden Repos mit
erkennbarer Gestaltungssorgfalt. Für den geplanten i18n-Toggle heißt das: die
konsortialen Fragen liegen bereits auf Deutsch vor.

### Das Layout selbst ist kein Vorbild

Karte plus ein schmaler rechter Streifen („Malfunction Monitor", darin
`None`/`None`, plus End/Restart/Resume). Alles andere sind **eigene
Betriebssystem-Fenster**, die über der Karte schweben. Ein
Floating-Window-Paradigma — das Gegenteil unseres angedockten Widget-Systems.
`T3.4`s HMI ist noch rudimentärer: ein vertikaler Stapel von Labels (`Scenario:`,
`Status: Ready.`, `HMI command: None`, `Rewards: {}`). Ein Debug-Harnisch.

### Der Ensemble-Agreement-Indikator

Aus `Co-Learning Approach/human_in_loop_compact.py` — der stärkste HMI-Fund
beider Repos, und er ist eine Zeile:

```
✓ All models AGREE on this recommendation
⚠ Models DISAGREE - choose carefully!
```

Drei Modelle (`safe` / `balanced` / `efficient`) empfehlen gleichzeitig, die
Oberfläche sagt, ob sie sich einig sind. Ein Grep nach `agree|disagree|ensemble`
über unser Repo findet nur Likert-Skalen im Survey — das Konzept fehlt uns
vollständig. Es sagt dem Operateur, *wann sein Urteil zählt*.

### Die Token→Planer-Naht

Zwei Mechanismen, beide winzig:

```python
# token_utils.py — AVOID_EDGE
G[u][v]["l"] = 1000; G[u][v]["learned_l"] = 1000

# blackbox_adapter.py — PRIORITY sortiert die PP-Planungsreihenfolge um
```

Damit wird aus einer Direktive etwas, das ein Planer verarbeitet, statt eines
Policy-Wechsels. **Kein kanonisches Token-Vokabular:** `token_utils` kennt
`AVOID_EDGE`, `blackbox_adapter` kennt `PRIORITY`, das Widget bietet
`Delay/Stop/Prioritise` — drei inkonsistente Sets in einem Repo.

---

## Teil 3 — Die Fahrplan-Geschichte

Diese Spur zog sich durch mehrere Runden und endete zweimal woanders, als sie
begann. Der Ablauf lohnt die Aufzeichnung, weil er zeigt, wie leicht man beim
Konsortium auf einen Fork hereinfällt.

**Schritt 1 — der Fund.** In beiden AI4REALNET-Repos liegt ein
`rail_network_drawing_board_v15.html` (161 KB, eigenständig). Es kann mehr als
unser `infrastructure-builder`: über Gleisen, Weichen und Stationen liegt eine
zweite Ebene aus **Linie → Zugklasse → Fahrplan**, mit `Travel Factor`,
`Dwell Time` und `Shift Amount`, die zu einer gerechneten Tabelle führen
(`Station ID | Distance | Travel Time | Arrival | Departure | Latest Arrival |
Earliest Departure`).

**Schritt 2 — die falsche Zuschreibung.** Ich hielt das zunächst für eine
FHNW-Eigenentwicklung.

**Schritt 3 — die Korrektur.** In `flatland-scenarios` liegt
`scenario_generator/flatland_environment_drawing_tool.html` (175 KB) — identischer
Button-Satz, identische Kürzel (`Q`/`W`/`R`/`F`/`S`/`D`/`C`). Das
AI4REALNET-Brett ist ein **Fork davon**, und zwar mit rückwärts gewandter
Benennung:

| offiziell | AI4REALNET-Fork |
|---|---|
| Lines & **Timetables** | Lines & **Schedules** |
| Train **Category** | Train **Class** |
| `trainCategories` | `trainClassId` |

„Schedule" ist genau das Wort, das Flatland 3 abgeschafft hat —
`flatland/envs/schedule_generators.py` besteht heute nur noch aus:

```python
raise ImportError(" Schedule Generators is now renamed to line_generators + timetable_generators, ...")
```

**Schritt 4 — was Flatland selbst mitbringt.** Der Begriff ist nativ:
`timetable_utils.py` definiert `Line(agent_waypoints, agent_speeds)` und
`Timetable(earliest_departures, latest_arrivals, max_episode_steps)`;
`line_generators.py` beginnt mit *„Railway Undertaking (RU) /
Eisenbahnverkehrsunternehmen (EVU)"*.

Aber die **Konstruktion** ist nicht nativ. Flatlands `timetable_generator`
würfelt:

```python
earliest_departure = np_random.randint(0, departure_window_max)
latest_arrival     = earliest_departure + ceil(shortest_path_time * 1.3 + mean_path_delay)
```

Ein zufälliges Machbarkeitsfenster, kein Fahrplan. Keine Haltezeit, kein
Travel Factor, keine benannten Zugklassen — Geschwindigkeit nur als
`speed_ratio_map`, eine Wahrscheinlichkeitsverteilung.

| | Flatland nativ | Zeichenwerkzeug |
|---|---|---|
| Linie | pro Agent aufgelöst, namenlos | benannt, wiederverwendbar |
| Zugklasse | Verteilung über Geschwindigkeiten | benanntes Objekt |
| Zeiten | gewürfelt | deterministisch gerechnet |
| Haltezeit / Lagenverschiebung | existiert nicht | `Dwell Time` / `Shift` |

**Schritt 5 — warum es überhaupt existiert.** `flatland-workshop-2024` führt im
Backlog *„Complex schedules in Flatland using Netzgrafikeditor"*. Deshalb liegen
zwei Deployment-Repos für den SBB-Netzgrafik-Editor in der Association-Org. Die
Fahrplanfrage ist dort ein bekanntes offenes Thema, nicht unsere Erfindung.

**Was daraus für uns folgt** steht als W7 im Plan: nicht das Werkzeug übernehmen,
sondern die Ebene, die es modelliert — mit den Upstream-Schlüsselnamen, damit
`Scenario.load()` unseren Export ohne Konverter liest.

---

## Teil 4 — Das Schwesterprojekt

[`flatland-hmi`](https://github.com/flatland-association/flatland-hmi):
**Angular + TypeScript + SCSS Frontend, FastAPI + Flatland-RL Backend.** Live
unter `hmi-int.flatland.cloud`. Eigenes `CLAUDE.md` (24 KB).

Drei Ansichten laut `ZWL.md`: **Map** (Raster) / **Link Map** (linearisiert
Station-zu-Station) / **ZWL** (Zeit-Weg-Diagramm, auf der Link-Map-Linearisierung
aufgebaut).

Die Trajektorien-API, die unser B4-Plan noch nicht kannte:

```
POST /trajectories                 POST /trajectories/{id}/step
POST /trajectories/{id}/fork       GET  /trajectories/{id}/link/{link_id}/map
```

`fork()` ruft `Trajectory.fork(data_dir, start_step, ep_id)` — **flatland-nativ
und in unserem 4.2.6 vorhanden**. Widget B1 braucht dafür keinen A3S-Dienst.

**Negativbefund, wichtig:** `@flatland-association/flatland-ui` (npm, v2.3.0) ist
laut Beschreibung *„Flatland association **identity** UI components"* — Branding,
keine Bahn-Widgets. Peer-Deps Angular ^20.3 + Tailwind ^3.4; wir sind Angular 22
+ SBB Lyne. Nicht übernehmen.

Der Vorgänger `flatland-hmi-hack4rail` (letzter Push Juni 2025) hatte bereits ein
**Marey-Diagramm** und *„alternative route variants that can be selected when
critical decisions need to be made"* — konzeptioneller Vorläufer unseres
`whatif-compare`.

---

## Teil 5 — Versionslandschaft

| Version | Wo | Datum |
|---|---|---|
| 4.0.3 | `flatland-blackbox`, `Tokener` | — |
| 4.0.6 / 4.1.0 | `scenario_olten` v1 / v2 | — |
| 4.2.2 | alle AI4REALNET-HMI-Repos | 2025-09-26 |
| 4.2.3 | `maze-flatland` | — |
| **4.2.6** | **wir** | 2026-06-02 |
| 4.3.0 | aktuell auf PyPI | 2026-08-10 |

### Was 4.2.6 schon kann und wir nicht nutzen

| Vorhanden | Wofür geplant |
|---|---|
| `Trajectory.fork(data_dir, start_step, ep_id)` | Widget B1 |
| `ConditionalMalfunctionEffectsGenerator` | scripted events |
| `condition_stopped_cells_and_range(start, end, cells)` | localized blocking |
| `PunctualityRewards`, `ECML2026Rewards`, `BasicMultiObjectiveRewards` | Strategie-Achsen |
| `flatland/integrations/interactiveai/` | InteractiveAI-Anbindung |

### Was 4.3.0 hinzufügt

Auf Dateiebene sechs neue Module, eines entfällt:

```
+ flatland/envs/stations_links.py              ← der Grund für B4
+ flatland/envs/record_steps_effects_generator.py
+ flatland/core/configuration_distance_map.py
+ 3× .pxd                                      ← Cython
- flatland/trajectories/regen_benchmarks.py
```

**Zwei Haken.** Erstens: 4.3.0 liefert **nur ein sdist**, kein Wheel, und fordert
`cython>=3.2.9` — `pip install` kompiliert aus dem Quellcode. 4.2.6 hatte ein
`py2.py3-none-any.whl`. Betrifft Docker und CI.

Zweitens, und für eine Studie gravierender: **die Reward-Semantik ändert sich.**
Die Kollisionsstrafe greift nicht mehr, wenn der Controller `STOP` sendet, und
ein Zwischenhalt gilt als bedient, wenn der Zug an *irgendeiner* Haltezelle der
Station steht. 4.2.6- und 4.3.0-Zahlen sind nicht vergleichbar.

Entfernte APIs (`RailEnv.record_timestep`, `_apply_timetable_to_agents`) —
geprüft, wir nutzen beide nicht. `RailEnvPersister.save`/`load_new` sind
signaturgleich, haben aber mehrere Verhaltenskorrekturen bekommen; das ist unser
Env-Fork-Pfad und damit die Stelle zum Beobachten.

---

## Teil 6 — Was `flatland-blackbox` wirklich ist

Das Repo enthält `2.1_Beta_release.pdf`, 21 Folien, **Task 2.1 Beta Release der
UvA** (Marius Captari, Herke van Hoof): *Neural Prioritized Planning: Flatland*.

Damit erklärt sich der Name und das `learned_l`-Kantenattribut, das
`token_utils.py` beschreibt. Die Idee: **Kantengewichte lernen**, sodass gieriges
PP näher an CBS-Optimum landet — differenziert durch den Solver hindurch nach
Vlastelica et al. 2019, *„Differentiation of Blackbox Combinatorial Solvers"*.

Trainingsschleife: CBS erzeugt Optimalpfade → PP auf Kosten-1-Graph →
Hamming-Distanz als Verlust → Gewichte aktualisieren → PP erneut.

Der Ertrag (30×30, mittlere Flow-Time über 100 Seeds):

| Agenten | CBS | PP | Trained PP |
|---|---|---|---|
| 3 | 59.75 | 60.74 | 60.38 |
| 7 | 140.86 | 144.39 | 143.03 |
| 11 | 224.33 | 230.14 | 227.67 |

Etwa ein Drittel der PP→CBS-Lücke, für eine torch-Abhängigkeit und eine
Trainingspipeline. Deshalb im Plan: Solver nehmen, Trainingsschleife liegen
lassen.

Zwei Punkte der „Perspectives"-Folie stehen dort als **noch nicht erledigt** —
und beide sind unser Anwendungsfall: *„if breakdowns happen, replan using updated
positions/weights"* und *„learn to assign priorities (learn to rank)"*.

### Die Entwarnung zur Versionsfrage

`cbs.py` und `pp.py` importieren **nichts aus Flatland**:

```python
from copy import deepcopy
from heapq import heappop, heappush
from math import inf
from flatland_blackbox.utils import (NoSolutionError, get_row, get_col, …)
```

Sie rechnen auf einem networkx-Graph plus Agentenliste. Alles, was sie aus
`utils.py` holen, sind reine Graph-Helfer (Zeilen 15–278). Nur die andere Hälfte
von `utils.py` — `initialize_environment`, `plot_agent_subgraphs`,
`visualize_graph_weights` — fasst Flatland an, und die rufen die Solver nie auf.

Die Solverdateien in `T3.4-with-HMI` sind **byteidentisch** mit dem Upstream
(per Diff geprüft). Die 4.0.3-vs-4.2.6-Sorge, die seit Monaten in unserer
Roadmap mitlief, ist für den Solver-Kern eine Deklarations-, keine Codefrage.

---

## Teil 7 — Die WP4-Kampagne

`ai4realnet_orchestrators/railway/` ist gewachsen. Fünf KPIs haben jetzt echten
Code statt drei Stubs:

| KPI | Name |
|---|---|
| AF-029 | AI Response time |
| AF-051 | AI-Agent Scalability Testing |
| NF-045 | Network Impact Propagation |
| PF-026 | Punctuality |
| **RS-058** | **Robustness to operator input** |

**NF-045s Methode ist unabhängig von jeder Integration übernehmenswert:**
dasselbe Szenario zweimal fahren — einmal sauber, einmal mit *einer
kontrollierten* Störung über `ConditionalMalfunctionEffectsGenerator` — und die
Differenz messen. Ein saubereres A/B-Design, als unsere Impact-Analyse heute
benutzt.

Und es gibt `ai4realnet_orchestrators/railway/playground/` mit
`orchestrator_interactive.py`. Im Code steht:

```python
# Playground: https://ai4realnet-int.flatland.cloud/benchmarks/9fbde927-…/734144d1-…
```

Der Runner lädt Olten `partially_closed`, spielt die Trajektorie ab und postet
live an InteractiveAI. **Offen und aus dem Code nicht beantwortbar: ob dieser
Benchmark-Eintrag für unser Projekt gedacht ist.** → Adrian.

---

## Teil 8 — Quer über die Domänen: ATM und Stromnetz

AI4REALNET stellt dieselbe Mensch-KI-Frage in drei Domänen. Die Algorithmen
übertragen sich nicht; **die HMI-Muster und die Human-Factors-Rahmung schon.**

### ATM

**`ATMSectorization`** — ein eigenständiges JS+D3-HMI für dynamische
Luftraum-Sektorisierung, das lehrreichste Nicht-Bahn-Artefakt der Org:

1. **No-go-Fläche zeichnen, der Planer routet um.** `CTRL` halten, über Zellen
   ziehen, loslassen — ein Theta\*-Pfadfinder routet die Luftstraßen drumherum.
   Das ist `AVOID_EDGE` als **Direktmanipulation auf der Karte** statt als
   Dropdown.
2. **Constraint-Verletzungen an der Geometrie selbst** gerendert (Mindestlänge,
   Kreuzungspunkte zu nah am Rand), nicht im Seitenpanel. Unser
   `builder-validation-panel` berichtet; deren Werkzeug *zeigt*.
3. **Komplexitätsmonitor pro Polygon** — ein „wie schwierig ist dieses Gebiet
   gerade"-Indikator. Wir haben nichts zwischen globalen KPIs und
   Einzelzug-Detail.
4. **Drill-down** vom Balken zur 120-Minuten-Prognosekurve.

**`CDRTrainer`** (Clark Borst, TU Delft) — eine einzelne HTML-Datei mit Action
Shielding, menschlichem Feedback und Expertendemonstrationen. Übertragbar ist die
Zielmenge:

> Staffelungsverlust vermeiden · Kurs wiederherstellen · Querabweichung
> minimieren · **Anzahl der Manöver minimieren**

Das letzte ist ein **Operateurslast-Ziel**: ein Plan ist schlechter, wenn er mehr
Eingriffe verlangt — unabhängig von der Verspätung. Unsere KPIs (Verspätung,
Deadlocks, Ankünfte) haben keinen solchen Term. Für eine Studie über
Mensch-KI-Teaming eine auffällige Lücke.

### Stromnetz

**`RL-agent-uncertainty-prediction-module` — Conformal Prediction.** Der
nützlichste domänenübergreifende Fund. Verteilungsfreie Vorhersageintervalle mit
Überdeckungsgarantie, **methodenagnostisch** — es umhüllt einen beliebigen
Schätzer. Unser A1-Plan zielt auf ein evidential NN, das erst trainiert werden
muss; Conformal Prediction gäbe kalibrierte Intervalle um unsere bestehenden
Verspätungsschätzungen, ohne den Schätzer zu ersetzen.

**`risk-sensitive-inverse-rl`** — ICML-2025-Paper (Lazzati & Metelli) mit einer
Studie über 15 Personen: inverses RL, das eine **Nutzenfunktion samt
Risikoeinstellung** aus Demonstrationen rekonstruiert. Nicht zum Nachbauen, aber
die richtige Referenz, wenn wir begründen, warum wir Präferenzen vom Operateur
*erklären* lassen statt sie zu inferieren.

**`XLLM`** — Multi-Agenten-LLM-Pipeline (erzeugen → kritisieren → verfeinern →
bewerten), die AC-OPF-Ergebnisse in Operateurserklärungen übersetzt. Dieselbe
Idee wie das nie umgesetzte RAG in `T3.3-3.4-HMI`. Wir haben bewusst kein LLM in
der Schleife — festgehalten, damit das ausdrücklich bleibt.

---

## Teil 9 — Fallen und Verworfenes

### Die Spiegel-Falle

Die AI4REALNET-Org spiegelt **sechs** `flatland-association`-Repos als Forks:
`flatland-rl`, `flatland-book`, `flatland-scenarios`, `flatland-baselines`,
`ai4realnet-orchestrators`, `flatland-benchmarks-f3-starterkit`. Letzter Push
zwischen **2025-09-30 und 2026-02-03**. Der `flatland-rl`-Fork dort ist elf
Monate alt und kennt weder `stations_links` noch 4.3.0.

Wer über die AI4REALNET-Org einsteigt — was CLAUDE.md bis zu dieser Recherche
nahelegte — landet auf veralteten Ständen.

### Geprüft und als nicht relevant eingestuft

`D1.1-decision-making-analysis` (ein einzelnes Word-Embeddings-Notebook),
`T2.3_explainability_dashboard` (fest an ExpertOp4Grid gebunden), `distributed_rl`,
`network-distributed-q-learning`, `safe-constrained-policy-gradient`,
`soft_label_gnn`, `failure_prediction`, `grid2evaluate`, `GNPDT`, `T2.1_*`,
`bluesky*`, `Grid2Op_MORL`, `pypowsybl2grid` — andere Domänen oder andere
Arbeitspakete.

`AI4REALNET.github.io` ist eine Vite/Tailwind-Seite **ohne Deliverable-PDFs**.
CLAUDE.mds Vermerk „D3.1 / D3.2 noch nicht verfügbar" bleibt unverändert. Einzige
Ausnahme im gesamten Bestand: das `2.1_Beta_release.pdf` in `flatland-blackbox`.

---

## Teil 10 — Was diese Recherche im Repo geändert hat

| Datei | Änderung |
|---|---|
| [`flatland-ecosystem-reuse-plan.md`](../plans/flatland-ecosystem-reuse-plan.md) | **neu** — 10 Arbeitspakete, vier Spuren, Nicht-Ziele, offene Fragen |
| [`widget-linkmap-zwl.md`](../plans/widget-linkmap-zwl.md) | `stations_links` ist auf PyPI; git-Pin-Risiko ersetzt durch die zwei Upgrade-Risiken |
| [`recommender-roadmap.md`](../plans/recommender-roadmap.md) | PP/CBS-Reuse-Ziel neu begründet; Versionssorge entkräftet |
| [`CLAUDE.md`](../../CLAUDE.md) | neuer Abschnitt „Two upstreams, not one"; Spiegel-Warnung; „erst im installierten `flatland-rl` nachsehen" |
| [`wp4-validation-alignment.md`](../reference/wp4-validation-alignment.md) | datierter Nachtrag: neues Repo-Zuhause, fünf KPIs, `playground/`-Runner |

### Zwei eigene Irrtümer, die dabei aufgelöst wurden

1. **„Die Fahrplanebene hat die FHNW gebaut."** Falsch — sie stammt von der
   Flatland Association; das AI4REALNET-Brett ist ein Fork mit veraltetem
   Vokabular.
2. **„T3.4s `flatland_blackbox` ist wegen 4.2.2 das nähere Ziel."** Die
   Begründung war falsch: die Dateien sind byteidentisch mit dem 4.0.3-Upstream,
   und die Solver hängen gar nicht an Flatland.

Beide sind im Plan an ihren Stellen korrigiert; hier stehen sie, damit die
Denkbewegung nachvollziehbar bleibt.

---

## Teil 11 — Abschliessende Einschätzung: InteractiveAI

Schlussstück der Analyse. Es beantwortet den offenen Punkt (c) aus
[`event-based-architecture-analysis.md`](../archive/event-based-architecture-analysis.md)
— *„Check whether real interop with InteractiveAI's Event Service is realistic"* —
und die Frage, ob wir die Integration überhaupt brauchen.

### Der Befund, der alles andere entscheidet

**InteractiveAI liegt nicht im Ergebnispfad der Validierungskampagne.** Am Code
geprüft:

| Pfad | InteractiveAI beteiligt? |
|---|---|
| `abstract_test_runner_railway.py` — Basis **aller fünf KPI-Runner** (AF-029, AF-051, NF-045, PF-026, RS-058) | **nein**, kein einziges Vorkommen |
| Ergebnisweg der KPIs | Docker → lokales Volume → `upload_to_s3` → FAB |
| `playground/test_runner_playground_interactive.py` | **ja** — `FlatlandInteractiveAICallbacks`, `collect_only=False`, live gegen `interactiveai.flatland.cloud` |

InteractiveAI ist also die **Vorführfläche**, nicht die Abgabeform. Im
Playground-Runner steht sogar als Kommentar, dass die Plattform den Lauf
ausbremst:

> „run faster… limiting factor becomes environment stepping time and **blocking
> requests InteractiveAI platform**"

**Damit gilt: KPIs gut abliefern und InteractiveAI anbinden sind zwei
unabhängige Vorhaben.** Wer die Tests ernst nimmt, muss die Integration nicht
tun. Das war die Vermutung, die diesen Abschnitt ausgelöst hat; sie hält.

### Oberflächenvergleich

Die beiden sind keine Konkurrenten auf derselben Achse, und das ist der Kern der
Einschätzung.

**InteractiveAI** ist eine **Ereignis-Hypervision für den Betrieb**: drei
Ansichten — Map (context) / Notifications (events) / Timeline (historic) —
über einem ereigniszentrierten Domänenmodell, generisch über Bahn, Luftverkehr
und Stromnetz. Erklärtes Ziel: *„shifting focus from alarm monitoring to
efficient task execution"*.

**Unser Playground** ist ein **Forschungsinstrument für Interaktionsgestaltung**:
45 Features, drei Automationsgrade als umschaltbare Versuchsbedingungen,
modusskalierte Layouts, Reflexion und Erhebungsinstrumente.

| | InteractiveAI stärker | Wir stärker |
|---|---|---|
| Domänenmodell | **Ereignis als erstklassiges Objekt** — Identität, Lebenszyklus, `criticality`, `parent_event_id`. Unsere „Ereignisse" sind abgeleitete Sichten ohne Identität. | — |
| Rückmeldung | Operateurshandlung und Accept/Reject hängen **am Ereignis** (Capitalization) → sauberer Prüfpfad | — |
| Breite | über drei Domänen erprobt | — |
| Betriebsreife | Mehrbenutzer, Keycloak, OperatorFabric | — |
| **Interaktionsmodi** | — | **Kennt InteractiveAI nicht.** Automationsgrad, Allocation, Partial Non-Control — das ist unsere ganze Forschungsfrage |
| Bahnfachliche Tiefe | — | Marey, Fahrplan, Agent-Inspektor, Impact-Analyse, What-if. Deren Map ist ein Punkt auf einer Karte |
| Zusammensetzbarkeit | — | Widget-/Layout-System pro Modus statt drei festen Ansichten |
| Studientauglichkeit | — | Reflexion, Surveys, Entscheidungsprotokoll auf das Experiment hin entworfen |

Die Überlappung — Karte, Meldungsliste, Verlauf — ist bei beiden die **flache
Hälfte**. Was jeweils die Substanz ausmacht, überlappt gar nicht.

### Was wir durch eine Anbindung gewinnen würden

Ehrlich: als Oberfläche **wenig bis nichts**. Unsere Daten erschienen in einer
generischeren Version dessen, was wir bereits haben, und der Teil, der uns
auszeichnet, überlebt die Übersetzung ins Event/Context-Schema nicht. Was ankommt,
ist „Zug 7 hat eine Störung" — die uninteressante Hälfte.

Zwei reale Gewinne bleiben:

1. **Konsortiale Sichtbarkeit** — unser Szenario liefe auf der Vorführfläche des
   Konsortiums. Ein Kommunikations-, kein Produktargument.
2. **Die Disziplin des Ereignismodells** — Identität, Lebenszyklus, Feedback am
   Ereignis. Das ist ein echter Gewinn, **und wir bekommen ihn ohne die
   Plattform.** Genau das empfiehlt das Archivdokument bereits: *adopt the
   pattern, not the platform*.

### Urteil

| Frage | Antwort |
|---|---|
| InteractiveAI als **Anzeige** übernehmen? | **Nein.** Doppelt unsere Oberfläche, verliert unseren Beitrag. |
| InteractiveAI als **Abgabeform** für WP4 nötig? | **Nein** — am Code belegt. Die KPIs gehen über S3 an FAB. |
| Ereignismodell mit Lebenszyklus einführen? | **Ja, unabhängig davon** — Punkt (b) des Archivdokuments, weiterhin gültig. |

Punkt (c) des Archivdokuments ist damit beantwortet: technisch wäre echte
Interoperabilität realistisch — die Clients liegen in unserem installierten
`flatland-rl`, ein lauffähiges Beispiel existiert. **Nur ist sie für unsere
Ziele nicht nötig.** Sie bliebe ein Kann, gebunden an die offene Frage aus
Teil 7, ob der Playground-Benchmark unser Projekt ist.

**Was dieses Urteil kippen würde:** wenn die Kampagnenleitung InteractiveAI als
*verbindliche* Abgabeform verlangt statt als eine Möglichkeit. Das steht in
keinem Repo — das weiß nur Adrian oder die WP4-Leitung.

---

## Anhang — Wie das reproduzierbar ist

Ohne `gh`-Authentifizierung, nur über die öffentliche API:

```bash
# Org-Bestand
curl -s "https://api.github.com/orgs/<ORG>/repos?per_page=100&sort=pushed"

# Dateibaum eines Repos
curl -s "https://api.github.com/repos/<ORG>/<REPO>/git/trees/HEAD?recursive=1"

# Datei roh
curl -s "https://raw.githubusercontent.com/<ORG>/<REPO>/HEAD/<PFAD>"

# Release-Notes / Versionsvergleich
curl -s "https://api.github.com/repos/flatland-association/flatland-rl/releases/tags/v4.3.0"
curl -s "https://pypi.org/pypi/flatland-rl/<VERSION>/json"    # zeigt auch Wheel vs. sdist
```

Der Versionsvergleich auf Dateiebene ging über zwei Tag-Bäume und `comm`; die
Byte-Gleichheit der Solver über `diff` gegen die Rohdateien beider Repos.

**Vorbehalt:** alles hier ist ein Stand vom 2026-08-16. `flatland-rl` 4.3.0 war
zu diesem Zeitpunkt sechs Tage alt. Repos ändern sich — bei Zweifel neu prüfen,
statt diesem Dokument zu glauben.
