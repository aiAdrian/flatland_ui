# Dispatcher-Review — Co-Learning für User Study 2

*Aufgenommen 2026-08-24. Feedback aus Disponenten-Sicht, mit einem Layout-Bild
als Gegenentwurf. Fachliche Rückfragen an **Nerissa** sind als solche markiert.*

Schwesterdokument zum [HMI-Review vom 2026-08-22](2026-08-22-hmi-review-workshop.md).
Wo sich beide überschneiden (ZWL, Fachsprache), ist das unten vermerkt — eine
Sache, die zweimal unabhängig genannt wird, ist keine Geschmacksfrage.

---

## 1. Das Bild: Reduktion, nicht Ergänzung

> „Es braucht nicht alle Informationen, die das Tool bietet."

Der Gegenentwurf ist vor allem eine **Streichliste**. Er zeigt drei Spalten:

- **links** Situation Summary · Notifications · Zugliste
- **Mitte** zwei Tabs: **Streckenspiegel** und **ZWL**
- **rechts** What-if Compare · Reflection

Nicht mehr vorhanden: Agent Inspector, Impact, Scenario, Recommendations. Für
eine Studie ist das der Punkt — die Teilnehmenden sollen *einer*
Entscheidungsfläche gegenüberstehen, nicht sieben.

Weitere Details aus dem Bild, die in der Textliste fehlen:

- Züge tragen **echte Namen**: `IC 301`, `S425`, `S420` — keine Handles.
- Bahnhöfe stehen **benannt auf der Karte** („Railway Station" mit Symbol).
- Meldungen sprechen fachlich: „IC301 hat Verspätung. Geplante Kreuzung
  funktioniert nicht."
- **What-if Compare wird eine KPI-Matrix mit drei Optionen** — Option A
  *human generated*, Optionen B und C *AI generated* — über die Zeilen
  *Local Delay · Global Delay · Energy · Anschlüsse · Action*, mit
  „Confirm Selection" darunter. Notiz auf dem Bild: „Eine Auswahl wird
  automatisch die Impact-Analyse generiert."

---

## 2. Die Punkte, geprüft

| Feedback | Befund |
|---|---|
| „2 von 5 Reflection-Fragen statt alle" | **Bereits so.** `reflectionQuestionLimit` steht im Store und ist auf **2** vorbelegt; im laufenden Layout erscheinen zwei Fragen. |
| „«Agents = Züge» nicht intuitiv" | Zutreffend. Die Panel-Titel sind Entwicklersprache; im Study-2-Preset heisst die Spalte jetzt **Züge**. |
| „Was ist der Unterschied zwischen Agents und Agent Inspector?" | Berechtigt — und durch die neue Dispositionstabelle sind es inzwischen **drei** Zugflächen. Braucht eine Entscheidung, nicht nur eine Umbenennung. |
| „Züge sollten Namen haben" · „Bahnhöfe müssen ersichtlich sein und Namen haben" | Existiert heute nicht: Züge haben nur `handle`, Stationen heissen `S1…S6`. Stationen sind als *Struktur* da (`station_aware_env.py` bewahrt Flatlands City/Station-Gruppierung), aber ohne Namen. Die Namen müssten aus Szenariodaten kommen — `flatland-scenarios` liefert `stations`, `lines`, `timetables`, inklusive **Olten** als reales Netz. |
| „Es ist kein ZWL integriert" | **Zum zweiten Mal genannt** (auch im HMI-Review). Im Bild ist es ein gleichwertiger Tab, kein zuschaltbarer Layer — im Study-2-Preset jetzt so umgesetzt. |
| „Alles auf Deutsch" | Offen. Es gibt einen i18n-Plan (`docs/plans/i18n-strategy.md`); die Tab-Labels sind vorgezogen, der Rest ist eine eigene Aufgabe. |
| „Schieberegler mit Kontrast braucht es nicht" | Offen, klein. |
| „Reflection-Gründe nachträglich korrigierbar" | Offen, klein — und inhaltlich richtig: eine Begründung, die man nicht revidieren kann, misst Bequemlichkeit statt Überzeugung. |
| „Präferenz-Hypothese finde ich super" | Bleibt. |

---

## 3. Die Aktionen — und warum „VMax" nicht einfach ein Label ist

> Nerissa: „Bei «left, right» ist nicht klar, was genau gesteuert wird."
> Beispiele für Aktionen: **VMax · Umleiten · Halten**

Flatlands Aktionsraum hat **genau fünf** Werte
(`backend/app/core/cell_classifier.py`):
`DO_NOTHING · MOVE_LEFT · MOVE_FORWARD · MOVE_RIGHT · STOP_MOVING`.

Damit zerfällt Nerissas Liste in zwei sehr verschiedene Teile:

- **Halten** = `STOP_MOVING`. Existiert. Heisst nur geometrisch statt fachlich.
- **Umleiten** = an der Weiche den anderen Zweig nehmen = `MOVE_LEFT` /
  `MOVE_RIGHT`. Existiert ebenfalls; die Oberfläche zeigt heute die *Richtung*
  statt der *Absicht*.
- **VMax** — **existiert nicht.** Flatland kennt Geschwindigkeits*profile*, die
  pro Zug bei Env-Erstellung feststehen; eine Geschwindigkeitsänderung zur
  Laufzeit ist keine Aktion im Aktionsraum.

### Offene Frage (VMax) — bewusst offen gelassen, 2026-08-24

Bevor wir die Simulation erweitern, braucht es eine Antwort auf: **wie zentral
ist VMax für die Studie?** Drei mögliche Wege, in aufsteigendem Aufwand:

1. **Weglassen.** Halten und Umleiten decken die Konfliktlösung ab, die die
   Studie untersucht. VMax wäre dann eine bewusst nicht modellierte Handlung —
   im Studienmaterial zu benennen, damit Teilnehmende sie nicht suchen.
2. **Als Effekt annähern.** Ein „langsamer fahren" liesse sich als wiederholtes
   Halten annähern. Ehrlich nur, wenn wir es so *nennen* — ein Button „VMax",
   der in Wahrheit stottert, wäre eine Lüge über das Modell.
3. **Env erweitern.** Geschwindigkeit zur Laufzeit veränderbar machen. Greift in
   Policies, Trajektorien, Scenario-Branches und alle Vorhersagen ein — die
   sauberste, aber mit Abstand grösste Variante.

**Nicht** vorgesehen: ein VMax-Button, der nichts tut oder etwas anderes tut,
als er behauptet.

---

## 4. Was daraufhin umgesetzt wurde (2026-08-24)

### Layout-Presets als Repo-Artefakt

Ein Layout konnte bisher nur zwei Formen haben: das eine hardcodierte Default
oder ein Eintrag im `localStorage` eines Browsers. Damit war ein Layout, das
wir tatsächlich untersuchen wollen, nicht überprüfbar — es lebte in einem
Browser, niemand konnte es diffen, und ein Löschen der Site-Daten hätte es
mitgenommen.

`frontend/src/app/core/layout/layout-presets.ts` führt **Presets** ein: dieselbe
Datenstruktur wie ein gespeichertes Design, aber versioniert im Repo und in der
Session-Auswahl als *· Preset* erkennbar. Sie werden **angeboten, nie
automatisch angewandt** — mode-scoped Layouts sind ein eigener, ungebauter
Schritt ([`mode-scoped-layouts-plan.md`](../plans/mode-scoped-layouts-plan.md)).

### Preset „Co-Learning · User Study 2"

Der Aufbau aus dem Bild: Lage links, Streckenspiegel/ZWL als Tabs in der Mitte,
What-if und Reflection rechts. Die Zentrumsansichten heissen jetzt
**Streckenspiegel** und **ZWL** statt „Map" und „Marey" — die Wörter, die die
Disponenten benutzt haben.

### Eine geerbte Lücke, beim Testen aufgefallen

Das Preset heisst „Co-Learning", aber nichts erzwingt den Modus: der
Saved-Layout-Pfad fragt `panel-mode-availability` gar nicht ab. Die Reflection
ist dort auf `['co-learning']` beschränkt und rendert trotzdem, wenn oben
*Recommendation* aktiv ist. Das ist derselbe Bypass, den
`mode-scoped-layouts-plan.md` §1 beschreibt — kein neues Problem der Presets,
aber eines, das sie sichtbar machen. Bis der Resolver existiert, trägt der
**Name** eines Presets seine Modus-Absicht, und man wählt den Modus selbst.

### Die Reflection war nicht platzierbar

Beim Bauen des Layouts kam heraus, dass `co-learning-reflection` **nie im
Plugin-Host registriert** war — genau die Lücke, die `mode-scoped-layouts-plan.md`
§1 benennt. Ein Layout konnte sie also gar nicht enthalten; das Panel meldete
„No plugin component has been mapped for this panel type yet". Sie hat jetzt
wie jedes andere platzierbare Widget einen `embedded`-Modus, ist im Plugin-Host
und in der Designer-Palette registriert.

---

## 5. Offen, in Reihenfolge

1. **Zug- und Bahnhofsnamen** aus Szenariodaten (`flatland-scenarios`; Olten als
   reales Netz). Voraussetzung dafür, dass Meldungen „IC301 hat Verspätung"
   heissen können statt „Train 1 is malfunctioning".
2. **Aktionen fachlich benennen** — Halten / Umleiten statt Stop / Left-Right.
   Klein, sofort machbar, betrifft Liste, Karte, Marey und Tabelle gemeinsam
   (alle gehen durch denselben Dispatch-Seam).
3. **VMax entscheiden** (§3) — mit Nerissa, vor jeder Umsetzung.
4. **What-if als KPI-Matrix** mit drei Optionen. Zwingt uns, die **Anschluss-KPI
   echt zu rechnen**: heute ist `connection` im Recommendations-Panel
   ausdrücklich ein Proxy aus dem `done`-Delta.
5. **Deutsch durchgängig** (i18n-Plan).
6. **Kleinkram:** Kontrast-Regler entfernen · Reflection-Gründe revidierbar ·
   Agents vs. Agent Inspector vs. Dispositionstabelle entwirren.
