# Tile A1 — Risk & Uncertainty

> Spec following [tile-authoring-process.md](../reference/tile-authoring-process.md).
> Status: **spec / not built.**

## 1. Identity
- **Name:** Risk & Uncertainty
- **`kind`:** Trust (exposes *appropriateness of reliance*, not just a number)
- **`granularity`:** overview → detail (a per-decision reliability badge that
  expands into "what is uncertain and why")
- **Default zone:** right (next to Recommendation / Conflict)
- **Sources:** AI4REALNET **D3.1** (uncertainty-aware augmentation) + **D3.2**
  (UQ building block) · UI exploration ("honest uncertainty" tile, 4/6+6/6) ·
  owner's accountability line (Trust as double-edged)
- **Grounding:** Lee & See (2004) *appropriate reliance*; epistemic vs. aleatoric
  uncertainty; Grote's caution — *trust may be a consequence of lack of control*.

## 2. Promise
The operator can see **how much to trust each AI output** — a calibrated
reliability signal plus *what* is uncertain (data noise vs. model doubt) — so
that "when do I intervene?" becomes an informed choice rather than a reflex.

## 3. Per-mode behaviour
- **Recommendation:** reliability shown **with** the ranked recommendation
  (confidence + a spread band); low/uncertain reliability visually invites
  scrutiny. Framing = *Recommendation*.
- **Co-Learning:** uncertainty shown **neutrally per option** as evidence for/against
  (Evaluative AI), no single "trust score" winner. Framing = *Assessment*. Feeds
  the reflection prompt ("you overrode a low-confidence suggestion — why?").
- **Director:** **aggregate** reliability of the autonomous policy (supervisory);
  read-only, but a **low-confidence event surfaces for exception handling** —
  the moment adjustable autonomy would hand back control.

## 4. System interaction
Data **in** (available now):

| Signal / endpoint | Field used | Role |
|---|---|---|
| `store.recommendations` / `getRecommendations` | `confidence` | primary reliability, Recommendation mode |
| `store.scenarios` / `getScenarios` | `score`, `kpiDeltas` | **dispersion across alternatives** = uncertainty proxy (ensemble-style) |
| `store.impact` / `getImpact` | `ImpactOption.delta` | per-option consequence spread |
| `api.whatIfOverride` | `summary` | consequence preview on hover (already used by impact panel) |

Actions **out:** none that mutate sim state (informational). May set
`selectedHandle` on drill-down. **Emits a reliance signal** when the operator
accepts/overrides *in the presence of a shown reliability* → for accountability
logging (§5).

Backend — **to build (flagged extensions, not faked):**

| Need | Why | First cut without it |
|---|---|---|
| Epistemic vs. aleatoric split | D3.2 UQ; "data noise" vs "model out-of-distribution" | show a single calibrated band from confidence + alternative-dispersion |
| Calibration data (reliability vs. actual outcome) | to prove the number is *appropriate*, not decorative | label as "model-reported confidence", not "reliability", until calibrated |

## 5. Allocation & accountability touchpoints
- **Loop stage:** Decide (Trust is the reliance judgement feeding Control).
- **Allocation:** in Rec/Co-Learning the human owns Decide → the tile serves
  *their* reliance calibration; in Director the AI owns Decide → the tile is the
  human's **exception trigger** (supervisory).
- **Decision events emitted:** `{decision, shownReliability, shownUncertainty,
  action: accept|override, decisionTimeMs}` → directly powers the accountability
  signals (override-rate, friction, **decision-time ÷ acceptance-rate overtrust
  proxy**). This is the tile where the owner's Trust-vs-control tension becomes
  *measurable*.
- **Design guardrail (from the framework):** must show **calibration**, not a
  false-comfort confidence number — otherwise it manufactures the overtrust it
  claims to prevent.

## 6. Acceptance scenario
A malfunction blocks a corridor; the AI recommends *reroute* at **confidence
0.62** with a **wide** spread (alternatives disagree). The badge renders amber +
wide band; the operator expands it, sees "alternatives disagree on delay
(±40%)", and overrides to *hold*. **Measurable success:** override rate is
higher when reliability is low-and-wide than when high-and-tight (the signal is
*calibrated* and *acted on*), and the overtrust proxy is captured per decision.

## 7. Effort & changes
- **Effort:** M (~1–2 days; ~frontend-heavy first cut, backend UQ later).
- **Touch:** new `features/risk-uncertainty/`; register in `panel-plugin-host`
  (+`@switch`), `layout-designer` palette, `PANEL_MODE_AVAILABILITY` (all modes,
  behaviour differs), `PanelDefinition.kind='trust'`; add a small
  reliability-derivation helper; `panel-mode-matrix` row. Backend: none for the
  first cut; UQ endpoint is a later extension.

## 8. Open questions / risks
- Which reliability proxy is *honest* without real UQ? Risk of **false
  precision** — mitigated by labelling ("model-reported") until calibrated.
- Does showing uncertainty **reduce overtrust or just add noise**? This is itself
  a study question (cognitive-forcing vs. "feels good" tension).
- Epistemic/aleatoric distinction without overwhelming a busy dispatcher —
  progressive disclosure (overview badge → detail on demand).
