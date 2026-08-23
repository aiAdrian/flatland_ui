# HMI-Review — Gabys Durchgang durch Recommendation & Co-Learning

*Aufgenommen 2026-08-22. Quelle: Miro-Board „AI4REALNET Workshop 1 Februar",
als PDF exportiert (3 Seiten: Szenario Recommendation, Szenario Co-Learning,
plus ein Zoom-Screenshot der Oberfläche).*

Dieses Dokument hält **das Feedback** und **was wir davon umgesetzt haben**.
Entscheidungen über die grösseren Umbauten gehören in einen Plan unter
`docs/plans/`, nicht hierher.

> **Quellenlage.** Das Board ist als 4495 px breites JPEG eingebettet. Die
> grossen Kommentare und die meisten roten Stickies sind lesbar; ein Teil der
> kleinen gelben Antwort-Stickies ist bei dieser Auflösung nicht mehr
> rekonstruierbar. Wo unten „(sinngemäss)" steht, ist die Lesung unsicher.

---

## 1. Informationsarchitektur / Arbeitsfluss

Der Hauptpunkt, wörtlich:

> „Beim Aufbau wäre zu überlegen, wo der Nutzer die meisten Aktionen ausführt,
> sich orientiert und welche Daten zusammen gesehen werden sollten. […] Die
> Listen sind links und rechts verteilt angeordnet, der Nutzer muss viel
> ‚suchen'. Bei der alten Tunnelautomatik war die Anordnung ähnlich. Sie wurde
> neu konzipiert über die Abbildung der Infrastrukturelemente im oberen Drittel
> vom Bild und über eine Tabelle wurden die konkreten Daten zu den Zügen inkl.
> Handlungsaufforderung im dem unteren Part abgebildet."

> „Jetzt muss sich der Anwender quer über den Screen orientieren. Könnten die
> Daten so gebündelt werden, dass Abhängigkeiten näher zusammen dargestellt
> werden?"

Dazu ein **ausgezeichneter Gegenentwurf** auf Seite 2 des Boards: Karte oben,
Situation Summary, Policy-Vergleichskarten, darunter eine Tabelle mit einer
Zeile pro Zug —

| Status | Zug | Notification | Remaining Steps | Next switch | Aktionen |
|---|---|---|---|---|---|
| moving | 7 | malfunctioning · Arr 124 · −105 · forward only (9,28) | 10 | Hold / Left / Reroute | Forward / Right / Proceed |

— und darunter `AI Plan | My Plan | System Effect` sowie der Impact-Block.

Anschlussideen:

- **Dockable Panels.** „Die Eingabe der Reflektion könnte über ein eigenes
  Fenster dargestellt werden, welches der Anwender frei verschieben kann z.b.
  auf einen neuen Bildschirm." Begriffe, die sie explizit für den Prompt
  mitgibt: *Dockable Windows / Docking Panels*, speziell *Dockable Panels /
  Dock Panels* (Photoshop, VS Code, Blender), *Panes* für Splitscreens.
- **ZWL.** „Warum wird das ZWL ausgeblendet? Das deutet daraufhin, dass hier
  ein Platzhalter für Daten geschaffen wird, der anders besser genutzt werden
  kann." Im Co-Learning-Screen dieselbe Frage schärfer: „Ist es realistisch,
  dass Daten aus dem Betrieb dafür nicht mehr ganz sichtbar sind? Kann es auch
  ein Indiz sein, dass das ZWL unwichtig ist? Was nützen dem Anwender die
  wenigen Infos, welche noch vom ZWL sichtbar sind?"

**Status: offen.** Das ist Umbauarbeit, kein Etikett — siehe §5.

---

## 2. Semantik & Beschriftung

Was Gaby gefragt hat, und was der Code tatsächlich tut:

| Frage | Befund |
|---|---|
| „27% bedeutet die ‚Erfüllungsquote' von dem Vorschlag der KI oder was sagt die Zahl aus?" | **Berechtigt — die Zahl war falsch benannt.** `_confidence()` reichte den gewichteten KPI-Score (`score_branch()`: Ankunftsrate − normierte Verspätung − Deadlock-Strafe) unverändert als „confidence" durch. Er wandert ausserdem mit den KPI-Slidern. |
| „arr 112: erwartetet Ankunftszeit in Minuten?" | Nein: `latest_arrival`, die **späteste planmässige** Ankunft in Simulationsschritten. Keine Prognose, keine Minuten. |
| „−80 = ?" | 80 Schritte **Puffer** bis zur spätesten Ankunft. Das Minuszeichen war als „time remaining" gemeint und las sich als Defizit. |
| „Rot 0 = ?" | Das rote `↻ 0` war die Restdauer einer Störung. |
| „rot = Alarm, gelb = Vorsicht ?" | Richtig geraten — stand nirgends. |
| „FORWARD_ONLY grün, doch nicht vorwärts fahren kann = Forward rot???" | Rot markiert den **bereits gesetzten Eingriff** dieses Disponenten auf diesem Zug (`override_action === opt.action`) — ein Toggle, kein „gesperrt". Nochmal klicken hebt ihn auf. |
| „Done = gelöste Konflikte?" | Nein: am Ziel angekommene Züge. |
| „Alle Züge oder nur die mit Konflikt?" | Alle — es gab keinen Filter. |
| „Was bedeuten die Icons? Sie waren vorher nicht sichtbar." | Layer-Glyphen erschienen ohne Legende. |

