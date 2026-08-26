# Lesedokument: Co-Learning & Reflexion

*Zusammengestellt 2026-07-16, für ruhige Ferien-Lektüre. Kein Spec, kein Plan —
eine Zusammenstellung aus dem, was im Repo bereits an Denkarbeit steckt: der
Plan (was wir bauen und warum), die Referenzen (das AI4REALNET-Konsortium) und
die Publikationen (worauf das Ganze akademisch fußt).*

---

## Warum dieses Thema

Das Reflection-Modul (`co-learning-reflection`) ist der Teil des Repos, in dem
sich am meisten Theorie auf kleinstem Raum verdichtet: Kolbs Lernzyklus,
Endsleys Situationsbewusstsein, das Supportive-AI-Framework des Konsortiums —
alles in einem eingeklappten Panel mit vier Zahlen und fünf Fragen. Gut
geeignet, um in Ruhe zu verstehen, *warum* es so aussieht, wie es aussieht,
bevor man weiterbaut.

---

## Teil 1 — Der Plan: was wir bauen und warum

### Die drei Modi, kurz

- **Recommendation (WP 3.1)** — AI schlägt vor *mit* Empfehlung, Mensch entscheidet.
- **Co-Learning (WP 3.3)** — AI bietet **neutrale** Optionen; Mensch entscheidet,
  reflektiert, simuliert Alternativen.
- **Director (WP 3.4)** — AI läuft autonom nach High-Level-Direktiven; Mensch
  überwacht (*adjustable autonomy*).

Quelle: [`docs/reference/interaction-modes-brief.md`](../reference/interaction-modes-brief.md)
— der maßgebliche Implementierungs-Brief, verankert in den konsortiumsvalidierten
Interaktionsabläufen.

### Der validierte Co-Learning-Ablauf (Mode B)

Aus dem Brief, Schritte, die ein Nutzer beim Durchklicken genau erleben soll:

1. Situation beginnt.
2. AI visualisiert den Zustand **und die Prognose**.
3. Bei einem vorhergesagten Vorfall generiert die AI **neutrale Optionen** —
   keine Empfehlung, kein Ranking, kein "beste Option"-Badge.
4. Mensch wählt eine Option.
5. **Wenn es sich beruhigt hat, kann der Mensch reflektieren.**
6. Situation läuft weiter.
7. Mensch kann simulieren *"was wäre, wenn ich anders gewählt hätte"* und
   vergleichen.

Schritt 5 und 7 sind der Kern des Reflection-Moduls — Schritt 5 ist heute
gebaut (siehe unten, inkl. des "reflect now?"-Nudges vom 2026-07-16), Schritt 7
("what-if compare", §3.3 im Brief) ist als Nächstes größerer Brocken offen.

### Was heute existiert (`features/co-learning-reflection/`)

- **Statistische Recap ("Mirroring")** — Interventionen, Interventionen trotz
  AI-Hinweis, Ankünfte, Gesamtverspätung. Der eigene Lauf, dem Operator
  gespiegelt zurückgegeben.
- **Sokratische Prompts ("Animation"/"Transparency")** — 5 kontextabhängige
  Fragen, standardmäßig 2 sichtbar (konfigurierbar), z. B. *"Du bist 3× eingeschritten
  — welche Signale haben dich dazu bewogen?"*
- **Der "Ruhe"-Trigger** — reflektieren soll möglich sein, sobald es *"calm"*
  ist, nicht nur am Episodenende. `isCalm` (Session-Store) prüft: Session
  gestartet, pausiert, keine Malfunction. Bis heute war das Signal berechnet,
  aber nirgends sichtbar gemacht — der Nudge im Panel-Header schließt genau
  diese Lücke.
- **Persistenz** — Antworten liegen pro Session in `localStorage` (kein
  Backend bisher — bewusst, siehe TODO zur Persistenzschicht).
- **Anschluss an Workstream B** — das "Warum?"-Prompt nach einem manuellen
  Override (Rationale Capture, [`docs/plans/workstream-b-rationale-capture.md`](../plans/workstream-b-rationale-capture.md))
  und die bestätigten Lernsätze (`app-learning-records`) hängen im selben
  Panel, weil beides Teil derselben Lernschleife ist.

### Was noch fehlt

- **Statistical + open-question in einem Modul** ist laut Spec vollständig,
  aber der **what-if-Vergleich** (Schritt 7, §3.3 im Brief) fehlt noch:
  eigene Wahl vs. hypothetische Alternative, beide Linien auf dem Marey-Diagramm,
  KPI-Delta. Die Maschinerie (Scenario-Panel, Marey) existiert größtenteils —
  es fehlt die explizite "compare to my actual choice"-Affordance.
