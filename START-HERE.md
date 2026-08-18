# Demo starten

Ein Befehl, aus diesem Ordner:

```bash
./start-demo.sh
```

Dann **http://127.0.0.1:8000** öffnen → *New Session* → oben *Director*.

Weitere Varianten:

```bash
./start-demo.sh 8080                # anderer Port
./start-demo.sh 8000 --lan          # auch im lokalen Netz erreichbar
./start-demo.sh 8000 "" --rebuild   # Frontend neu bauen (nach Code-Änderungen)
```

Das Skript ist idempotent: es richtet ein, was fehlt, überspringt was da ist, und
startet dann den Server. Ein warmer Start dauert Sekunden, ein kalter baut das
Frontend und installiert die Python-Abhängigkeiten.

## Ablauf im Director Mode (und die Wartezeiten)

Der Planer ist echt, und Planen kostet Zeit. Gemessen auf dem Demo-Environment:

| Schritt | Dauer | Was passiert |
|---|---|---|
| Director öffnen (pausiert) | ~10 s | Erstplan wird erstellt |
| direkt danach | ~20 s | drei Strategiepläne (A/B/C) auf Kopien |
| gleiche Lage nochmal | 0 s | aus dem Cache |
| „Übernehmen“ | ~10 s | Neuplanung mit den neuen Zielen |

Während dieser ~30 s sind die Kacheln **nutzbar**: der Trade-off steht da und
„Übernehmen“ geht sofort. Nur „Auf Karte“ braucht den fertigen Plan — der Knopf
sagt per Tooltip, worauf er wartet.

**Während Play wird die Prognose absichtlich nicht gerechnet.** Sie dauert ~20 s,
jeder Simulationsschritt macht sie ungültig, und sie konkurriert mit der
Simulation um CPU. Stattdessen: Zahlen werden als veraltet markiert, und beim
**Pausieren** rechnet die UI automatisch neu. Wer nicht warten will, drückt
„Neu berechnen“ — das erzwingt es auch während der Fahrt.

Empfohlener Demo-Ablauf:

1. *New Session* → *Director* → ~30 s warten, bis A/B/C Zahlen haben
2. *Auf Karte* bei einer Option → gestrichelte Umleitung auf der Karte
   („Vorausschau … noch nicht übernommen“)
3. *Übernehmen* → Karte zeigt „**Aktiver Plan**“, rechts erscheint die
   Reflexionskarte („Als Regel merken / Nur diesmal / Trifft nicht zu“)
4. *Play* → Züge fahren, rechts läuft „Was die KI macht“ mit
5. *Pause* → Prognose rechnet neu, nächste Entscheidung
6. **„Schicht beenden“** (in der Director-Leiste) → der *Schichtabschluss* als
   **eigener Screen** (Karte und Kacheln treten zur Seite): Bilanz, bis zu drei
   Reflexionsmomente mit Grund/Preis/Auswahlbegründung, und was die KI gelernt
   hat. Nicht auf Schritt 400 warten — der Knopf ist der Weg dorthin, und
   „← Zurück zur laufenden Schicht“ (oben rechts) führt zurück, ohne die
   Strategien neu rechnen zu müssen.
7. Im Schichtabschluss **„Präferenzen für die nächste Schicht speichern“** →
   die bewusste Evidenz wandert ins Langzeitprofil.

## Präferenzen über Schichten hinweg

Gespeichert wird serverseitig in `backend/data/operator-profiles.json` — nur die
gezählte Evidenz, die Zahl abgeschlossener Schichten und die *bestätigten*
Regeln. Einzelfälle („nur diesmal“) und passive Zustimmungen bleiben draußen.
Die laufenden Rohsignale werden nicht geschrieben; erst der Klick im
Schichtabschluss macht sie dauerhaft.

Beim nächsten Start markiert Director die passende Kachel („◆ Passt zu deiner
gelernten Präferenz“ mit der Evidenz dahinter). Das ist ein **Vorschlag**: die
Reihenfolge der Kacheln bleibt gleich, und übernommen wird nichts automatisch.

Profil zurücksetzen (kalter Start für die nächste Vorführung):

```bash
curl -X DELETE http://127.0.0.1:8000/operator/operator1
```

Anderer Speicherort oder ganz ohne Persistenz:
`OPERATOR_MODEL_STORE=/pfad/profile.json` bzw. `OPERATOR_MODEL_STORE=` (leer).

## Was dabei passiert

Der FastAPI-Backend liefert das gebaute Angular-Frontend statisch aus
(`backend/static/`) — es gibt also **nur einen Prozess und einen Port**, keinen
separaten Dev-Server.

Drei Dinge, die das Skript prüft und die sonst still schiefgehen:

- **`flatland-rl` und `torch`** installieren sich hier nur gegen das öffentliche
  PyPI (`--index-url https://pypi.org/simple`); der Standard-Index in dieser
  Umgebung führt sie nicht.
- **`torch` ist optional**, aber nur formal: ohne es läuft der Director auf dem
  modellfreien Fallback, und dann liefern die A/B/C-Strategiekacheln keine
  Prognose (keine Achsen-Utilities). Das Skript sagt es, wenn Checkpoints
  vorhanden sind, torch aber fehlt.
- **`backend/models/goal_directed/`** muss `evaluator.ckpt` und
  `connection.ckpt` enthalten, sonst ist die Planquelle
  `avoidance (no models)` statt `search`.

## Nach Code-Änderungen

Das Frontend wird nicht automatisch neu gebaut — der Server liefert den letzten
Build aus. Also entweder mit `--rebuild` starten oder von Hand:

```bash
cd frontend && npx ng build --configuration development
cp -R dist/frontend/browser/. ../backend/static/
```

## Tests

```bash
cd frontend && npx ng test --watch=false --browsers=ChromeHeadless   # braucht CHROME_BIN
cd backend  && .venv-run/bin/python -m pytest tests/ -q
```

## Die andere Demo (ohne Flatland)

Der Streamlit-Prototyp liegt in diesem Repo unter `director-reflection-playground/`
(Branch `roman/director-reflection-playground`) und läuft unabhängig:

```bash
cd director-reflection-playground && ./start-demo.sh    # http://localhost:8501
```

Eigene Anleitung dort in `START-HERE.md`.

Beide können gleichzeitig laufen (Port 8000 und 8501).
