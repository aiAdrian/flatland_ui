import { InteractionMode } from '../events/event-types';

/**
 * Widget catalog — the single source of truth for widget metadata.
 *
 * A "widget" is an HMI panel authored per the interaction-framework taxonomy
 * (docs/reference/interaction-framework.md) and the widget-authoring process
 * (docs/reference/widget-authoring-process.md). Until this file existed, the same
 * facts lived scattered across three places that drifted apart:
 *
 *   - the layout-designer palette (type, title, description, kind badge),
 *   - core/layout/panel-mode-availability.ts (availableModes),
 *   - docs/reference/panel-mode-matrix.md + docs/plans/widget-catalog.md
 *     (per-mode behaviour, grounding, status) — prose only, not consumable.
 *
 * This registry consolidates them so the in-app **Widget Gallery**
 * (features/widgets-gallery) can render each widget with its kind, granularity,
 * per-mode behaviour and grounding, and so the `/create-widget` authoring skill
 * has a machine-checkable place to register a new widget. Keep it in sync with
 * the palette and the availability map (the gallery cross-checks and warns).
 */

/** interaction-framework §2 function class. The primary classification of a
 *  widget — its role in the human-AI loop, not its visual form. */
export type WidgetKind =
  | 'event'
  | 'context'
  | 'prediction'
  | 'decision-support'
  | 'control'
  | 'capitalization'
  | 'trust';

/** overview ↔ detail (Shneiderman's mantra); 'overview-detail' = a badge that
 *  expands / drills down. */
export type WidgetGranularity = 'overview' | 'detail' | 'overview-detail';

/** Build status — drives whether the gallery can render a live preview. */
export type WidgetStatus = 'shipped' | 'first-cut' | 'planned';

/** Per-mode behaviour: how the *same* widget behaves in each interaction mode.
 *  A short sentence per mode, or `null` when the widget is not offered in that
 *  mode (see `availableModes`). Grounded in panel-mode-matrix.md. */
export interface WidgetModeBehaviour {
  recommendation: string | null;
  'co-learning': string | null;
  director: string | null;
}

export interface WidgetMeta {
  /** Panel `type` — the key used by panel-plugin-host `@switch`, the palette,
   *  and PanelInstance.type. Empty/absent for not-yet-built (planned) widgets. */
  type: string;
  /** Catalog id where one exists (A1, B1, …), else undefined. */
  catalogId?: string;
  title: string;
  kind: WidgetKind;
  granularity: WidgetGranularity;
  status: WidgetStatus;
  /** One short sentence: what the widget shows/does (palette-length, ≤90 chars). */
  description: string;
  /** One sentence: what the operator can now *do* (the widget-spec "Promise"). */
  promise: string;
  /** Grounding reference — a consortium deliverable, paper, or control-room
   *  practice. Every widget is grounded; no generic-dashboard widgets. */
  grounding: string;
  /** Modes in which the widget type is offered. 'all' = every mode. Mirrors
   *  core/layout/panel-mode-availability.ts (which stays the runtime source). */
  availableModes: InteractionMode[] | 'all';
  /** How behaviour branches per mode. `null` where not offered in that mode. */
  perMode: WidgetModeBehaviour;
  /** Default layout zone, for the gallery preview + palette. */
  defaultZone: 'left' | 'center' | 'right' | 'bottom' | 'floating';
  /** Minimum preview height (px), mirrors the palette. */
  minHeight: number;
  /** Spec / plan doc, relative to repo root, when one exists. */
  spec?: string;
}

/** Presentation metadata per kind: label, the CSS token that colours its badge
 *  (see --app-kind-* in styles.scss), whether it is an AI-novel core capability,
 *  and the question the kind answers. */
export const KIND_META: Record<
  WidgetKind,
  { label: string; token: string; aiNovel: boolean; answers: string; blurb: string }