- **AI lernt vom Menschen** (die andere Hälfte von Co-Learning) ist laut
  [`docs/plans/co-learning-direction.md`](../plans/co-learning-direction.md)
  der eigentlich offene, neuartige Teil: nicht "AI lernt die Aufgabe besser"
  (Level A, braucht echtes RL-Training), sondern "AI lernt, *mit dem Menschen*
  zu arbeiten" (Level B) — ein Operator-Modell, das Präferenzen und
  Vertrauen/Autonomie aus den bereits gesammelten Interaktionssignalen ableitet
  (`coLearningFeedback`: Overrides, Accept/Reject, Reflection-Antworten).
  Braucht kein GPU-Training, nur leichte Methoden (Bayesian Update über
  Reward-Gewichte, ein Bandit/Heuristik über das Autonomie-Level).

### Ein Satz zur Einordnung

> "Co-Learning ist nicht nur 'die AI lernt einen besseren Algorithmus' — es ist
> die Maschine, die lernt, *mit dem Menschen zusammenzuarbeiten*, durch die
> Interaktion." — `co-learning-direction.md`

Dieser Satz ist vermutlich der beste Kompass für alles Weitere in diesem Bereich.

---

## Teil 2 — Die Referenzen: das AI4REALNET-Konsortium

AI4REALNET ist ein EU-Horizon-Projekt; Flatland Dispatcher ist unser
Spielplatz für dessen Human-AI-Teaming-Forschung. Bevor wir Verhalten neu
erfinden, gilt die Regel: erst in den Konsortium-Referenzimplementierungen
nachsehen.

### Die offizielle Quelle: RP2 Part B (2nd EU review)

Der Implementierungs-Brief ist direkt aus dem offiziellen AI4REALNET-Bericht
abgeleitet, nicht erfunden. Zentrale Zitate (§7 im Brief):

- **Drei Kontroll-Modalitäten** = volle menschliche Kontrolle · geteiltes
  Human-AI-Co-Learning · vollautonome AI-Kontrolle. Die HMI, die alle drei
  abdeckt, *"provides the foundation for adjustable autonomy"*.
- **Co-Learning-HMI (T3.3, FHNW/Flatland):** bei Störungen kann der Operator
  *"formulate their own solutions or choose from AI-recommended solutions"*;
  Impact wird *"evaluated and presented … to evaluate trade-offs and compare
  alternatives"*; danach eine *"statistical evaluation and an open-question
  reflection module"*; die menschliche Interaktion wird als Trainingsdaten
  für kontinuierliches AI-Lernen geloggt.
- **What-if (T3.1, EnliteAI A3S/TraceRL):** eine Entscheidung in einer
  Trajektorie überschreiben, vorwärts simulieren; **Konvention: menschlich
  beeinflusste Schritte blau, AI-simulierte Schritte gelb** (Fig. 8).
- **Director (T3.4):** High-Level **Token-basierte Direktiven**; eine
  **Negotiation Proxy** löst Konflikte über den globalen Langzeit-Reward auf;
  Design muss Situationsbewusstsein und Motivation schützen.
- **Autonomie-Ziel (O4):** ≥ 70 % menschliche Akzeptanz autonomer AI-Aktionen.

### Die Konsortium-Repos (GitHub-Org `AI4REALNET`)

Für den Reflexions-/Co-Learning-Kontext konkret relevant:

