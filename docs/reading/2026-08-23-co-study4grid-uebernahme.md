# Co-Study4Grid — was wir übernehmen können

*Gelesen 2026-08-23. Quelle: [`marota/Co-Study4Grid`](https://github.com/marota/Co-Study4Grid)
(RTE, MPL-2.0, Release 0.9.0) — Repo vollständig gelesen: `docs/features/`,
`docs/architecture/`, `scripts/` inkl. aller CI-Gates, der Game-Mode und die
Recommender-Registry. Demo: [HuggingFace Space](https://huggingface.co/spaces/amarot/Co-Study4Grid).*

Dieses Dokument ist **eine Kandidatenliste mit Begründung**, kein Plan.
Entscheidungen über die grösseren Umbauten gehören in `docs/plans/`.

---

## 0. Warum das Repo für uns relevant ist — und wo die Analogie bricht

Gleiche Familie, andere Domäne: Co-Study4Grid ist eine Contingency-Analyse-HMI
für Stromnetz-Dispatcher, gebaut auf `pypowsybl` + `expert_op4grid_recommender`,
React 19 + FastAPI. Es übernimmt ausdrücklich das **Supportive-AI-Mindset aus
AI4REALNET** („empowering and supporting the user in developing its expertise
rather than automating it") und zitiert dieselben Paper wie unser
[`interaction-framework.md`](../reference/interaction-framework.md) — u. a.
Leyli-abadi/Bessa (arXiv:2504.16133) und Waefler/Hamouche, *The Supportive AI
Framework*.

**Kein Code-Reuse.** Andere Domäne, anderer Stack (React vs. Angular), keine
gemeinsame Bibliothek. Was übertragbar ist, sind **Interaktionsmuster und
Prozess-Disziplin** — und davon überraschend viel, weil dort dieselben
Human-AI-Teaming-Fragen an einer weiter fortgeschrittenen Codebasis
durchgespielt wurden.

**Der strukturelle Unterschied, der bei jedem Punkt unten mitzudenken ist:**
Co-Study4Grid kennt **keine laufende Zeit**. Ein Netzzustand, eine Abschaltung,
dann beliebig lange Exploration — der Operator kann eine Stunde in der
Kombinations-Modale sitzen, ohne dass sich die Welt bewegt. Bei uns läuft die
Simulation. Alles, was dort „der Operator hat Zeit zu vergleichen" voraussetzt,
braucht bei uns entweder eine Pause
([`localized-blocking-decisions.md`](../plans/localized-blocking-decisions.md))
oder eine Ruhephase (`isCalm`, Brief §3.2). Das ist kein Hindernis, aber es
verschiebt die Kosten jedes Musters.

### Schnellübersicht

| # | Muster dort | Unser Ort |
|---|---|---|
| A1 | „Make a first guess" + `origin`-Provenienz | Co-Learning §3.3, Widget B1 |
| A2 | Zweistufige Analyse, Mensch steckt das Ziel ab | Impact-Panel, `/hmi/impact` |
| A3 | `target_max_rho` neben `max_rho` | Widget B1 §8 („local action → global effect") |
| A4 | Schätzung neben Wahrheit, nebeneinander | Konfidenz-Kalibrierung (Workshop §5.6, Widget A1 §4) |
| A5 | „Clear" — KI-Vorschläge weg, eigene Arbeit bleibt | Modusvergleich-Schleife (fehlt) |
| A6 | Modellwechsel ohne Studienneuladen + Signatur-Cache | [`recommender-roadmap.md`](../plans/recommender-roadmap.md) #6 |
| B1–B4 | Log-Disziplin, Provenienz, Fidelity-Gate | [`interaction-logging-plan.md`](../plans/interaction-logging-plan.md) |
| B5 | Game Mode + geteilte Lösungsbasis | [`ecml2026-flatland-env.md`](../plans/ecml2026-flatland-env.md) |
| C1–C6 | Filter-/Gesten-/Severity-Disziplin | HMI-Review-Punkte §1, §2, §3 |
| D1–D6 | CI-Gates | `frontend-lyne-conventions.md`, Docs-Pflege |

---

## A. Für Co-Learning — der eigentliche Ertrag

### A1. „Make a first guess" — die eigene Lösung *vor* der KI

**Dort.** Solange keine Analyse gelaufen ist, zeigt der Action-Feed einen
**💡 Make a first guess**-Shortcut, der die manuelle Aktionsauswahl öffnet. Die
so entstandene Aktion bekommt `origin: "user"` und — der entscheidende Teil —
**überlebt den anschliessenden Analyse-Lauf**: beim Mergen der
Recommender-Menge werden manuell hinzugefügte Aktionen explizit behalten, und
wenn der Recommender dieselbe Aktion vorschlägt, behält sie ihre
Nutzer-Provenienz. Der Shortcut verschwindet, sobald Vorschläge da sind.
Das README rahmt es als *„the UI invites the operator's hypothesis before the
recommender runs"*.

**Bei uns.** Widget B1 (*What-if Compare*) vergleicht bereits „My plan" gegen
„AI plan" — aber der AI-Plan steht dabei schon auf dem Schirm. Das ist
Vergleich **nach** dem Ankern, nicht davor. Die offizielle T3.3-Formulierung
(RP2 Part B, im Brief §7 zitiert) lautet aber: der Operator kann *„formulate
their own solutions **or** choose from AI-recommended solutions"* — das *or*
setzt voraus, dass die eigene Formulierung eine Chance hat, unbeeinflusst zu
entstehen.

**Konkret.** Zwei kleine Dinge, ein grosser Effekt:

1. In Co-Learning bei einem vorhergesagten Konflikt zuerst *nur* das Problem
   zeigen, mit einer Einladung „Was würdest du tun?" — die Optionsliste
   erscheint erst nach einer eigenen Setzung oder einem expliziten
   „Optionen zeigen" (das dann selbst ein protokolliertes Ereignis ist).
2. Jede Option/Aktion trägt `origin: 'user' | '<recommender-id>'`, gesetzt bei
   der Entstehung und **nie durch spätere Interaktion verändert**.

**Warum das die Mühe wert ist.** Es erzeugt genau die Messgrösse, die unserer
Q2/Q3-Frage bisher fehlt: *Stimmte die eigene Hypothese mit dem KI-Vorschlag
überein — und wie hat sich das über die Session verändert?* Ohne die
Reihenfolge-Trennung ist Übereinstimmung nicht interpretierbar, weil Ankern
nicht von Zustimmung unterscheidbar ist. Von allen Mustern in dem Repo ist das
das mit dem höchsten Wert für unsere Studie.

**Aufwand:** S–M, Frontend. Betrifft `recommendations-panel`, `agent-inspector`,
die `optionPresentation`-Weiche und den Decision-Log.

---

### A2. Zweistufige Analyse — der Mensch steckt das Ziel ab, bevor die KI rechnet

**Dort.** `run-analysis-step1` findet nur die Überlastungen. Dann hakt der
Operator an, **welche davon er lösen will** (und darf hypothetische zusätzliche
Abschaltungen ergänzen). Erst `run-analysis-step2` streamt Vorschläge. Ob
abgewählte Probleme trotzdem weiter überwacht wurden, wird als
`monitor_deselected` mitprotokolliert.

**Bei uns.** Störung → Impact-Panel → Recommender. Der Mensch rahmt die Frage
nie; er bekommt eine Antwort auf eine Frage, die die KI selbst gestellt hat.

**Konkret.** Bei einer Störung erst die Impact-Menge zeigen (welche Züge
betroffen, welche Konflikte vorhergesagt), den Disponenten ankreuzen lassen,
*welche* Konflikte er aufgelöst haben will, dann erst die Optionen rechnen.

**Warum.** Drei Dinge auf einmal: es macht die Zielfunktion der KI sichtbar
(statt sie zu unterstellen), es liefert die Bezugsmenge für A3 — und es ist
der Modusunterschied in Reinform. In Recommendation kann die KI die Vorauswahl
vorschlagen, in Co-Learning bleibt sie leer.

**Aufwand:** M, Backend + Frontend. Berührt `/hmi/impact` und den
Interventions-Recommender-Seam.

---

### A3. Zwei Zahlen statt einer: „löst *mein* Problem" vs. „global"

**Dort.** Jede Aktion und jedes Paar wird doppelt bewertet: `max_rho` global,
und `target_max_rho` **beschränkt auf die Leitungen, die der Operator in
Schritt 1 selbst als zu lösen markiert hat**. Beide stehen nebeneinander,
*„so the operator can tell whether a pair actually solves their scenario or
merely shifts the hot spot elsewhere"*.

**Bei uns.** Widget B1 §8 nennt den „local action → global effect"-Lehrpunkt
bereits und hat ihn halb umgesetzt (Zug-Ergebnis primär, System-KPIs
sekundär). Was fehlt, ist die **vom Menschen definierte Zwischenebene**: nicht
„dieser Zug" und nicht „das ganze System", sondern *„die Konflikte, nach denen
ich gefragt habe"*.

Das beantwortet nebenbei Gabys Frage aus dem HMI-Review (§3): *„Hier wird auf
Zuglevel eine Info angezeigt? Hat sie einen Bezug zu einem den unten
aufgeführten Szenarios?"* — mit A2+A3 hat sie einen, und zwar einen vom Nutzer
selbst gesetzten.

**Aufwand:** S, wenn A2 steht. Ohne A2 nicht sinnvoll.

---

### A4. Schätzung neben Wahrheit — die billigste Kalibrier-Affordanz

**Dort.** Zwei Wege zur selben Antwort: eine lineare
Superpositions-**Schätzung** (~gratis) und die **echte Simulation**
(Sekunden). Die *Explore Pairs*-Modale zeigt sie **nebeneinander in zwei
Spalten** — `ESTIMATION | SIMULATION FEEDBACK` —, und die Modale bleibt während
der Simulation offen, „so the user sees feedback". Ein einziges Flag
`is_estimated` trennt die beiden Welten; nur simulierte Paare wandern in den
Haupt-Feed, geschätzte bleiben im Nebenspeicher.

Dazu — und das ist der eigentlich seltene Teil — dokumentieren sie in
`docs/features/combined-actions.md` **mit gemessenen Zahlen, wo die Schätzung
lügt**: die *on-target*-Überlastung wird zuverlässig vorhergesagt, die globale
`max_rho`-Leitung kann zwischen zwei fast gleich belasteten Parallelleitungen
kippen (74 % geschätzt auf der einen vs. 70 % simuliert auf der anderen —
*„not a bug… provably 0 MW in DC"*), und Injektion+Injektion-Paare sind
schwach (5,6 % geschätzt vs. 38,1 % simuliert im Beispielfall). Fazit im
Klartext: *„trust `target_max_rho`; treat the off-target global max as
indicative."* Ein eigenständiges Diagnose-Skript reproduziert den Vergleich.

**Bei uns.** Seit dem 22./23.08. ist die Konfidenz eine echte Konfidenz
(P(Option schlägt aktuellen Kurs), aus dem Branch-Ensemble) — aber sie ist
**model-reported und nicht kalibriert**, und der Workshop-Punkt §5.6
(*„Kalibrierung der Konfidenz — erst wenn Entscheidungsausgänge protokolliert
sind"*) wartet auf die Evidential-NN-Arbeit aus
[`widget-a1-risk-uncertainty.md`](../plans/widget-a1-risk-uncertainty.md) §4.

**Konkret — und das ist der Punkt: es gibt einen billigeren Weg dorthin.**

1. **Prognose neben Ergebnis.** Sobald die Simulation an einem
   Entscheidungspunkt vorbeigelaufen ist, die damals angezeigte Prognose neben
   das tatsächlich eingetretene Ergebnis stellen — dieselbe Zwei-Spalten-Geste.
   Das erzeugt die Kalibrierungsdaten **im normalen Betrieb**, statt sie
   vorauszusetzen. Genau die „protokollierten Entscheidungsausgänge", auf die
   Punkt §5.6 wartet, entstehen dabei als Nebenprodukt.
2. **Die Grenzen des Schätzers publizieren**, mit Zahlen. Bei uns wäre das:
   ein Branch ist *ein* deterministischer Rollout, die Streuung misst
   Uneinigkeit zwischen Policies, nicht Varianz *einer* Policy — das steht
   bereits ehrlich im Code und im Workshop-Doc, gehört aber in die UI und in
   ein reproduzierbares Skript.

**Warum.** Der Operator lernt die Verlässlichkeit der KI **an seinem eigenen
Fall**, statt sie zugesichert zu bekommen. Das ist die stärkste
Trust-Calibration-Affordanz in dem ganzen Repo und trifft Q2 mitten hinein.

**Aufwand:** M. Braucht B1/B3 (Prognose muss protokolliert sein, um sie später
gegen das Ergebnis zu halten).

---

### A5. „Clear" — die KI-Vorschläge wegwerfen, die eigene Arbeit behalten

**Dort.** Unter dem Vorschlags-Header steht kursiv *„Suggestions produced by
**\<Modell\>** in **\<X\>s** ⓘ"* und daneben ein gefährlich eingefärbter
**Clear**-Knopf mit Bestätigung. Er löscht **nur die unangefassten
KI-Vorschläge** — was der Operator markiert, verworfen oder selbst gebaut hat,
bleibt. Er startet **keine** neue Analyse (der Ablauf ist: Clear → ggf. Modell
wechseln → Analyze & Suggest). Und er löscht `active_model`, sodass die
Herkunftszeile verschwindet.

**Bei uns.** Es gibt gar kein Konzept „die Vorschlagsmenge der KI" als
löschbares Objekt. Für den Modusvergleich — dieselbe Situation, anderer Modus
oder andere Policy — fehlt damit jede Hygiene: entweder man behält alten
KI-Output im Bild oder man verliert die eigene Setzung mit.

Für Co-Learning ist die Formulierung noch direkter: *„räum die Optionen der KI
weg, meine eigene formulierte Lösung bleibt stehen"* — das ist die
Aufräum-Geste, die A1 überhaupt erst wiederholbar macht.

**Aufwand:** S, sobald `origin` (A1/B3) existiert.

---

### A6. Modellwechsel ohne Studienneuladen — und der Signatur-Cache darunter

**Dort.** Zwei Endpunkte mit sehr unterschiedlichem Gewicht:
`POST /api/config` lädt die ganze Studie neu (Netz, Aktionskatalog, Reset),
`POST /api/recommender-model` setzt nur zwei Attribute und antwortet mit
`{status, active_model, compute_overflow_graph}`. Dazu wird der teure Teil
(der Overflow-Graph) unter einer **Signatur seiner echten Eingaben** gecacht
— *„because the overflow graph depends only on topology — never on the
recommender — this makes the common 'swap model and re-run' loop
near-instant"*.

Der Vertrag selbst ist bemerkenswert schlank. Ein Modell ist drei
Klassenattribute und zwei Methoden:

```python
class MyPolicy(RecommenderModel):
    name = "ml_policy"                 # Registry-Schlüssel
    label = "ML policy v3"             # UI-Label
    requires_overflow_graph = True     # Capability-Flag

    @classmethod
    def params_spec(cls): ...          # deklarierte Parameter → GET /api/models
    def recommend(self, inputs, params) -> RecommenderOutput: ...
```

Drei Details, die den Unterschied machen:

- **Die Nachbearbeitung gehört der App, nicht dem Modell.** Bewertung,
  Anreicherung, Kartendarstellung laufen automatisch über das, was
  `recommend()` zurückgibt — *„Action cards in the UI look identical to the
  expert's."* Ein fremdes Modell bekommt die volle Oberfläche geschenkt.
- **Registry in der App, Vertrag in der Bibliothek** — begründet: *„the library
  only owns the contract; the registry sits here so this app stays in control
  of which models are offered to operators."*
- **Capability-Flags sperren Bedienelemente, beidseitig durchgesetzt.**
  `requires_overflow_graph` macht aus einer Checkbox eine gesperrte, gesetzte
  Checkbox mit dem Zusatz „required by this model" — und das Backend leitet
  dieselbe Regel unabhängig her, damit ein direkter API-Aufruf sie nicht
  umgeht.

**Bei uns.** [`recommender-roadmap.md`](../plans/recommender-roadmap.md) Punkt 6
(*„Recommender selection (settings / per session)"*) ist genau dieser Endpunkt.
Die zwei Seams (Policy / InterventionRecommender) sind schon da — was fehlt,
ist die **Parameterdeklaration** und die Trennung „teurer Aufbau vs. billiger
Wechsel". Bei uns ist der teure Teil das Branch-Ensemble, das der
`ScenarioBuilder` rechnet — und das ist seit dem Konfidenz-Umbau tragend
geworden. Eine Signatur über seine echten Eingaben (Seed, Schritt,
Agentenzustand, Policy-Menge) würde „Modus wechseln → neu rechnen → vergleichen"
zu einer interaktiven Schleife statt zu einer Wartezeit.

**Ehrliche Einschränkung — nicht 1:1 nachbauen.** Das README behauptet, die
Parameter-Eingaben würden dynamisch aus `params_spec()` gerendert. Der Code tut
das nicht: `SettingsModal` rendert eine **fest verdrahtete Liste** und filtert
sie nur per Namensabgleich. Ein Modell mit einem wirklich neuen Parameter
bekommt ihn in `GET /api/models`, aber kein Eingabefeld. Wenn wir es bauen,
dann sauber aus dem Deskriptor heraus (`kind`/`min`/`max`/`group`).

**Aufwand:** M (Vertrag + Registry-Erweiterung), S für den reinen Wechsel-Endpunkt.

---

## B. Für die Studie und die Datenerfassung

### B1. Start/Complete-Paare, `correlation_id`, `duration_ms`

**Dort.** Jeder Handler, der asynchrone Arbeit anstösst, schreibt **zwei**
Ereignisse mit derselben `correlation_id`:

```ts
interface InteractionLogEntry {
  seq: number;                      // monoton, ordnet auch bei gleichem Zeitstempel
  timestamp: string;                // ISO 8601
  type: InteractionType;            // ~90er String-Union
  details: Record<string, unknown>; // typspezifisch, replay-fähig
  correlation_id?: string;          // verknüpft Start ↔ Abschluss
  duration_ms?: number;             // nur auf *_completed
}
```

Dazu eine **Wartepunkt-Tabelle** im Doc: pro auslösendem Ereignis die
beobachtbare Bedingung, die „die App ist nachgezogen" bedeutet. Und die Regel:
ein `_started` ohne `_completed` heisst *abgebrochen oder fehlgeschlagen* —
ein Abbruch erzeugt bewusst **kein** `_completed` und keinen Fehler-Toast,
sondern einen Info-Toast. *Ein Abbruch darf den Entscheidungsdatensatz nicht
verschmutzen.*

Fünf Prinzipien halten das Log über die Zeit brauchbar; das wichtigste:
**„log what the user did (clicked, selected, toggled), not internal state
changes"** — und zwar *dort, wo die Geste behandelt wird*, nie in einem
nachgelagerten Reducer/Effect. Sie nennen sogar den Refactor, der das erzwang:
Re-Simulations-Ereignisse zogen aus dem Hook in den Feed-Handler um, weil nur
dort die vom Nutzer editierten Zielwerte im Scope sind.

**Bei uns.** `DecisionLogEntry` hat `decisionTimeMs`, aber nichts für
asynchrone Vorgänge — und Prognose/Rollout/Impact-Berechnung *sind*
asynchron. Ohne Korrelations-ID lässt sich später nicht rekonstruieren, welche
Prognose zu welcher Entscheidung gehörte. Das ist die Voraussetzung für A4.

**Aufwand:** S. Additive Erweiterung des bestehenden Schemas.

---

### B2. Die Trennregel: was in den Record gehört und was nur ins Log

**Dort.** Ein eigener Abschnitt „What is NOT persisted" benennt **pro Feld**,
was flüchtig ist und **welches Log-Ereignis es wiederherstellt** —
Karten-Editierzustände, angedockte Fenster, sämtlicher Zustand des
Overflow-Tabs. Die Regel dahinter in einem Satz:

> **Zustand, der ein Analyseergebnis verändert, gehört in die Session;
> Zustand, der reine Ansicht ist, gehört nur ins Log.**

**Bei uns.** [`interaction-logging-plan.md`](../plans/interaction-logging-plan.md)
§6 Entscheidung 4 fragt „nur semantische Ereignisse oder auch UI-Telemetrie?"
und empfiehlt „semantisch". Die Regel oben ist schärfer und beantwortet die
Frage besser: **Gesten werden auf UI-Ebene protokolliert** (also durchaus
Filterklicks und Panel-Wechsel — das ist *„was hat der Operator gesehen, als er
entschied"*), aber **in den Session-Record kommt nur, was ein Ergebnis
verändert**. Kein Hover-Tracking, keine Gaze-Surrogate — die Grenze verläuft
nicht bei „semantisch vs. UI", sondern bei „ergebniswirksam vs. Ansicht".

Das entschärft nebenbei den Fragmentierungs-Befund (§3.5 des Plans, vier
`localStorage`-Namensräume): mit der Regel ist klar, welche der vier überhaupt
in den Record gehören.

**Aufwand:** keiner — eine Entscheidung und eine Tabelle.

---

### B3. Provenienz, die nie mutiert — und „Absicht vs. Wahrheit"

**Dort.** Zwei getrennte Disziplinen, beide für uns relevant:

- **`origin`** (`"user" | "<model id>"`) wird bei der Entstehung gesetzt und
  **nie** durch Markieren, Verwerfen oder Neusimulieren verändert; im
  aufgeklappten Kartenblock erscheint sie als „Source"-Zeile. Das Doc
  kontrastiert sie ausdrücklich mit dem überladenen Interaktionsflag
  `is_manually_simulated`, das auch dann umkippt, wenn der Operator einen
  Vorschlag bloss markiert — eine Warnung aus Erfahrung.
- **`configuration.model` vs. `analysis.active_model`** — „was der Operator
  gewählt hat" gegen „was das Backend tatsächlich ausgeführt hat". Sie können
  auseinanderlaufen (unbekannter Modellname → stiller Fallback), und
  `active_model` ist dokumentiert als **die Wahrheit** darüber, was die Karten
  erzeugt hat.

**Bei uns.** Unsere Definition of Done verlangt ausdrücklich, dass
**Moduswechsel mitten in der Session** sofort wirken (Brief §5). Genau deshalb
ist eine Session mit Moduswechsel heute nicht auswertbar: eine Option, die
unter `recommendation` entstand und unter `co-learning` angewandt wurde,
trägt keine Spur davon.

**Konkret.** Jede Option/Empfehlung und jeder Decision-Log-Eintrag stempelt:
`origin` (wer hat's gedacht), `producedInMode` (unter welchem Modus entstanden),
`producedByPolicy` / `producedByRecommender`. Der Modus im
`SessionHeader` (§4.2 des Plans) bleibt der Startwert; die Stempel sind die
Wahrheit pro Artefakt.

**Aufwand:** S. Und ohne das ist B5/A4/A1 alles nicht auswertbar.

---

### B4. Der Fidelity-Gate — später relevant, aber jetzt billig anzulegen

**Dort.** `scripts/check_session_fidelity.py`: ~35 **von Hand kuratierte**
Felddeskriptoren; für jedes greppt das Skript den Speicher- und den
Wiederherstellungspfad und klassifiziert `ok` / `save_only` (bewusst, wird neu
hergeleitet) / `regression` (gespeichert, nie wiederhergestellt → **FAIL**) /
`restore_only` (→ **FAIL**). ~200 Zeilen Regex, <2 s in CI.

Die Begründung im Docstring ist die interessante Stelle: die Liste ist
**bewusst kuratiert statt aus dem TypeScript-Interface abgeleitet** — *„a field
in the interface is not automatically 'critical'… the author decides whether it
needs reload fidelity and adds it here."* Das Gate existiert, weil genau dieser
Bug **viermal** ausgeliefert wurde (jeweils ein neues Detail-Feld gespeichert,
aber beim Neuladen nie gelesen — die Karten rendern dann einfach leer, ohne
Fehler).

**Bei uns.** Save/Load ist explizit out of scope
([`interaction-logging-plan.md`](../plans/interaction-logging-plan.md) §8). Aber
die **Zusammenstellung des `SessionRecord`** (§4.1) hat dieselbe Bugklasse: ein
Feld, das zu `DecisionLogEntry` hinzukommt und nie im Export landet, fällt in
keinem Test auf und in keinem Review. Solange der Record aus Signalen
*zusammengebaut* wird, ist das ein realer Pfad.

**Aufwand:** S, aber erst sinnvoll, wenn P1 des Logging-Plans steht.

---

### B5. Game Mode und die geteilte Lösungsbasis — spekulativ, aber forschungsstark

Der Game Mode ist deutlich mehr als eine Gamification-Schicht, und mehrere
Teile davon sind für uns interessant:

- **Additiv und inert.** Aktiv nur über `?game=1`; erreicht die Haupt-App über
  **genau drei** bewachte Berührungspunkte, alle über ein Bridge-Singleton
  (*„mirrors `interactionLogger`"*). Die Evaluationsschicht darf das evaluierte
  Werkzeug nicht verändern.
- **Zwillings-Scorer an *einem* Golden Fixture.** Der In-Browser-Scorer (TS)
  und der Codabench-Scorer (Python) sind numerisch identische Zwillinge, beide
  gegen dieselbe handgeschriebene Fixture-Datei getestet — in zwei
  verschiedenen CI-Jobs. Divergenz macht CI rot.
- **Client-Score ist eine Vorschau, der Server leitet die Wahrheit neu her.**
  `--replay` fährt die aufgezeichneten Aktionen erneut gegen das echte Backend
  und **beendet sich mit Fehlercode, wenn eine Studie über die Toleranz hinaus
  abweicht** — Manipulations- und Drift-Alarm in einem.
- **Schwierigkeit durch den Referenz-Löser definiert**, nicht geraten: *easy* =
  eine einzelne vorgeschlagene Aktion reicht, *medium* = erst eine Kombination,
  *hard* = auch die besten geschätzten Kombinationen reichen nicht. Entartete
  Fälle werden „für die Buchhaltung" erfasst, aber aus dem Pool gehalten.
  Herkunft ist verschleiert (Ordner sind Hashes, der Spieler sieht nur
  „Januar — Montagabend"), und die hinterlegte Referenzlösung wird
  **serverseitig entfernt**, bevor irgendetwas den Client erreicht.
- **Die geteilte Lösungsbasis** ist der originellste Teil. Jede behaltene
  Lösung wird in eine gemeinsame Basis geschrieben, mit **magnitudenfreien
  Signaturen**: `redispatch:<gen>`, `ls:<load>`, `switch:<id>=<state>` —
  **ohne** MW- oder Stufenwert. Begründung: *„retuning a known lever is not
  novel, **mobilising a new lever is**."* Ein handgebauter Schaltvorgang und
  eine Katalogaktion signieren identisch, wenn sie dasselbe physische Manöver
  sind. Der Neuheitsbonus (+20 für einen nie gesehenen Hebel, +10 für eine neue
  Kombination bekannter) ist **an Wirksamkeit gekoppelt** und wird **bewusst
  ausserhalb der gerankten Punktzahl gehalten**. Und die Basis wird
  zurückgelesen: die am häufigsten mobilisierten Hebel pro Kontext erscheinen
  Anfängern als *handlungsfähige* Tipps (Einfachklick lokalisiert, Doppelklick
  simuliert).

**Bei uns.** Das Flatland-Vokabular schriebe sich fast von selbst:
`hold:<zug>@<station>`, `reroute:<zug>=<pfad-hash>`, `reorder:<knoten>=<seq>` —
magnitudenfrei heisst hier: *dass* umgeleitet wurde zählt, nicht um wie viele
Sekunden verschoben.

**Ehrlich:** das ist ein grosser Bau und nur dann sinnvoll, wenn ein Benchmark
oder eine Challenge wirklich geplant ist
([`ecml2026-flatland-env.md`](../plans/ecml2026-flatland-env.md)). *Aber*: die
geteilte Lösungsbasis ist unabhängig davon ein echtes Forschungsinstrument —
sie macht aus einer Einzelstudie eine **kollektive Wissensbasis**, und sie
adressiert genau die Sorge aus
[`co-learning-direction.md`](../plans/co-learning-direction.md) („datenhungrig:
ein einzelner Nutzer liefert wenig Signal"), indem sie über Teilnehmer hinweg
aggregiert. Das ist die Lösung für ein Problem, das wir bereits notiert haben.

---

## C. Für die Oberfläche — direkt auf die HMI-Review-Punkte

### C1. Ein Filterobjekt, ein Prädikat, alle Flächen

**Dort.** *Ein* Zustandsobjekt (`ActionOverviewFilters`: Kategorien,
Schwellwert, „Unsimulierte zeigen", Aktionstyp) mit **einem** Default-Literal,
und **allen** Flächen gemeinsam: Seitenleisten-Feed, Pin-Layer auf der Karte,
Score-Tabelle, Kombinations-Tabelle und — via `postMessage` — der eingebettete
Overflow-Viewer. Die Garantie ist strukturell, weil alle durch **ein
gemeinsames Prädikat** laufen. Das Doc sagt die Konsequenz direkt: *„This
lock-step is the reason a card and a pin can never disagree about visibility."*

Zwei ehrliche Details: wenn der Filter Karten versteckt, zeigt der Feed
*„5 actions hidden by the overview filter."* — die Schleife, die ein Filterchip
öffnet, wird auch wieder geschlossen. Und Elemente, die nur wegen eines
Zusammenhangs sichtbar bleiben müssen, werden **gedimmt statt stillschweigend
durchgelassen**, damit niemand glaubt, sie hätten den Filter bestanden.

**Bei uns.** Gabys Hauptpunkt (§1: *„Die Listen sind links und rechts verteilt
angeordnet, der Nutzer muss viel ‚suchen'"* / §3: *„Die Info über z. B. Zug 5
und Aktionen sind an diversen Stellen im Screen verteilt"*) ist nicht nur ein
Layout-Problem. Der zweite Teil ist Kohärenz: Karte, Agents-Liste,
Impact-Panel und Marey müssen **dieselbe Menge** zeigen. Der frisch gebaute
Filter „Nur Konflikte (n)" ist der erste davon — der richtige Moment für die
Struktur ist **bevor** es drei sind, nicht danach.

(Dass die Kopfzahl ungefiltert bleibt, damit sie ihre Bedeutung behält, machen
wir bereits richtig — dieselbe Intuition.)

---

### C2. Gestengrammatik, auf jeder Fläche gleich

**Dort.** Einfachklick = **Vorschau** (Popover am Ort, kein Tabwechsel, keine
Zustandsänderung, 250 ms verzögert und vom Doppelklick abgebrochen).
Doppelklick = **festlegen / hineinzoomen** (auswählen, Diagramm holen, Karte in
die Seitenleiste scrollen — oder, auf einem noch nicht simulierten Element,
*die Simulation starten*). Identisch auf der Netzübersicht, im eingebetteten
Viewer und auf den Feed-Karten.

**Bei uns.** Gabys Frage *„Kann die Funktion sowohl als auch an diesen zwei
Stellen ausgelöst werden?"* wurde im Board mit *„Flow müssen wir ausarbeiten"*
beantwortet. Das hier ist eine mögliche Antwort — und zwar eine, die die
Redundanz **behält**: Kartenpills und Agents-Liste dürfen dasselbe auslösen,
solange die *Grammatik* identisch ist. Verwirrend ist nicht die doppelte
Stelle, sondern dass dieselbe Geste an zwei Stellen Verschiedenes tut.

---

### C3. Severity-Taxonomie mit einem „kein Urteil"-Eimer

**Dort.** Vier Stufen mit bedienerlesbaren Namen — **Solves overload** /
**Low margin** / **Still overloaded** / **Divergent or islanded** — und die
gesamte Einstufung hängt an **einem** vom Operator einstellbaren Schwellwert
(`monitoringFactor`), nicht an drei verstreuten Literalen. Der vierte Eimer ist
*„das Modell konnte mir keine Zahl geben"* — erstklassig, filterbar, sichtbar.

Und: dass der Schwellwert ein Parameter und **kein Literal** ist, ist eine
CI-Invariante — weil hartkodierte 0.9/1.0 genau dann falsch einstufen, wenn der
Operator den Faktor verstellt hat.

**Bei uns.** Zwei Dinge auf einmal. Erstens beantwortet es Gabys Frage
*„rot = Alarm, gelb = Vorsicht?"* („richtig geraten — stand nirgends") nicht
durch eine Legende, sondern indem die Stufen **Namen bekommen**:
*löst den Konflikt* / *knapp* / *weiterhin Konflikt* / **Rollout divergiert
oder Deadlock**.

Zweitens — und das ist der wichtigere Teil — brauchen wir den vierten Eimer.
Heute verschwindet ein fehlgeschlagener oder deadlockender Rollout vermutlich
einfach aus der Anzeige. Das ist genau die Unehrlichkeit, gegen die Widget A1
(„honest uncertainty") gebaut ist: *„ich weiss es nicht"* ist eine Antwort und
gehört sichtbar gemacht, nicht weggefiltert.

---

### C4. Gestaffelte Hinweise statt gestapelter Banner

**Dort.** Fünf gleichzeitige gelbe Warnbanner wurden ersetzt durch: eine
**Pille mit Zähler** im Header, die zu Hinweiskarten aufklappt (jede mit
optionaler Aktion „Einstellungen öffnen" und optionalem Schliessen), plus
**graue Einzeiler direkt unter dem betroffenen Bedienelement**
(„130/150 Leitungen überwacht — Details unter Hinweise."). Dazu ein einziger
Toast-Store mit `severity`, Sticky-Flag, **Deduplizierung** (identische Meldung
frischt auf statt zu stapeln) und `aria-live`.

**Bei uns.** Passt auf Gabys Statuszeilen-Kritik (*„sie wird als ‚Fusszeile'
eingestuft = lese ich, wenn Zeit ist"*): der Einzeiler-am-Ort ist genau das
Gegenmittel — die Information steht dort, wo die Handlung stattfindet, statt am
unteren Rand. Die Run-Clock haben wir schon hochgeholt; das ist dieselbe
Bewegung, systematisiert.

---

### C5. Legende auf jeder Ansicht — als Invariante

Sie rendern die Diagrammlegende auf **jedem** Diagramm-Tab und sichern das mit
einer CI-Invariante ab. Wir haben nach dem Workshop Legenden nachgezogen
(Karten-Popover, Event-Feed-Farben, Konfidenz-Belegzeile). Die Invariante ist
das, was verhindert, dass die nächste neue Ansicht wieder ohne startet.

---

### C6. Bestätigungsdialoge nur, wenn echte Arbeit verloren geht

**Dort.** *Ein* geteilter Dialog mit fünf Typen, und er feuert nur, wenn
`hasAnalysisState()` wahr ist — mit einer **explizit ausgeschriebenen
Definition** von „echte Arbeit". Ausdrücklich **nicht** gezählt: das blosse
Vorhandensein eines N-1-Diagramms, *„selecting a contingency and viewing the
diagram is a lightweight operation that doesn't warrant a confirmation dialog."*

Der zweite Teil ist die eigentliche Lehre: der Dialog greift **am
Festlegungspunkt** ein, nicht am Tastendruck — das Eingabefeld ist eine
Datalist und feuert bei jedem Zeichen; wer dort abfängt, macht Tippen kaputt.

---

## D. Prozess und CI — der unterschätzte, billigste Hebel

### D1. Ceiling vs. Ratchet — die Antwort auf unsere ~1270 Farbliterale

**Dort.** `check_code_quality.py` unterscheidet zwei Arten von Zahl, und die
Unterscheidung ist der ganze Trick:

- **Ceilings** (Verstoss = Fehlschlag): 0 `print(` im Backend, 0 stille
  `except: pass`, 0 `any` / `@ts-ignore`, **0 Hex-Farbliterale ausserhalb der
  Token-Dateien**, Modul ≤1150 Zeilen, Funktion ≤240, Komplexität ≤38.
- **Ratchets** (auf dem heutigen Stand eingefroren; senken willkommen,
  **erhöhen ist eine Regression**): `as unknown as` ≤12, `console.log` ≤25,
  fehlende Rückgabetypen ≤60.

**Bei uns.** Unsere `CLAUDE.md` sagt zu den ~1270 hartkodierten Farben:
*„don't add to them; migrate opportunistically when you touch a file."* Das ist
eine **soziale Regel**, und soziale Regeln erodieren — besonders bei
delegierter Arbeit an andere Agenten. Der Ratchet ist exakt das Werkzeug für
diese Situation: er friert die Zahl bei 1270 ein, jede Migration darf sie
senken, und **jede Erhöhung wird zu einer Sache, die jemand im Review
rechtfertigen muss**. Das ist der Unterschied zwischen einer Absicht und einer
Zusicherung — und es ist die Voraussetzung dafür, dass Dark Mode je ein
Konfigurationsschalter wird.

Dazu der hübscheste Trick des Repos: eine **Meta-Invariante** in einem
*zweiten* Skript prüft, dass die Konstante `FRONTEND_HEX_LITERAL_MAX` immer
noch `0` ist — damit niemand das Gate still lockert, statt den Verstoss zu
beheben.

**Aufwand:** ein halber Tag. Bester Ertrag pro Stunde in der ganzen Liste.

---

### D2. `check_invariants.py` — nutzersichtbare Invarianten mit Bug-Geschichte

**Dort.** Das eigenwilligste Gate. Jede Invariante trägt einen Namen, ein
Regex-Paar (`pattern` + `must_not`) **und eine Prosabeschreibung des
nutzersichtbaren Bugs, den sie verhindert, samt Commit, der ihn ausgeliefert
hat**. Die sechs Bugklassen, die es motiviert haben: visuelle Schwellwerte,
Bedingungen fürs Rendern, Feldsemantik, Reihenfolge automatischer Effekte,
Ladezustands-Hygiene, Render-Performance. Also: *der Code kompiliert, alle
Tests sind grün, und der Operator sieht das Falsche.*

Ehrliche Einschränkung, die sie selbst benennen: Regex auf Quelltext ist ein
**Stolperdraht auf einer kleinen Menge teuer erkaufter Invarianten**, kein
Typsystem.

**Bei uns.** Und hier wird es spezifisch: **unsere Modusunterscheidung ist
genau so eine Invariante.** Die Definition of Done im Brief §5 lautet
sinngemäss „in Co-Learning erscheint kein bevorzugter Vorschlag" — und das ist
heute **nur durch menschliches Review gesichert**. Statisch prüfbar wäre etwa:
*in den Options-Templates darf `isRecommended` / `confidence` / der Countdown
nicht erreichbar sein, ohne durch `optionPresentation` zu laufen.* Das ist
unsere Kernforschungsfrage Q1, und sie hängt momentan an Aufmerksamkeit.

**Aufwand:** S für die ersten drei Invarianten. Sehr hoher Wert.

---

### D3. OpenAPI-Snapshot + einheitlicher Fehler-Envelope

**Dort.** `app.openapi()` wird normalisiert (Framework-Version und Titel
gepinnt, damit ein Upgrade den Snapshot nicht rauschen lässt), rekursiv
sortiert und gegen einen eingecheckten Snapshot gediffed. Drift → Fehler mit
Unified Diff; beabsichtigte Änderung → `--write` + Review des Diffs.

Dazu ein einheitlicher Fehler-Envelope `{detail, code}` mit stabilen Slugs
(`400→BAD_REQUEST`, `409→STUDY_BUSY`), einem eigenen Code für den *einen*
Fehler, auf den das Frontend verzweigt — und **genau einem Leser im Frontend**,
der ~10 verstreute `err?.response?.data?.detail || '…'`-Stellen ersetzt hat.
Nicht gefangene Ausnahmen werden generisch 500, ohne `str(e)` (keine
Serverpfade im Browser).

---

### D4. Docs als geprüftes Artefakt — und die Sache mit den Zeilennummern

**Dort.** `check_docs_tree.py` prüft zweierlei: (A) jeder in Backticks
genannte, verzeichnisqualifizierte Pfad mit Quellcode-Endung muss auf eine
echte Datei zeigen — ausser die Zeile markiert ihn als *removed / former /
renamed / superseded*; (B) **`foo.py:352`-Anker sind verboten** — *„the
convention is a **symbol anchor** — name the function / class instead, which
survives edits."* Begründung: *„the review's own anchors had already rotted by
hundreds of lines."*

**Bei uns.** Genau dieser Verfall ist bei uns schon eingetreten:
[`interaction-logging-plan.md`](../plans/interaction-logging-plan.md) verweist
auf `session.store.ts:1599`, `:1656`, `:1681`, `decision-log.ts:42`,
`app.component.ts:559` — fünf Anker, die beim nächsten Refactor still falsch
werden. Symbolanker (`setOverride`, `systemHold`, `clearOverride`,
`persistSessionSettings`) sagen dasselbe und überleben.

Und die Regel aus unserer `docs/README.md` (*„Every markdown file under `docs/`
is listed here"*) ist selbst maschinell prüfbar — ein `ls` gegen die Indexliste,
zehn Zeilen. Bei einem Docs-Baum dieser Grösse mit mehreren beteiligten Agenten
lohnt sich das.

---

### D5. Pin + wöchentlicher Canary

**Dort.** PR- und Deploy-Installationen pinnen die Upstream-Bibliothek exakt
(`--no-deps`), damit ein fremdes Release keinen unbeteiligten PR rot macht. Ein
**separater wöchentlicher Job** löst den Pin auf „latest" und fährt die
Backend-Suite — *„a red canary = 'bump the pin after checking'"*. Deploy hängt
am Erfolg des Test-Workflows, mit manuellem Auslöser als Rückfallweg.

**Bei uns.** Direkt auf `flatland-rl` übertragbar und genau die Situation aus
[`flatland-43-upgrade.md`](../plans/flatland-43-upgrade.md): 4.2.6 → 4.3.0 hat
fünf echte Fehler und einen Seed-Stabilitäts-Blocker gefunden. Ein Canary hätte
das gemeldet, als es passierte, statt bei einem geplanten Upgrade-Versuch.

---

### D6. CI-Bahnen um langsame Abhängigkeiten

Schnelle Bahn (alle Backend-Tests ohne die Graphviz-Binärabhängigkeit, ~720
Tests in ~15 s, keine Systempaket-Installation), langsame Bahn dahinter
gestaffelt. Die Kommentare halten die gescheiterten Versuche fest: ein
`apt-get update`, das acht Minuten am Azure-Mirror hing, und ein Paket-Cache,
dessen `.deb` mit der `libstdc++` des Runners auseinanderlief. Analog bei den
Browser-Tests: eine **billige Meta-Invarianten-Scheibe** (Konsolenfehler, leere
sichtbare Texte, `undefined`-Lecks — ~1 min) läuft bei jedem PR, *„because the
signal-to-cost ratio is high"*, die volle Suite nachts.

---

## E. Kleinere Muster, ohne eigenen Abschnitt

| Muster | Kern | Für uns |
|---|---|---|
| **Ein NDJSON-Leser** | Ein Async-Generator ersetzte fünf handkopierte Leseschleifen, von denen nur zwei die letzte Zeile leerten | wenn Streaming kommt |
| **Abbrechbare Langläufer** | Frischer `AbortController` pro Lauf; Abbruch ist *Abbruch, kein Fehler* — Info-Toast, kein `_completed` | Rollouts/Prognosen |
| **Zeitaufschlüsselung pro Stufe** | Sechs Zeiten, „in Xs ⓘ" mit Tooltip inkl. Restposten „Other (Netz/Streaming)" | macht die Kosten der KI lesbar; ergänzt `decisionTimeMs` |
| **Defaults für Altfelder, pro Feld begründet** | Jedes nachträglich eingeführte Feld hat einen Fallback, der das **historische Verhalten exakt reproduziert** | sobald Records versioniert sind |
| **Integrations-Checkliste je Querschnittsfeature** | `adding-action-type.md`: Tabelle pro Schicht, endend mit *„§3.5 Die Speichern/Log/Neuladen-Trias — der Teil, den alle vergessen"* | Gegenstück zu `widget-authoring-process.md` — unsere Trias wäre Decision-Log / Context-Event / Export |
| **Performance-Entscheide als Prosa mit Zahlen** | ~24 kurze Notizen, **inklusive verworfener Optionen** (`isolated-nad-worker-rejected.md`) | macht „warum nicht einfach…" billig |
| **Fail-open-Filterkette** | Jede Schicht gibt bei internem Fehler ihre Eingabe unverändert zurück; ein *leeres* Ergebnis einer funktionierenden Schicht bleibt aber leer | Aktionsraum-Einschränkung |

---

## F. Bewusst *nicht* übernehmen

- **Den Replay-Agenten.** Das Doc spezifiziert einen „Replay Agent Contract"
  detailliert — **im Repo existiert er nicht**. Was existiert, ist das
  Umgekehrte: ein handgeschriebenes Playwright-Skript fährt die UI und
  vergleicht das *erzeugte* Log gegen eine goldene Spur. Der Vertrag ist eine
  **Disziplin dafür, was man protokolliert** — und darin liegt sein Wert. Nicht
  als „wir können Sessions abspielen" verkaufen (unsere eigene offene
  Entscheidung §6.5 im Logging-Plan lautet ohnehin richtig: *beschreiben jetzt,
  abspielen später*).
- **`params_spec` als angeblich dynamisches Rendering** — siehe A6, das README
  überzeichnet. Wenn wir es bauen, sauber aus dem Deskriptor.
- **Die „Standalone-Parität"-Hälfte der Gates** ist Altlast eines
  aufgegebenen handgepflegten Mirrors. Für ein frisches Projekt: die Spec-Seite
  nehmen, die Mirror-Seite weglassen.
- **Ihr Backend hält genau eine aktive Studie in Modul-Singletons** — daher „ein
  Spieler pro Instanz". Wir haben mit `SessionManager` bereits das Bessere;
  nicht dorthin zurückfallen.
- **Domäne bleibt Domäne:** Superpositionsphysik, Pin-Ankerauflösung,
  Netzgeometrie. Übertragbar sind die *Formen*, nicht die Inhalte.

---

## G. Vorschlag: erste Welle

Nach Ertrag pro Aufwand, nicht nach Reihenfolge im Text:

1. **A1 + B3** — „eigene Lösung zuerst" plus Provenienz-/Modusstempel. Zusammen
   klein, und sie sind der Co-Learning-Kern, den die Studie braucht. Ohne B3
   ist eine Session mit Moduswechsel nicht auswertbar; ohne A1 ist
   Übereinstimmung nicht von Ankern zu unterscheiden.
2. **C3 + die Modus-Invarianten aus D2** — Severity mit „kein Urteil"-Eimer,
   abgesichert durch statische Prüfungen. Beantwortet direkt zwei
   Workshop-Punkte und sichert Q1 zum ersten Mal maschinell.
3. **D1 Ratchet** — halber Tag, stoppt das Wachsen der Farbschuld heute.
4. **B1 + B2** in den Logging-Plan P1/P2 einarbeiten (Korrelations-IDs, die
   Trennregel als Antwort auf offene Entscheidung 4).
5. **A4** — Prognose neben Ergebnis. Der billige Weg zu Kalibrierungsdaten,
   ohne auf das Evidential-NN zu warten. Braucht 4.
6. **A2 + A3** — grösser, verändert den Impact-Fluss; danach.

**A5 und A6** kommen fast von selbst, sobald A1/B3 stehen. **B5** ist eine
eigene Entscheidung und hängt daran, ob eine Challenge tatsächlich kommt.

---

## H. Quellen

- [`marota/Co-Study4Grid`](https://github.com/marota/Co-Study4Grid) — README,
  `docs/features/` (interaction-logging, save-results, combined-actions,
  action-overview-diagram, interactive-overflow-analysis, game-mode-*,
  sld-topology-edit, state-reset-and-confirmation-dialogs, adding-action-type,
  dark-mode), `docs/architecture/`, `scripts/` (check_code_quality,
  check_invariants, check_session_fidelity, check_openapi_contract,
  check_gesture_sequence, check_docs_tree, PARITY_README, game_mode/)
- [`marota/Expert_op4grid_recommender`](https://github.com/marota/Expert_op4grid_recommender)
  — der `RecommenderModel`-Vertrag
- Demo: [HuggingFace Space `amarot/Co-Study4Grid`](https://huggingface.co/spaces/amarot/Co-Study4Grid)
- Verwandt bei uns: [`interaction-modes-brief.md`](../reference/interaction-modes-brief.md),
  [`interaction-logging-plan.md`](../plans/interaction-logging-plan.md),
  [`widget-catalog.md`](../plans/widget-catalog.md),
  [`colearning-across-modes.md`](../plans/colearning-across-modes.md),
  [`2026-08-22-hmi-review-workshop.md`](2026-08-22-hmi-review-workshop.md)
