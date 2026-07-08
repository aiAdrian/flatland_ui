# Widget A1 — Risk & Uncertainty

> Spec following [widget-authoring-process.md](../reference/widget-authoring-process.md).
> Status: **first cut built (frontend-only, not calibrated).** See
> `frontend/src/app/features/risk-uncertainty/risk-uncertainty-panel.component.ts`
> and the matrix row in `docs/reference/panel-mode-matrix.md`. Backend UQ /
> calibration remains a flagged extension (§4).

## 1. Identity
- **Name:** Risk & Uncertainty
- **`kind`:** Trust (exposes *appropriateness of reliance*, not just a number)
- **`granularity`:** overview → detail (a per-decision reliability badge that
  expands into "what is uncertain and why")
- **Default zone:** right (next to Recommendation / Conflict)
- **Sources:** AI4REALNET **D3.1** (uncertainty-aware augmentation) + **D3.2**
  (UQ building block) · UI exploration ("honest uncertainty" widget, 4/6+6/6) ·
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

Backend — **to build (flagged extensions, not faked). Per CLAUDE.md's
"reuse, don't reinvent" rule, the UQ reuse target is AI4REALNET's own UQ
building block — [`AI4REALNET/RL_agent_failure_forecast`](https://github.com/AI4REALNET/RL_agent_failure_forecast)
(INESC, D3.2) — not a from-scratch build. A from-scratch UQ would need an
explicit, stated decision, not the default.**

Concrete AI4REALNET UQ vocabulary to align our backend fields with (from
`RL_agent_failure_forecast/src/enn_models.py` + `rule_predictor.py`):

| Need | Why | AI4REALNET reuse target (exact identifiers) | First cut without it |
|---|---|---|---|
| Epistemic vs. aleatoric split | "data noise" vs "model out-of-distribution" | `EvidentialNetwork.forward()` → `{alpha, evidence, S, prob, uncertainty}`; **epistemic = vacuity = `num_classes / sum_alpha`**; aleatoric = forecast-residual variance (`aleatoric_load_p_mean`, `aleatoric_gen_p_mean`) | show a single calibrated band from confidence + alternative-dispersion |
| "What is uncertain & why" NL layer | the detail drill-down's reason lines | `translate_rule_to_sentence(rule_code, line_name)` (Dual-LLM Generator-Evaluator → symbolic rule → sentence) | hand-written reason strings from dispersion/score |
| Calibration data (reliability vs. actual outcome) | to prove the number is *appropriate*, not decorative | the repo's failure-prediction classifier (probability of agent failure under contingency) | label as "model-reported confidence", not "reliability", until calibrated |

**Domain divergence (note in the PR):** `RL_agent_failure_forecast` targets
power grids (Grid2Op / l2rpn_icaps_2021_small), not railways. It is a
**semantic alignment** — same UQ vocabulary and split — not a drop-in library.
The Flatland backend would host an equivalent Evidential NN over *our* agent's
action space. A3S (EnliteAI/TraceRL, T3.1) is the reuse target for Widget **B1**
(what-if branch compare), not A1's UQ.

## 5. Allocation & accountability touchpoints
- **Loop stage:** Decide (Trust is the reliance judgement feeding Control).
- **Allocation:** in Rec/Co-Learning the human owns Decide → the widget serves
  *their* reliance calibration; in Director the AI owns Decide → the widget is the
  human's **exception trigger** (supervisory).
- **Decision events emitted:** `{decision, shownReliability, shownUncertainty,
  action: accept|override, decisionTimeMs}` → directly powers the accountability
  signals (override-rate, friction, **decision-time ÷ acceptance-rate overtrust
  proxy**). This is the widget where the owner's Trust-vs-control tension becomes
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