> = {
  event: {
    label: 'Event',
    token: '--app-kind-event',
    aiNovel: false,
    answers: 'What is happening?',
    blurb: 'Event / Context detection — synthesises what is going on (Hypervision).',
  },
  context: {
    label: 'Context',
    token: '--app-kind-context',
    aiNovel: false,
    answers: 'Why, how bad, whom does it affect?',
    blurb: 'Context Determination — explains and scopes a situation.',
  },
  prediction: {
    label: 'Prediction',
    token: '--app-kind-prediction',
    aiNovel: true,
    answers: 'What happens next / what-if?',
    blurb: 'Anticipation — forecasts future events to enable proactive intervention.',
  },
  'decision-support': {
    label: 'Decision Support',
    token: '--app-kind-decision-support',
    aiNovel: true,
    answers: 'Which option, on what evidence?',
    blurb:
      'Decision Assistance / Evaluative AI — evidence for and against options. ' +
      'Framed by mode: Assessment (neutral) → Co-Learning, Recommendation (ranked) → Recommendation, suppressed → Director.',
  },
  control: {
    label: 'Control',
    token: '--app-kind-control',
    aiNovel: false,
    answers: 'Enact / adjust.',
    blurb: 'Operator Interaction / Mode Selection — the human acts on the system.',
  },
  capitalization: {
    label: 'Capitalization',
    token: '--app-kind-capitalization',
    aiNovel: true,
    answers: 'What do we learn from this?',
    blurb: 'Feedback Integration / Learning — reflection, feedback, decision record.',
  },
  trust: {
    label: 'Trust',
    token: '--app-kind-trust',
    aiNovel: true,
    answers: 'Can I rely on the AI here?',
    blurb:
      'Compliance Monitoring (+ Evaluative AI) — must expose *appropriateness of ' +
      'reliance*, not just a confidence number (Weyer vs. Grote tension).',
  },
};

export const WIDGET_KIND_ORDER: WidgetKind[] = [
  'event',
  'context',
  'prediction',
  'decision-support',
  'control',
  'capitalization',
  'trust',
];

const ALL_MODES: WidgetModeBehaviour = {
  recommendation: 'Same in all modes — no mode-specific branching.',
  'co-learning': 'Same in all modes — no mode-specific branching.',
  director: 'Same in all modes — no mode-specific branching.',
};

/**
 * The catalog. Order within a kind roughly follows overview → detail. Built
 * widgets first (have a `type` + component), then planned candidates from
 * docs/plans/widget-catalog.md (no live preview; shown as spec cards).
 */
