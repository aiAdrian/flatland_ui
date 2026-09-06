# Workshop-Vision — das Brainstorming-Whiteboard

*Aufgenommen 2026-09-06. Quelle: Foto eines Whiteboards aus dem
Workshop-Brainstorming (AI4REALNET-Kontext). Vier Spalten oben — Theme /
Objectives / Entry Points / Expected Outcomes — und darunter eine Bilanz
**Lacking ↔ Achieved**.*

Dieses Dokument hält **fest, was auf dem Board steht**, und ordnet ein, was
davon das Playground schon trägt. Entscheidungen über die Umbauten gehören in
einen Plan unter `docs/plans/`, nicht hierher.

> **Quellenlage.** Handschrift auf einem Foto. Die Struktur und die meisten
> Stichworte sind eindeutig lesbar; wo unten „(unsicher)" steht, ist die Lesung
> nicht gesichert. Datum, Ort und Teilnehmende des Workshops sind auf dem Board
> nicht vermerkt und hier bewusst nicht ergänzt.

---

## 1. Was auf dem Board steht

### Theme (What)

- Co-Learning
- Collective, Interactive **AI-augmented Prototyping**
- Human-AI Collaboration **in high-stake environments**
- Common research ground: *Engineers + Cognitive/HF/HCI scientists + Domain
  Experts*
- darunter, als Klammer über allem: **AI4RealNet**

### Opportunities

- Fast prototyping & Tangibility
- More time allocation: Design & Evals
- Cross-fertilization of industrial domains + collective designs

### Project-wise — die Diagnose

- **Disjoint work**
- **Too distant from operators**

Mit einem Pfeil auf das Gegenmittel: *tangible, testable manipulation*.

### Objectives (Why?)

- Identifying projects / teams / people
- Shared lessons
- Existing promising platforms & concepts → **connect the dots**
- Needs & challenges ahead
- Rethink / redesign collective work with AI
- Visibility / attractivity
- Perspectives on HAI
- **In-session prototyping** (*„inspiration & continuation"*, unsicher)

### Expected Outcomes

**2-Tages-Session.** Perspektive: *participatory design & fast prototyping of
interactions for HAI*.

### Achieved

- Primary vision
- Version of conceptual framework
- Algorithms / agents
- Interactive simulation environments (**reusable**)
- **Version of monolithic interface**
- Connect disciplines
- Eval needs & challenges
- New concepts (Co-Learning …)

### Lacking = Needs

**Design** → interactions · human factors · modules · UIs/workflows ·
methodologies — gespeist aus *AI-boosted integration*

**Validation / Eval** → realistic-enough scenarios · **baseline to
best/current practices** · availability of users · **protocols**: session
execution, capture, analysis

**Prototyping** → short iterations, modular · getting good feedback · open and
joint dev · **making accessible design env to community (feedback by
manipulation)**

---

## 2. Die eine Spannung, die das Board benennt

Sie steht wörtlich da, quer über die beiden unteren Spalten:

> *Achieved:* „Version of **monolithic** interface" — *Lacking:* „**modules**",
> „short iterations, **modular**", „accessible design env to community".

Das ist genau die Achse, auf der dieses Repo seit Monaten arbeitet: Widget
Gallery, Layout Designer, Infrastructure Builder, die geplante
Szenarien-Galerie, die Contribute-Seite. Das Board liefert dafür keine neue
Richtung, sondern die Begründung — und einen Massstab: *feedback by
manipulation.* Etwas ist erst dann modular genug, wenn jemand es in einer
Session anfassen und verändern kann.

---

## 3. Was das Playground davon schon trägt

| Board-Bedarf | Stand im Repo |
|---|---|
| Interactive simulation environments (reusable) | ✓ vorhanden — Presets, Szenen, Fixtures |
| Modules statt monolithischer Oberfläche | ◐ teilweise — Widget Gallery, Layout Designer, Panel-Zonen |
| Realistic-enough scenarios | ◐ geplant — [scenario-infrastructure-gallery.md](../plans/scenario-infrastructure-gallery.md) |
| Baseline to best/current practices | ◐ geplant — Baseline-Lauf pro Setup, §6 desselben Plans |
| Protocols: session execution, capture, analysis | ◐ teilweise — [interaction-logging-plan.md](../plans/interaction-logging-plan.md) |
| Short iterations, modular prototyping | ◐ teilweise — Layouts und Szenen im Browser, Widgets nicht |
| **Accessible design env to community** | **✗ offen für die code-förmigen Bereiche** |
| Availability of users / too distant from operators | ✗ offen — kein Repo-Thema allein |

---

## 4. Der offene Punkt für eine Session

Die Contribute-Seite (`/contribute`, Commit `01d7c12`) benennt die Grenze
selbst: **Widgets, Algorithmen und Surveys brauchen ein geklontes Repo und eine
Dev-Umgebung**, weil sie Code sind. Szenarien, Infrastruktur und Layouts gehen
im Browser.

Für eine partizipative 2-Tages-Session heisst das: drei von sechs
Beitragswegen sind für die Teilnehmenden zu — und ausgerechnet die drei, auf
denen „interactions", „UIs/workflows" und die Eval-Instrumente liegen. Das ist
der Punkt, an dem „in-session prototyping" und „feedback by manipulation"
heute scheitern würden.

Offene Fragen, die ein Plan beantworten müsste:

1. Was genau muss eine Teilnehmerin in einer Session verändern können — ein
   Widget *auswählen und anordnen* (geht schon), *konfigurieren* (teilweise),
   oder *neu bauen* (heute nur mit Repo)?
2. Reicht dafür eine Konfigurationsebene über bestehenden Widgets, oder braucht
   es eine echte Autorenumgebung im Browser?
3. Wie kommt das Ergebnis einer Session zurück ins Repo, so dass es reviewbar
   ist statt in einem Browser zu verbleiben? (Dieselbe Frage stellt der
   Galerie-Plan für lokal gebaute Szenen: „promote to fixture".)
4. Was von den Eval-Bedürfnissen — Protokolle für Session-Execution, Capture,
   Analyse — muss vor einer Session stehen, damit sie überhaupt auswertbar ist?