Tooltips gab es teilweise, aber nur als native `title`-Attribute — im Workshop
sieht die niemand.

**Status: umgesetzt** (§4).

---

## 3. Arbeitsfluss-Redundanz und Randfragen

- „Die Info über z. B. Zug 5 und Aktionen ‚Forward'/‚Stop' sind an diversen
  Stellen im Screen verteilt. Wie ist hier der Arbeitsfluss gedacht?" ·
  „Kann die Funktion sowohl als auch an diesen zwei Stellen ausgelöst werden?"
  Antwort im Board (gelb): **„Flow müssen wir ausarbeiten."** (sinngemäss)
  → Ja, Karten-Pills und Agents-Liste lösen dasselbe aus. Bewusst so, nirgends
  erklärt. Teil-Entschärfung in der Kartenlegende; der Flow selbst bleibt offen.
- Statuszeile: „sollte der Nutzer aus dieser Zeile auch Infos bemerken können?
  Ich denke sie wird als ‚Fusszeile' eingestuft = lese ich, wenn Zeit ist. Wenn
  die Daten wichtig sind, würde ich sie an einer anderen Stelle, auf eine andere
  Art platzieren."
- „Sieht der beauftragte Disponent nur seine Daten oder auch die von anderen?
  Arbeitet nur ein Disponent in dem Sektor?" (sinngemäss) → **offene
  Konzeptfrage**, betrifft das Studiendesign, nicht nur die UI.
- Scenario-Panel: „Das Szenario wird ohne Bezug auf die betroffenen Zugnummern
  beschrieben. Ist die Info hier nicht relevant?" — Antwort im Board: *globale
  Sicht, verdichtet*.
- What-if Compare: „Hier wird auf Zuglevel eine Info angezeigt? Hat sie einen
  Bezug zu einem den unten aufgeführten Szenarios?" — *muss noch ausgearbeitet
  werden*.
- Impact-Panel: „Was kann hier noch stehen?" — *TBD*.
- Co-Learning: „Wann wird die Reflektion erfasst?"

---

## 4. Was daraufhin umgesetzt wurde (2026-08-22/23)

### Konfidenz ist jetzt eine Konfidenz

Der 27%-Punkt war kein Beschriftungsfehler, sondern ein inhaltlicher. Getrennt
werden jetzt zwei Zahlen, die vorher eine waren:

- **`utilityScore`** — Ergebnisgüte der Option auf der gewichteten KPI-Skala
  (das, was vorher fälschlich „confidence" hiess).
- **`confidence`** — P(Option schlägt den aktuell gefahrenen Kurs), geschätzt
  aus dem **Branch-Ensemble**, das der `ScenarioBuilder` ohnehin rechnet:
  Vorsprung gegenüber der Baseline, gemessen an der Streuung aller Branches,
  durch eine Logistik gedrückt. Gleichstand ⇒ 0.5, ehrlicher Münzwurf.
- **`margin`, `dispersion`, `confidenceBasis`** reisen als Belege mit, damit die
  UI die Zahl *erklären* statt behaupten kann.

Ehrliche Grenzen, die im Code und in der UI benannt sind: jeder Branch ist ein
**einzelner deterministischer Rollout**, die Streuung misst also Uneinigkeit
zwischen Policies, nicht die stochastische Varianz einer Policy. Die Zahl ist
*model-reported*, **nicht kalibriert**. Kalibrierung braucht protokollierte
Entscheidungsausgänge und die Evidential-NN-Arbeit aus
[`widget-a1-risk-uncertainty.md`](../plans/widget-a1-risk-uncertainty.md) §4
(Reuse-Ziel: `AI4REALNET/RL_agent_failure_forecast`).

`backend/app/core/recommendation_generator.py` · `backend/app/models/hmi.py`

### Beschriftung und Legenden

- Recommendations-Panel: Legendenzeile „Score = Ergebnisgüte · Konfidenz = wie
  sicher die KI ist, dass die Option den aktuellen Kurs schlägt"; Konfidenz-Chip
  mit Ampelrand und einer Belegzeile pro Karte („0.70 besser als der aktuelle
  Kurs, die Varianten liegen eng beieinander (Streuung 0.12). Modellwert, nicht
  kalibriert.").
- Event Feed: Farblegende rot / gelb / blau. Dafür neuer Token
  `--app-severity-info` (die bestehenden Severity-Hexwerte in dieser Datei
  wurden bei der Gelegenheit auf Tokens migriert).
- Karte: Legende-Popover in der Layer-Leiste — Zugfarbe, Störungsring,
  Decisions, Weichen, Signale, Stationen, Grid. Nennt ausdrücklich, dass die
  Pills auf der Karte dieselben Aktionen sind wie in der Agents-Liste.
- Agents-Liste: `arr 112` → `Soll-Ank. 112`; `dep` → `Soll-Abf.`;
  `−80` → `noch 80` bzw. `+12 spät`; `↻ 0` → `Störung · noch 0`;
  Gruppen bekommen eine Klartext-Beizeile (`DONE — am Ziel angekommen`).
- Rote Aktionsbuttons: Tooltip „Dein gesetzter Eingriff — nochmal klicken hebt
  ihn auf" plus eine sichtbare Zeile „rot = dein gesetzter Eingriff · nochmal
  klicken hebt ihn auf", wenn eine solche Option angeboten wird.
- Filter **„Nur Konflikte (n)"** über der Agents-Liste. Konflikt = im
  Impact-Ergebnis genannt (blockiert oder blockierend) oder gestört. Die
  Kopfzahl bleibt ungefiltert, damit sie ihre Bedeutung behält.
- Run-Clock „Schritt X / Y" aus der Fusszeile in die Situation Summary geholt.

### Ein Aktionsmodell statt fünf Kopien

Gabys „Kann die Funktion sowohl als auch an diesen zwei Stellen ausgelöst
werden?" hat beim Nachmessen mehr zutage gefördert als vermutet:
`setOverride`/`clearOverride` wurde aus **sechs** Widgets aufgerufen, und der
Toggle-Handler war **viermal kopiert** — der Kommentar im Marey-Chart sagte es
selbst („mirrors left-sidebar.onActionClick"). Drei der sechs hatten ausserdem
ein `kind`, das laut Taxonomie gar nicht schreiben sollte (Karte = Event,
Marey und What-if = Prediction).

Entschieden wurde bewusst **nicht**, die Aktionen dort zu entfernen: der Klick
auf den Zug direkt auf der Karte ist Direktmanipulation am Objekt und im
Leitstand eine Tugend. Stattdessen:

- **`core/dispatch/train-action.service.ts`** ist die einzige Tür zum Handeln an
  einem Zug. Widgets lesen über den Store, handeln aber nur über den Seam —
  damit ist „darf dieses Widget etwas verändern?" eine sichtbare Abhängigkeit
  statt einer Nebenwirkung. Die Toggle-Regel liegt einmal dort.
- **`origin`** (`map | roster | table | inspector | impact | marey | whatif`)
  reist bis in den Decision Log. Damit wird „wie ist der Arbeitsfluss gedacht?"
  messbar statt behauptet — welche Fläche Disponent:innen wirklich benutzen,
  steht danach in den Daten.
- **`writes`** (`none | view | record | simulation`) ist eine neue orthogonale
  Achse in [`interaction-framework.md`](../reference/interaction-framework.md)
  §3, pro Widget im Katalog deklariert und in der Widget Gallery als Pill
  sichtbar. Karte und Marey sind jetzt ausdrücklich als *Control-Ebene auf einem
  Event-/Prediction-Widget* benannt.

**Reichweite, ehrlich:** der Seam deckt Zug-Aktionen ab. Policy-Wechsel,
Run-Control und Director-Weights rufen weiterhin direkt Store/API — als nächste
Seams benannt, nicht stillschweigend als erledigt ausgegeben.

### Nicht geändert, weil kein Fehler

**ZWL/Marey war nie „ausgeblendet".** `LayoutViewToggleService` startet mit
`{ flatlandMap: true, marey: true }`; im Demo-Screenshot war die Marey-Checkbox
schlicht abgewählt und der Zustand aus `localStorage` wiederhergestellt. Die
inhaltliche Frage — *was* das ZWL im Co-Learning zeigen soll — bleibt offen.

---

## 5. Offen, in Reihenfolge

1. **Zug-Tabelle als Widget** nach Gabys Skizze (eine Zeile pro Zug: Status,
   Notification, Remaining Steps, Next Switch, Aktionen) plus ein
   Layout-Preset „Infrastruktur oben / Tabelle unten". Löst §1 und §3
   gemeinsam und bleibt reversibel, weil es ein Layout ist.
2. **Arbeitsfluss festlegen**: wo entscheidet man, wo orientiert man sich, und
   was ist die Rolle der doppelten Aktionsaufrufe.
3. **Scenario/Impact mit Zugnummern** anreichern (oder begründet dabei bleiben,
   dass die globale Sicht verdichtet ist).
4. **Dockable/Floating Panels** — betrifft `panel-shell` und den Layout
   Designer; die mode-scoped Layouts sind laut
   [`mode-scoped-layouts-plan.md`](../plans/mode-scoped-layouts-plan.md) erst
   halb gelandet.
5. **Sektor- und Rollen-Scoping** (ein Disponent oder mehrere?) — Studiendesign.
6. **Kalibrierung der Konfidenz** — erst wenn Entscheidungsausgänge
   protokolliert sind; Reuse-Ziel steht in widget-a1 §4.