export const WIDGET_CATALOG: WidgetMeta[] = [
  // ── Event ────────────────────────────────────────────────────────────────
  {
    type: 'situation-summary',
    title: 'Situation Summary',
    kind: 'event',
    granularity: 'overview',
    status: 'shipped',
    description: 'Headline counts: arrived / active / delayed / malfunctioning trains + progress.',
    promise: 'See the state of the whole network at a glance before drilling in.',
    grounding: 'Hypervision / big-board synthesis (control-room practice).',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'left',
    minHeight: 120,
  },
  {
    type: 'notifications',
    title: 'Notifications',
    kind: 'event',
    granularity: 'overview',
    status: 'shipped',
    description: 'Event feed: notifications with kind, title, message, related train.',
    promise: 'Notice new events (malfunctions, conflicts, arrivals) as they occur.',
    grounding: 'InteractiveAI notification stage (Event → Notification).',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'left',
    minHeight: 140,
  },
  {
    type: 'toggle-view',
    title: 'Track Layout & Timetable',
    kind: 'event',
    granularity: 'overview-detail',
    status: 'shipped',
    description: 'Composite: track map + graphic timetable with view & layer controls.',
    promise: 'Switch between spatial (map) and temporal (Marey) views of the same run.',
    grounding: 'Dispatcher big-board + graphic timetable convention.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'center',
    minHeight: 520,
  },
  {
    type: 'flatland-map',
    title: 'Track Layout (Map)',
    kind: 'event',
    granularity: 'overview-detail',
    status: 'shipped',
    description: 'SVG network map: rails, trains, trajectories, switches, signals, decisions.',
    promise: 'Read the network spatially and select trains / decision points.',
    grounding: 'Flatland-RL network topology; control-room track diagram.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'center',
    minHeight: 320,
  },

  // ── Context ──────────────────────────────────────────────────────────────
  {
    type: 'agents',
    title: 'Trains',
    kind: 'context',
    granularity: 'overview',
    status: 'shipped',
    description: 'Train roster grouped by state: position, arrival, deadline, actions.',
    promise: 'Scan every train by state and jump to the one that needs attention.',
    grounding: 'Rolling-stock roster (control-room practice).',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'left',
    minHeight: 180,
  },
  {
    type: 'agent-inspector',
    title: 'Agent Inspector',
    kind: 'context',
    granularity: 'detail',
    status: 'shipped',
    description: 'Train detail: position, destination, delay, malfunction, override actions.',
    promise: 'Understand one train in depth and act on it (details-on-demand).',
    grounding: 'Detail-in-context / Train Detail Overlay (Shneiderman drill-down).',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'right',
    minHeight: 180,
  },
  {
    type: 'impact',
    catalogId: 'impact',
    title: 'Impact',
    kind: 'context',
    granularity: 'detail',
    status: 'shipped',
    description: 'Trains blocked by a malfunction: ETA, severity, options, what-if hover.',
    promise: 'See who a disruption blocks and weigh the response before deciding.',
    grounding: 'Reference mode-aware component (impact-panel.component.ts).',
    availableModes: 'all',
    perMode: {
      recommendation:
        'Surfaces the AI recommended action; keeps the gentle global pause + decision countdown so the human decides *with* a suggestion.',
      'co-learning':
        'Affected trains shown **neutrally**; the human inspects and decides. Empty-state handled explicitly.',
      director: '**Overview only** — per-decision hooks suppressed because the AI handles it.',
    },
    defaultZone: 'right',
    minHeight: 160,
  },
  {
    type: 'goal-achievement',
    title: 'Goal Achievement',
    kind: 'context',
    granularity: 'overview',
    status: 'shipped',
    description: 'Progress toward the operational goal with status badge & progress bar.',
    promise: 'Track how close the run is to the directive / operational goal.',
    grounding: 'Director supervisory goal readout (WP 3.4).',
    availableModes: ['director'],
    perMode: {
      recommendation: null,
      'co-learning': null,
      director: 'The supervisory goal readout — progress against the standing directive.',
    },
    defaultZone: 'right',
    minHeight: 140,
  },

  // ── Prediction ───────────────────────────────────────────────────────────
  {
    type: 'marey',
    title: 'Graphic Timetable',
    kind: 'prediction',
    granularity: 'overview-detail',
    status: 'shipped',
    description: 'Time-distance train-movement diagram (graphic timetable / Marey).',
    promise: 'Read train movements over time and spot crossing / conflict structure.',
    grounding: 'Marey time-distance diagram; central to §3.3 dual-path (marey-rethink).',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'center',
    minHeight: 260,
  },
  {
    catalogId: 'B1',
    type: '',
    title: 'What-if Branch Compare ("A3S-light")',
    kind: 'prediction',
    granularity: 'detail',
    status: 'planned',
    description: 'Branch a decision point: AI plan vs override, simulate both, compare KPI deltas.',
    promise: 'Try a decision both ways and compare the futures before committing.',
    grounding:
      'AI4REALNET/agent-as-a-service-trace-rl (A3S) — Flatland-configured; reuse restore/simulate/action-space. Human steps blue, AI-simulated yellow.',
    availableModes: 'all',
    perMode: {
      recommendation: 'Compare the recommended plan against an operator override side-by-side.',
      'co-learning': 'The dual-path core (§3.3): formulate-own vs AI plan, both simulated forward.',
      director: 'Supervisory what-if — inspect a branch without taking per-step control.',
    },
    defaultZone: 'right',
    minHeight: 200,
    spec: 'docs/plans/widget-catalog.md',
  },
  {
    catalogId: 'B2',
    type: '',
    title: 'Conflict-aware Marey (ribbons + predicted lines)',
    kind: 'prediction',
    granularity: 'overview-detail',
    status: 'planned',
    description: 'Marey with conflict ribbons, predicted trajectories, plan-vs-actual.',
    promise: 'See predicted conflicts on the timetable, not just current positions.',
    grounding: 'UIX top cross-model bet (6/6); central to §3.3. From-scratch UI build.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'center',
    minHeight: 260,
    spec: 'docs/plans/widget-catalog.md',
  },
  {
    catalogId: 'B3',
    type: '',
    title: 'Network Correlation Graph',
    kind: 'context',
    granularity: 'overview-detail',
    status: 'planned',
    description: 'Force-directed graph: severity-coloured node circles, correlation-weighted edges.',
    promise: 'See what else a problem touches by proximity/edge-weight, not by scanning the map.',
    grounding:
      'AI4REALNET/InteractiveAI Graph.vue (D3 force graph, criticality-coloured circles) — Railway is a built-in use case, not analogy.',
    availableModes: 'all',
    perMode: {
      recommendation: 'AI-flagged conflict highlights its node + affected neighbours (focused path).',
      'co-learning': 'Neutral exploration — pick any node, see its correlation neighbourhood.',
      director: 'Aggregate read-only operating picture; a new HIGH node is the exception cue.',
    },
    defaultZone: 'center',
    minHeight: 260,
    spec: 'docs/plans/widget-b3-network-correlation-graph.md',
  },

  // ── Decision Support ─────────────────────────────────────────────────────
  {
    type: 'scenario',
    title: 'Scenario',
    kind: 'decision-support',
    granularity: 'overview',
    status: 'shipped',
    description: 'Scenario cards compared by KPIs (done / deadlock / delay) with policy switch.',
    promise: 'Compare candidate scenarios/policies by KPI and pick one.',
    grounding: 'Scenario-panel per-scenario KPIs; T3.2 policy-ensemble framing.',
    availableModes: 'all',
    perMode: {
      recommendation: 'Alternatives **ranked by the operator’s KPI priorities** (`optionPresentation === recommended`).',
      'co-learning': 'Options presented **neutrally**, no KPI-score ranking.',
      director: 'Neutral framing, and the panel is **expanded by default** (policy is the directive).',
    },
    defaultZone: 'right',
    minHeight: 160,
  },
  {
    type: 'recommendations',
    title: 'Recommendations',
    kind: 'decision-support',
    granularity: 'overview',
    status: 'shipped',
    description: 'AI recommendations: confidence, countdown, accept/reject, route preview.',
    promise: 'Act on a ranked AI suggestion — accept or reject with a reason.',
    grounding:
      'Decision Assistance, Recommendation framing (advisory under Human-in-Control). The signature surface of Recommendation mode.',
    availableModes: ['recommendation'],
    perMode: {
      recommendation: 'The signature surface — ranked suggestion + confidence + accept/reject with countdown.',
      'co-learning': null,
      director: null,
    },
    defaultZone: 'right',
    minHeight: 160,
  },
  {
    catalogId: 'C1',
    type: '',
    title: 'Trade-off Frontier / Scenario Small-multiples',
    kind: 'decision-support',
    granularity: 'overview',
    status: 'planned',
    description: 'Scenario alternatives over 2 KPI axes (Pareto), small-multiple previews.',
    promise: 'Pick by situational priority instead of trusting one ranked list.',
    grounding:
      'AI4REALNET/T2.3_explaining_action_alternatives (D2.3) — expected-outcome per option, no assumed reward weights. Pareto half: Grid2Op_MORL (domain caveat).',
    availableModes: 'all',
    perMode: {
      recommendation: 'Ranked — the frontier collapses to the recommended point (Recommendation framing).',
      'co-learning': 'Assessment framing — evidence for/against each option, no single winner.',
      director: 'Read-only trade-off context behind the standing policy.',
    },
    defaultZone: 'right',
    minHeight: 200,
    spec: 'docs/plans/widget-catalog.md',
  },
  {
    catalogId: 'C2',
    type: '',
    title: 'Triage’d Event Feed (act-now sorting)',
    kind: 'event',
    granularity: 'overview',
    status: 'planned',
    description: 'Notifications sorted by required action time (not chronology); lead-time bars.',
    promise: 'Work the events that need action soonest first, not the newest first.',
    grounding: 'EEMUA 191 alarm-management practice (external, not a consortium artefact).',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'left',
    minHeight: 160,
    spec: 'docs/plans/widget-catalog.md',
  },

  // ── Control ──────────────────────────────────────────────────────────────
  {
    type: 'toolbar',
    title: 'Toolbar',
    kind: 'control',
    granularity: 'overview',
    status: 'shipped',
    description: 'Play / pause, speed, step, policy selector, demo finish controls.',
    promise: 'Drive the simulation clock and pick the active policy.',
    grounding: 'Operator Interaction — the primary actuation surface.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'bottom',
    minHeight: 74,
  },
  {
    type: 'kpi-filter',
    title: 'KPI Filter',
    kind: 'control',
    granularity: 'overview',
    status: 'shipped',
    description: 'KPI weight sliders (time / energy / platform / routing) as dot meters.',
    promise: 'Express which KPIs matter, shaping how options are ranked.',
    grounding: 'Operator priority elicitation; the Director directive lever.',
    availableModes: 'all',
    perMode: {
      recommendation: 'Available but secondary — tunes ranking of recommendations.',
      'co-learning': 'Available but secondary — tunes what the operator compares.',
      director: 'The **primary directive lever** — **expanded** on entering Director.',
    },
    defaultZone: 'left',
    minHeight: 160,
  },
  {
    type: 'layer-visibility',
    title: 'Layer Visibility',
    kind: 'control',
    granularity: 'overview',
    status: 'shipped',
    description: 'Toggle map layers: grid, decisions, trajectory, switches, signals.',
    promise: 'Declutter the map by showing only the layers you need.',
    grounding: 'Map layer control (visualisation ergonomics).',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'left',
    minHeight: 80,
  },
  {
    type: 'director-directive',
    title: 'Director Directive',
    kind: 'control',
    granularity: 'overview',
    status: 'shipped',
    description: 'Set the high-level directive the AI runs on autonomously (WP 3.4).',
    promise: 'Delegate to the AI by stating a goal instead of per-step moves.',
    grounding:
      'AI4REALNET/T3.4-with-HMI, Tokener (token-based directives). Signature surface of Director mode.',
    availableModes: ['director'],
    perMode: {
      recommendation: null,
      'co-learning': null,
      director: 'State the standing directive; the AI acts under it while the human supervises.',
    },
    defaultZone: 'right',
    minHeight: 160,
  },
  {
    catalogId: 'D1',
    type: '',
    title: 'Autonomy Dial / Allocation Panel',
    kind: 'control',
    granularity: 'overview',
    status: 'planned',
    description: 'Shows current allocation {loop-stage → human/ai/shared}; Director autonomy dial.',
    promise: 'See — and later adjust — who owns which stage of the loop right now.',
    grounding:
      'AI4REALNET/T3.4-with-HMI, Tokener, T3.3-3.4-HMI. Display-only first (derived from mode), runtime dial later (framework §5a).',
    availableModes: 'all',
    perMode: {
      recommendation: 'Display: human owns actuation, AI advises.',
      'co-learning': 'Display: human owns actuation + reflection, AI offers neutral options.',
      director: 'The dial: autonomous-recommendation → supervised → override-only → simulation-only.',
    },
    defaultZone: 'left',
    minHeight: 140,
    spec: 'docs/plans/widget-catalog.md',
  },

  // ── Capitalization ───────────────────────────────────────────────────────
  {
    type: 'decision-log',
    catalogId: 'A2',
    title: 'Decision Log & Accountability Strip',
    kind: 'capitalization',
    granularity: 'detail',
    status: 'first-cut',
    description: 'Session decision strip: who decided, when, dwell, accept vs. override.',
    promise: 'Review the session as owned decisions and export them (accountability).',
    grounding:
      'Owner’s accountability line (Boos 2013) + D3.1. Maps to WP4 KPIs (HS-003, AS-005, HS-023, RS-091..096).',
    availableModes: 'all',
    perMode: {
      recommendation: 'Each entry shows the AI suggestion alongside what the human chose (accept vs override is the point).',
      'co-learning': 'Entries show the human’s chosen option neutrally; feeds the reflection prompt.',
      director: 'Mostly AI auto-decisions (owner = AI); operator entries are the rarer **exception interventions** — the strip surfaces the asymmetry.',
    },
    defaultZone: 'right',
    minHeight: 160,
    spec: 'docs/plans/widget-a2-decision-log.md',
  },
  {
    type: 'co-learning-reflection',
    title: 'Co-Learning Reflection',
    kind: 'capitalization',
    granularity: 'detail',
    status: 'shipped',
    description: 'Post-run statistical + open-question reflection on the operator’s choices.',
    promise: 'Reflect on what you decided and why, to learn across runs.',
    grounding:
      'AI4REALNET FHNW Co-Learning HMI (T3.3) — statistical + open-question reflection. Signature surface of Co-Learning mode.',
    availableModes: ['co-learning'],
    perMode: {
      recommendation: null,
      'co-learning': 'The reflection module — compare own vs AI solution, statistical + open-question prompts.',
      director: null,
    },
    defaultZone: 'right',
    minHeight: 200,
  },

  // ── Trust ────────────────────────────────────────────────────────────────
  {
    type: 'risk-uncertainty',
    catalogId: 'A1',
    title: 'Risk & Uncertainty',
    kind: 'trust',
    granularity: 'overview-detail',
    status: 'first-cut',
    description: 'Reliability, confidence & uncertainty band; Accept/Override with reasons.',
    promise: 'Judge whether to rely on the AI here, with honest uncertainty shown.',
    grounding:
      'AI4REALNET/RL_agent_failure_forecast (INESC, evidential NN) — epistemic/aleatoric. First cut frontend-only, not calibrated (label: "model-reported confidence").',
    availableModes: 'all',
    perMode: {
      recommendation:
        'Reliability shown **with** the ranked recommendation: confidence + a spread band from scenario score dispersion. Low-and-wide → amber, invites scrutiny.',
      'co-learning':
        'Uncertainty shown **neutrally per option** (Evaluative AI): each scenario gets evidence-for/against/mixed; no single trust-score winner.',
      director:
        '**Aggregate** policy reliability, read-only; a low-confidence aggregate is the **exception trigger** for adjustable autonomy. No accept/override instrumentation.',
    },
    defaultZone: 'right',
    minHeight: 160,
    spec: 'docs/plans/widget-a1-risk-uncertainty.md',
  },
  {
    catalogId: 'A3',
    type: '',
    title: 'AI Track Record / Reliability History',
    kind: 'trust',
    granularity: 'overview',
    status: 'planned',
    description: 'Rolling record: how often AI suggestions were taken/overridden and how each turned out.',
    promise: 'Calibrate reliance against how the AI has actually performed for you.',
    grounding:
      'Owner’s calibration-mirror line + D3.1. Needs outcome attribution per decision → depends on A2. UQ: RL-agent-uncertainty-prediction-module (Conformal), failure_prediction (D2.2).',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'right',
    minHeight: 160,
    spec: 'docs/plans/widget-catalog.md',
  },
  {
    catalogId: 'D2',
    type: '',
    title: 'Partial Non-Control Zones',
    kind: 'trust',
    granularity: 'detail',
    status: 'planned',
    description: 'Explicitly mark what the operator *cannot* influence right now.',
    promise: 'Know the honest boundary of your control — a precondition for fair accountability.',
    grounding:
      'Owner’s own research contribution (Grote, Partial Non-Control). Not in any consortium deliverable — from-scratch, deliberately.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'right',
    minHeight: 140,
    spec: 'docs/plans/widget-catalog.md',
  },
];

/** Widgets grouped by kind, in WIDGET_KIND_ORDER. */
export function widgetsByKind(): Array<{ kind: WidgetKind; widgets: WidgetMeta[] }> {
  return WIDGET_KIND_ORDER.map((kind) => ({
    kind,
    widgets: WIDGET_CATALOG.filter((t) => t.kind === kind),
  })).filter((g) => g.widgets.length > 0);
}

/** Look up a widget by its panel `type`. */
export function widgetByType(type: string): WidgetMeta | undefined {
  return WIDGET_CATALOG.find((t) => t.type === type && t.type !== '');
}

/** True if the widget is offered in the given mode (mirrors isPanelAvailableInMode). */
export function widgetAvailableInMode(widget: WidgetMeta, mode: InteractionMode): boolean {
  return widget.availableModes === 'all' || widget.availableModes.includes(mode);
}
