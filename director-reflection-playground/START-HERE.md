# Demo starten

Prototyp für Director Mode + Reflection. Läuft komplett lokal, ohne Flatland, ohne RL,
ohne LLM. Was er kann und was daran simuliert ist, steht im `README.md`.

## Einmalig

```bash
git fetch origin
git switch roman/director-reflection-playground
cd director-reflection-playground
./start-demo.sh
```

Das Skript legt ein eigenes `.venv` an, installiert Streamlit und Plotly, lässt die
Testsuite als Selbstcheck laufen und startet die App auf <http://localhost:8501>.
Der erste Start dauert ca. eine Minute (Installation), danach wenige Sekunden.

Voraussetzungen: Python 3.10 oder neuer und beim ersten Start eine Netzverbindung für
die beiden Pakete. Zur Laufzeit ist keine Verbindung nötig.

Der Branch enthält auch die Flatland-Director-UI aus
`roman/director-strategies-shift-review`; die startet separat über das `start-demo.sh`
im Wurzelverzeichnis. Die beiden Demos haben nichts gemeinsam außer der Idee.

## Danach

```bash
./start-demo.sh              # http://localhost:8501
./start-demo.sh 8600         # anderer Port, falls 8501 belegt ist
./start-demo.sh 8501 --lan   # auch für andere im selben Netz erreichbar
```

`--lan` bindet auf allen Interfaces. Die App hat keine Authentifizierung, also nur im
vertrauenswürdigen Netz. Eine gehostete Version gibt es nicht; für einen Link von außen
müsste ein Tunnel (`cloudflared`, `ngrok`) davor.

Beenden mit `Ctrl-C` im Terminal.

## Warm starten (für Vorführungen wichtig)

Bei einem Kaltstart kennt die KI dich nicht, also kann sie ihre Empfehlung auch nicht
wegen einer früheren Zusage verschieben — der Kern des Co-Learnings bleibt unsichtbar.
Auf dem Startbildschirm gibt es dafür **„Load prepared profile"**: das schreibt eine
plausible frühere Schicht samt zwei bestätigten Learnings über die normale Mechanik in
die Datenbank. Danach greift im Szenario `Demo (2 min)` an jedem Punkt mit kritischer
Verbindung sichtbar ein Learning („Because you taught me this before …").

Was gespeichert ist, steht auf dem Startbildschirm unter „What the AI stores about
you"; dort lässt sich das Profil auch löschen.

Der Debug view (rohes JSON) ist standardmäßig aus. Bei Bedarf:
`PLAYGROUND_DEBUG=1 ./start-demo.sh` oder `?debug=1` an die URL hängen.

## Durchlauf

Szenario wählen (`Demo (2 min)` für einen kurzen Durchgang, 6 Entscheidungen) → pro
Entscheidungspunkt eine der Strategiekarten wählen → Bestätigungsmodus und optional eine
Begründung angeben → Erwartet gegen Beobachtet vergleichen. Nach der letzten Entscheidung
kommt die Reflection Session: bis zu drei ausgewählte Momente, zu denen der Agent
Lernkandidaten vorschlägt, die du bestätigen, bearbeiten oder ablehnen kannst. Am Ende
steht die Zusammenfassung mit bestätigten Learnings, widersprüchlicher Evidenz und
offenen Fragen.

## Wenn etwas nicht geht

- **Port belegt** (`Address already in use`): mit anderem Port starten, siehe oben.
- **`./start-demo.sh: Permission denied`**: `chmod +x start-demo.sh`.
- **Installation bricht ab**: `rm -rf .venv && ./start-demo.sh`.
- **Zustand zurücksetzen**: `rm -f data/reflection.db`. Sessions, Entscheidungen und
  Learnings liegen dort; die Datei wird beim nächsten Start neu angelegt.

Tests einzeln laufen lassen: `.venv/bin/python -m pytest`