- **[`T3.3-3.4-HMI`](https://github.com/AI4REALNET/T3.3-3.4-HMI)** — die
  vollständige PyQt-Referenz-HMI für Co-Learning *und* Director auf Flatland.
  Lohnt sich vor jedem neuen Co-Learning/Director-Widget kurz durchzuschauen.
- **[`agent-as-a-service-trace-rl`](https://github.com/AI4REALNET/agent-as-a-service-trace-rl)**
  (A3S/TraceRL) — Redis-backed Service, der Aktionsräume
  restauriert/vorwärts-simuliert/reportet, plus eine Dash-Baumvisualisierung
  für verzweigende Trajektorien. Der Wiederverwendungsziel für den geplanten
  what-if-Vergleich (Schritt 7).
- **[`Tokener`](https://github.com/AI4REALNET/Tokener)** — Director-Ansatz
  (Hybrid CBS+PP, Token-basiert) *und* explizit ein "Co-Learning"-Ansatz:
  "human-in-the-loop learning system", das "transparent adaptation through
  interaction" ermöglicht — der Reuse-Kandidat für Level B (AI lernt vom
  Menschen) im Plan oben.
- **[`T2.3_explaining_action_alternatives`](https://github.com/AI4REALNET/T2.3_explaining_action_alternatives)**
  (D2.3) — Erklärungen von Handlungsalternativen ohne Annahmen über die
  Reward-Gewichte des Operators; verwandt mit der Frage, wie ein Operator-Modell
  (Level B) Präferenzen ableiten könnte.
- **[`hmisurveys`](https://github.com/AI4REALNET/hmisurveys)** (TU Delft) —
  validiertes Survey-Framework für Human-AI-Teaming; relevant, falls die
  Reflexionsfragen irgendwann durch validierte Items ergänzt/ersetzt werden.

*(Volle Liste inkl. `T3.4-with-HMI`, `CDRTrainer`, `RL_agent_failure_forecast`
etc. steht im [`CLAUDE.md`](../../CLAUDE.md) des Repos.)*

---

## Teil 3 — Die Publikationen: worauf das Ganze fußt

Direkt im Code zitiert (`co-learning-reflection.component.ts`) und in den
Referenz-Dokumenten:

- **Kolb, D. A.** — *Experiential Learning* (Lernzyklus). Das Reflection-Panel
  ist explizit **Phase 2** dieses Zyklus: konkrete Erfahrung → **Reflexion** →
  abstrakte Konzeptualisierung → aktives Experimentieren. Die Panel-Markierung
  `title="Kolb experiential learning — reflection phase"` ist kein Zufall.
- **Endsley, M. R. (1995)** — *Situation awareness*, Levels/Types. Grundlage
  für "wann ist genug Kontext da, um sinnvoll zu reflektieren" und für die
  Decision-Making-Level-Einordnung der Sokratischen Fragen.
- **Hamouche et al.** — *"A methodical approach to AI-supported human
  learning"* (AI4REALNET / FHNW). Die konkrete methodische Vorlage für das
  Panel: Kolb-Phase + Endsley-Level, operationalisiert über die
  Supportive-AI-Modi.
- **Waefler et al. (2025)** — Supportive-AI-Support-Modi, aus denen die drei
  im Code verwendeten Modi stammen:
  - **Mirroring [MR]** — dem Operator sein eigenes Verhalten statistisch
    zurückspiegeln (die vier Recap-Zahlen).
  - **Animation [AM]** — sokratische, anregende Fragen.
  - **Transparency [TP]** — Fragen, die Verständnis der Situation prüfen/fördern.
- **Sheridan & Verplank (1978); Parasuraman, Sheridan & Wickens (2000)** —
  Levels/Types of Automation. Grundlage der "control altitudes" im
  Director-Teil (§4 im Brief), aber auch relevant für die Frage, *wie viel*
  Reflexion bei *wie viel* Autonomie sinnvoll ist.
- **Lee & See (2004); Parasuraman & Riley (1997)** — Trust Calibration.
  Relevant für die Reflexionsfrage *"Wann hast du der AI vertraut, wann hast
  du sie übersteuert — was hat das getrieben?"* — das ist im Kern eine
  Trust-Calibration-Frage, ins Sokratische übersetzt.
- **Santoni de Sio & van den Hoven (2018)** — Meaningful Human Control;
  **Elish (2019)** — Moral Crumple Zone; **Bainbridge (1983)** — Ironies of
  Automation. Der breitere ethisch-organisationale Rahmen, warum Reflexion
  (statt nur Logging) überhaupt Teil des Designs ist.
- **AI4REALNET Conceptual Framework — arXiv:2504.16133** — die
  "Adjustable Autonomy"-Konzeption, aus der die drei Kontroll-Modalitäten
  stammen, die den drei Modi zugrunde liegen.

Volle Quellenliste mit allen Zuordnungen:
[`docs/reference/interaction-framework.md`](../reference/interaction-framework.md#sources).

---

## Zum Weiterdenken (für die Ferien, ohne Code)

Ein paar offene Fragen, die eher Kopf- als Tastaturarbeit sind:

1. **Level B (AI lernt vom Menschen)** ist laut Plan der "neuartige, noch
   offene Teil". Ist das wirklich der richtige nächste Schwerpunkt — oder ist
   der what-if-Vergleich (Schritt 7) der bessere nächste Schritt, weil er die
   Reflexion *erst vollständig* macht, bevor man beginnt, aus ihr zu lernen?
2. Die fünf Sokratischen Fragen sind aktuell **statisch formuliert** (nur die
   Zahl `n` fließt ein). Würde ein Operator-Modell (Level B) irgendwann auch
   *welche* Fragen gestellt werden beeinflussen — oder bleibt das bewusst
   unveränderlich, damit die Reflexion nicht selbst zum "optimierten" Objekt wird?
3. Der Nudge ("reflect now?") ist bewusst **nicht** ein automatisches Popup —
   `reflectionRequested` bleibt eine explizite menschliche Entscheidung. Ist
   das die richtige Grenze, oder sollte "calm" irgendwann stärker als sanfter
   Zwang statt als Angebot wirken?
4. Die Trust-Calibration-Frage im Panel setzt voraus, dass der Operator seine
   eigenen Trust-Entscheidungen introspektiv benennen kann. Wie viel davon ist
   in der Praxis eher *post-hoc Rationalisierung* als echte Rekonstruktion —
   und ändert das etwas daran, wie ernst man die Antworten als "Lernsignal"
   nehmen sollte (Bezug: Workstream B, `preferenceHypothesis`)?

---

*Verwandt: [`docs/plans/colearning-across-modes.md`](../plans/colearning-across-modes.md),
[`docs/reference/mode-guide.md`](../reference/mode-guide.md),
[`docs/reference/OVERVIEW.md`](../reference/OVERVIEW.md).*
