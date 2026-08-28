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

/** Where a widget's data comes from — surfaced so a study operator can tell,
 *  per widget, whether they are looking at the real Flatland run or a placeholder.
 *  Orthogonal to the guided-demo runtime path (see docs/reference/data-provenance.md):
 *  Demo ≠ Mock — the guided demo runs REAL simulation on a fixed seed with
 *  guaranteed decision moments; mock data is mock in every mode.
 *   - `simulation` — computed from the real Flatland run / real session data.
 *   - `derived`    — frontend-computed proxy from simulation data (not a backend KPI).
 *   - `mock`       — synthesized placeholder, not from the simulation.
 *   - `mixed`      — a combination (e.g. real data + derived proxies, or real
 *                    with a mock fallback).
 *   - `none`       — pure control / UI surface with no data source of its own. */
export type WidgetDataSource = 'simulation' | 'derived' | 'mock' | 'mixed' | 'none';

/** Per-mode behaviour: how the *same* widget behaves in each interaction mode.
 *  A short sentence per mode, or `null` when the widget is not offered in that
 *  mode (see `availableModes`). Grounded in panel-mode-matrix.md. */
export interface WidgetModeBehaviour {
  recommendation: string | null;
  'co-learning': string | null;
  director: string | null;
}

/**
 * What a widget may change — an orthogonal axis, deliberately **not** derived
 * from `kind` (interaction-framework.md §3).
 *
 * The HMI review asked how we stop actions from being available in several
 * places at once. Deriving the answer from `kind` would be wrong: the Flatland
 * map is an Event widget ("what is happening?") whose Decisions layer is a
 * genuine Control affordance, and direct manipulation at the point of interest
 * is a control-room virtue, not an accident. So capability is declared per
 * widget and the action layer is named as what it is.
 *
 * - `none`       — reads only.
 * - `view`       — changes presentation state only (layers, tabs, selection,
 *                  dismissals). Nothing the simulation or the AI sees.
 * - `record`     — writes the session record (decision log, reflection,
 *                  rationale). Capitalization widgets do this by design; it is
 *                  separated from `view` because the audit trail is not decor.
 * - `simulation` — can change what the simulation or the AI does (train
 *                  overrides, policy, run control, KPI weights, mode).
 *
 * Enforcement today covers **train actions**: they all run through
 * `core/dispatch/train-action.service.ts`, so acting on a train is a visible
 * injected dependency rather than a side effect of holding the store. Policy
 * switching, run control and Director weights still call the store/API
 * directly — named here as the next seams, not silently claimed as done.
 */
export type WidgetWrites = 'none' | 'view' | 'record' | 'simulation';

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
  /** What this widget may change (see WidgetWrites). Declared, not inferred. */
  writes: WidgetWrites;
  /** Default layout zone, for the gallery preview + palette. */
  defaultZone: 'left' | 'center' | 'right' | 'bottom' | 'floating';
  /** Minimum preview height (px), mirrors the palette. */
  minHeight: number;
  /** Where the widget's data comes from (real simulation vs mock vs derived).
   *  Shown as a badge in the gallery so provenance is legible. See
   *  docs/reference/data-provenance.md for the per-endpoint grounding. */
  dataSource: WidgetDataSource;
  /** Spec / plan doc, relative to repo root, when one exists. */
  spec?: string;
  /** Variant grouping (docs/plans/widget-variants-versioning.md). Widgets that
   *  share a `role` are alternative implementations of the same functional slot
   *  (e.g. Recommendations v1 vs v2). Absent = a standalone widget (no variants).
   *  `type` stays the concrete implementation key; `role` groups variants. */
  role?: string;
  /** Human label distinguishing this variant within its `role`
   *  (e.g. 'v1 · simple card', 'v2 · scored strategy cards'). */
  variantLabel?: string;
  /** The variant offered by default for its `role`. */
  variantDefault?: boolean;
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

/** Presentation metadata per data source: badge label, colour token, and a
 *  one-line blurb. Distinct from KIND_META — provenance is orthogonal to kind.
 *  Tokens only (styles.scss); see docs/reference/data-provenance.md. */
export const PROVENANCE_META: Record<
  WidgetDataSource,
  { label: string; token: string; blurb: string }
> = {
  simulation: {
    label: 'Simulation',
    token: '--app-positive',
    blurb: 'Real Flatland run / real session data.',
  },
  derived: {
    label: 'Derived',
    token: '--app-kind-decision-support',
    blurb: 'Frontend proxy computed from simulation data (not a backend KPI).',
  },
  mock: {
    label: 'Mock',
    token: '--app-severity-warn',
    blurb: 'Placeholder data, not from the simulation (mock in every mode).',
  },
  mixed: {
    label: 'Mixed',
    token: '--app-kind-prediction',
    blurb: 'Combination — e.g. real data plus derived proxies, or a mock fallback.',
  },
  none: {
    label: 'Control',
    token: '--sbb-color-granite',
    blurb: 'Pure control / UI surface — no data source of its own.',
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
    dataSource: 'simulation',
    kind: 'event',
    granularity: 'overview',
    writes: 'none',
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
    dataSource: 'mock',
    kind: 'event',
    granularity: 'overview',
    writes: 'view',
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
    type: 'ai-activity',
    title: 'AI Activity',
    dataSource: 'simulation',
    kind: 'event',
    granularity: 'overview-detail',
    writes: 'none',
    status: 'shipped',
    description: 'Supervisory feed: what the planner just decided, re-planned, and will do next.',
    promise: 'Follow what the autonomous AI is doing without having to ask it.',
    grounding:
      'Adjustable autonomy (WP 3.4) — supervision needs a channel of its own. Replaces `notifications` in Director, which reports malfunctions, operator overrides and per-train hints; two of those cannot occur under an autonomous planner, so it measured zero entries over 120 steps.',
    availableModes: ['director'],
    perMode: {
      recommendation: null,
      'co-learning': null,
      director:
        'Disruptions (trigger) · committed decisions up to the current step, re-plans with their verdict · scheduled decisions ahead. Planned and past are kept apart so a decision 30 steps out is not announced as having just happened. Carries the plan provenance ("Plan aus: modellgeführte Suche", "10 Optionen geprüft").',
    },
    defaultZone: 'right',
    minHeight: 180,
  },
  {
    type: 'toggle-view',
    title: 'Track Layout & Timetable',
    dataSource: 'simulation',
    kind: 'event',
    granularity: 'overview-detail',
    writes: 'view',
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
    type: 'view-tabs',
    title: 'View Tabs',
    dataSource: 'simulation',
    kind: 'event',
    granularity: 'overview-detail',
    writes: 'simulation',
    status: 'first-cut',
    description: 'One center container, tabbed: Map · Marey · Timetable · Goal Achievement.',
    promise: 'Switch the big center view by tab instead of stacking panels vertically.',
    grounding: 'Control-room single-surface-with-view-tabs convention; see docs/plans/center-view-tabs.md.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'center',
    minHeight: 320,
    spec: 'docs/plans/center-view-tabs.md',
  },
  {
    type: 'flatland-map',
    title: 'Track Layout (Map)',
    dataSource: 'simulation',
    kind: 'event',
    granularity: 'overview-detail',
    writes: 'simulation',
    status: 'shipped',
    description: 'SVG network map: rails, trains, trajectories, switches, signals, decisions.',
    promise: 'Read the network spatially, and act on a train where you see it.',
    grounding:
      'Flatland-RL network topology; control-room track diagram. The Decisions layer is a **control layer on an Event widget** — direct manipulation at the point of interest, declared via `writes` rather than left incidental (interaction-framework.md §3). It has its own visibility toggle, and acts through the shared dispatch seam with origin `map`.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'center',
    minHeight: 320,
  },

  // ── Context ──────────────────────────────────────────────────────────────
  {
    type: 'timetable',
    title: 'Timetable',
    dataSource: 'simulation',
    kind: 'context',
    granularity: 'overview',
    writes: 'view',
    status: 'shipped',
    description: 'Schedule board: train, from→to (shared labels), dep/arr, live position + status.',
    promise: 'Read every train’s route + schedule keyed to the map labels, plus where it is and how it’s doing now.',
    grounding: 'Operator timetable / departure board (control-room practice); tabular counterpart to the Marey graphic timetable.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'left',
    minHeight: 160,
    spec: 'docs/plans/widget-timetable.md',
    role: 'timetable',
    variantLabel: 'v1 · compact board',
    variantDefault: true,
  },
  {
    type: 'agents',
    role: 'agents',
    variantLabel: 'v1 · roster (schmale Spalte)',
    variantDefault: true,
    title: 'Trains',
    dataSource: 'simulation',
    kind: 'context',
    granularity: 'overview',
    writes: 'simulation',
    status: 'shipped',
    description: 'Train roster grouped by state: position, arrival, deadline, actions.',
    promise: 'Scan every train by state and jump to the one that needs attention.',
    grounding: 'Rolling-stock roster (control-room practice).',
    availableModes: ['recommendation', 'co-learning'],
    perMode: {
      recommendation: 'Same in all modes — no mode-specific branching.',
      'co-learning': 'Same in all modes — no mode-specific branching.',
      director:
        'Withdrawn: dispatcher-level detail. Director supervises objectives while the AI owns individual trains, so a per-train table is noise there.',
    },
    defaultZone: 'left',
    minHeight: 180,
  },
  {
    type: 'agents-table',
    role: 'agents',
    variantLabel: 'v2 · Dispositionstabelle',
    title: 'Trains (Dispositionstabelle)',
    dataSource: 'simulation',
    kind: 'context',
    granularity: 'overview-detail',
    writes: 'simulation',
    status: 'first-cut',
    description: 'One row per train: status, message, schedule, next switch and its action.',
    promise: 'Read a train\'s situation and act on it without leaving the row.',
    grounding:
      'The redesigned SBB Tunnelautomatik as reported in the 2026-08 HMI review: infrastructure in the upper third, a per-train table carrying the Handlungsaufforderung below. Replaces a left/right split with the same "der Nutzer muss viel suchen" complaint we had.',
    availableModes: ['recommendation', 'co-learning'],
    perMode: {
      recommendation:
        'The AI recommendation for a train is starred in its row — sourced from the impact analysis, the only place a real per-train recommendation exists. Trains without one show no marking.',
      'co-learning':
        'Options rendered as **equal choices**, no AI-preferred marking: the operator forms their own view first. Their own standing override is still marked as theirs.',
      director:
        'Withdrawn, like the v1 roster: dispatcher-level detail, while Director supervises objectives.',
    },
    defaultZone: 'bottom',
    minHeight: 220,
    spec: 'docs/plans/widget-agents-table.md',
  },
  {
    type: 'agent-inspector',
    title: 'Agent Inspector',
    dataSource: 'simulation',
    kind: 'context',
    granularity: 'detail',
    writes: 'simulation',
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
    dataSource: 'simulation',
    kind: 'context',
    granularity: 'detail',
    writes: 'simulation',
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
    dataSource: 'simulation',
    kind: 'context',
    granularity: 'overview',
    writes: 'none',
    status: 'shipped',
    description: 'Progress toward the operational goal with status badge & progress bar.',
    promise: 'Track how close the run is to the directive / operational goal.',
    grounding: 'Director supervisory goal readout (WP 3.4).',
    availableModes: [],
    perMode: {
      recommendation: null,
      'co-learning': null,
      director:
        'Superseded by `strategy-options` as the central Director surface — the supervisory decision is which objective the plan should pursue, not how far along a standing one is. Offered in no mode (empty ≠ absent), kept wired so re-enabling is a config flip.',
    },
    defaultZone: 'right',
    minHeight: 140,
  },

  // ── Prediction ───────────────────────────────────────────────────────────
  {
    type: 'marey',
    title: 'Graphic Timetable',
    dataSource: 'simulation',
    kind: 'prediction',
    granularity: 'overview-detail',
    writes: 'simulation',
    status: 'shipped',
    description: 'Time-distance train-movement diagram (graphic timetable / Marey).',
    promise: 'Read train movements over time, and act on the train whose line you are following.',
    grounding:
      'Marey time-distance diagram; central to §3.3 dual-path (marey-rethink). Its decision pills are a **control layer on a Prediction widget**, declared via `writes` and acting through the shared dispatch seam with origin `marey`.',
    availableModes: 'all',
    perMode: ALL_MODES,
    defaultZone: 'center',
    minHeight: 260,
  },
  {
    type: 'strategy-forecast',
    title: 'Strategy Impact Forecast',
    dataSource: 'derived',
    kind: 'prediction',
    granularity: 'overview',
    writes: 'none',
    status: 'shipped',
    description: 'Now / +10 / +20 / +30 min projection for conflict, connections and delay side effect.',
    promise: 'See what the next half hour looks like before committing to an option.',
    grounding:
      'Anticipation (interaction-framework §2) — proactive intervention needs a horizon, not just a current state. Rule-based projection over KPI deltas; states its own limits, since the reliable horizon shrinks as problems pile up. Not a re-simulation — contrast `whatif-compare`, which does restore/simulate (A3S).',
    availableModes: ['director'],
    perMode: {
      recommendation:
        'Not offered yet. Would project the *recommended* scenario option from its KPI deltas (the component already supports this default subject) — the natural pairing with an accept/reject decision.',
      'co-learning': 'Not offered yet. Same default-subject path as Recommendation; would need neutral framing (no single "recommended" option) to fit §3.3.',
      director:
        'Explicit subject: the caller passes the strategy *focus* signals, because what is being decided here is an objective, not a policy. Reading the scenario options would be wrong — under the Director planner the baseline scenario is not the plan that drives.',
    },
    defaultZone: 'right',
    minHeight: 200,
  },
  {
    catalogId: 'B1',
    type: 'whatif-compare',
    title: 'What-if Compare ("My solution vs. AI")',
    dataSource: 'simulation',
    kind: 'prediction',
    granularity: 'detail',
    writes: 'simulation',
    status: 'first-cut',
    description: 'Branch a decision point: AI plan vs your action — the selected train\'s own fate (arrives/delay/deadlock) primary, system effect secondary, both paths drawn on the map (blue=you, yellow=AI).',
    promise: 'Try a decision both ways — see your train\'s outcome and the two map paths — before committing.',
    grounding:
      'AI4REALNET/agent-as-a-service-trace-rl (A3S) — Flatland-configured; reuse restore/simulate/action-space. Human steps blue, AI-simulated yellow. This cut reuses the in-repo what-if-override forward-sim (same contract).',
    availableModes: 'all',
    perMode: {
      recommendation: 'Compare your action against the AI’s current course (incl. any active suggestion).',
      'co-learning': 'The dual-path core (§3.3): formulate-own vs AI plan, both simulated forward, neither marked “right”; committing feeds reflection.',
      director: 'Read-only supervisory what-if — inspect a branch; Commit hidden (AI owns actuation).',
    },
    defaultZone: 'right',
    minHeight: 200,
    spec: 'docs/plans/widget-b1-whatif-compare.md',
  },
  {
    catalogId: 'B2',
    type: '',
    title: 'Conflict-aware Marey (ribbons + predicted lines)',
    dataSource: 'simulation',
    kind: 'prediction',
    granularity: 'overview-detail',
    writes: 'none',
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
    dataSource: 'derived',
    kind: 'context',
    granularity: 'overview-detail',
    writes: 'none',
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
    dataSource: 'mixed',
    kind: 'decision-support',
    granularity: 'overview',
    writes: 'simulation',
    status: 'shipped',
    description: 'Scenario cards compared by KPIs (done / deadlock / delay) with policy switch.',
    promise: 'Compare candidate scenarios/policies by KPI and pick one.',
    grounding: 'Scenario-panel per-scenario KPIs; T3.2 policy-ensemble framing.',
    availableModes: ['co-learning'],
    perMode: {
      recommendation: null,
      'co-learning': 'The neutral policy-compare surface — options unranked, no KPI-score ordering; base for the §3.3 what-if.',
      director:
        'Withdrawn: swapping the *algorithm* is a different question from setting the *objective*, and both on one screen was the main source of "which of these actually steers the AI?". `strategy-options` is the objective lever here.',
    },
    defaultZone: 'right',
    minHeight: 160,
  },
  {
    type: 'combined-actions',
    catalogId: 'E1',
    title: 'Combined Actions',
    dataSource: 'mock',
    kind: 'decision-support',
    granularity: 'overview-detail',
    status: 'first-cut',
    description: 'AI-proposed multi-train dispatch orders; drag to fork a variant, see delay, energy, map and ZWL.',
    promise: 'Fork your own variant of a coordinated AI action and see what it costs — in minutes, in energy, and in the map and the ZWL.',
    grounding:
      'T3.4 / `AI4REALNET/Tokener`: the unit of interaction is a coordinated *priority order* over the trains contending for one resource, not a per-train command — which is what the Hybrid (CBS+PP) approach negotiates. Expected-outcome-per-alternative framing follows T2.3 (`T2.3_explaining_action_alternatives`), and the AI ↔ human colour split follows the A3S/TraceRL convention (human = blue, AI = orange). ⚠ The prediction itself is a deterministic **mock** — the reuse target for the real one is the CBS/PP solver in `AI4REALNET/flatland-blackbox`, behind the `ImpactPredictor` seam (spec §8).',
    availableModes: 'all',
    perMode: {
      recommendation:
        'Recommendation framing: the AI\'s pick is badged "Recommended by AI" and ranked first, with confidence. Dragging a train forks a **variant** beside it — both keep their delay and energy figures, the moved trains carry ▲/▼ markers, and the card asks which version is kept. "Recommended by AI" survives, but the variant never reads as the AI\'s recommendation.',
      'co-learning':
        'Assessment framing: A/B/C neutral, no badge and no ranking. The fork → re-predict loop is the point — the operator builds their own variant and reads the consequence, with AI vs current always shown once modified, on both the delay and the energy axis.',
      director:
        'Suppressed to read-only supervision. Dispatch-altitude decision support belongs to the AI in Director (the human\'s lever is the objective, in `strategy-options`), so the executing package is marked "AI executing", chips are not draggable and Apply/Reset are hidden. Pointing at a card still previews its consequence in the map and the ZWL — supervising means seeing what the AI is doing.',
    },
    writes: 'view',
    defaultZone: 'right',
    minHeight: 420,
    spec: 'docs/plans/widget-e1-combined-actions.md',
  },
  {
    type: 'combined-actions-package',
    catalogId: 'E1b',
    title: 'Combined Actions (package variant)',
    dataSource: 'mock',
    kind: 'decision-support',
    granularity: 'overview-detail',
    status: 'first-cut',
    description: 'The second E1 variant: one AI package the dispatcher reorders and confirms, with a problem overview beside it.',
    promise: 'Read what is wrong, reorder the one coordinated action that answers it, and confirm — with the indirect cost to the trains nobody instructed made visible.',
    grounding:
      'Same T3.4 / `AI4REALNET/Tokener` unit of interaction as E1 — a coordinated priority order — but a different interface answer to it: one package instead of three, preceded by a problem statement. Its simulation is a single-server queue over a conflict window (`core/combined-actions-package/simulation.ts`): the controlled trains are re-slotted into the positions the timetable gave them, so reordering two of them changes how long an *uninstructed* train waits. ⚠ Both the conflict window and the queue are a stand-in for Flatland, not a solve.',
    availableModes: 'all',
    perMode: {
      recommendation:
        'The AI proposes one package; the operator reorders it and confirms. The single option is the point of the variant — it asks whether one well-explained action beats three to choose between.',
      'co-learning':
        'Same surface, read as an object to reason about: the queue model makes the indirect effect on uncontrolled trains explicit, which is the thing a dispatcher learns and a single delay number hides.',
      director:
        'Supervisory read-only, like E1: the package the AI executes is shown, not editable.',
    },
    writes: 'view',
    defaultZone: 'right',
    minHeight: 420,
    spec: 'docs/plans/widget-e1-combined-actions.md',
  },
  {
    type: 'problem-overview',
    catalogId: 'E1c',
    title: 'Problem Overview',
    dataSource: 'mock',
    kind: 'context',
    granularity: 'overview',
    status: 'first-cut',
    description: 'What is wrong, stated before any action is offered — the left half of the package variant.',
    promise: 'Say what the conflict is and whom it costs, before proposing anything about it.',
    grounding:
      'Reading order is the argument: problem on the left, network in the middle, action on the right, so the dispatcher reads from what is wrong to what to do about it rather than meeting options first. Companion to `combined-actions-package`; its conflict window is the same fixture.',
    availableModes: 'all',
    perMode: {
      recommendation: 'States the conflict the recommended package answers.',
      'co-learning': 'Same statement, no framing of any option as preferred.',
      director: 'The conflict the AI is currently resolving, read-only.',
    },
    writes: 'view',
    defaultZone: 'left',
    minHeight: 200,
    spec: 'docs/plans/widget-e1-combined-actions.md',
  },
  {
    type: 'strategy-options',
    title: 'Strategy Options (A/B/C)',
    dataSource: 'simulation',
    kind: 'decision-support',
    granularity: 'overview-detail',
    writes: 'simulation',
    status: 'shipped',
    description: 'Three planned strategy focuses — minimise delay / hold connections / maximise stability — each with its price.',
    promise: 'Choose which objective the autonomous plan should pursue, seeing what each one costs.',
    grounding:
      'Adjustable autonomy (WP 3.4) — the directive is a high-level goal, not a dispatch action. Each option is a real plan: three variants computed on session copies (~20 s) via the goal_directed planner, so the tiles carry measured per-axis utilities rather than labels. Evaluative AI per T2.3 (`AI4REALNET/T2.3_explaining_action_alternatives`): expected outcome per alternative, with the limiting factor named instead of an opaque aggregate.',
    availableModes: ['director'],
    perMode: {
      recommendation: null,
      'co-learning': null,
      director:
        'The central surface. Decision-support at the **directive** altitude, not the dispatch altitude the kind blurb suppresses in Director: the human picks an objective, the AI still owns every train. Doubles as the control — committing a tile sets the planner\'s three weights, which is why `director-weights` is withdrawn (two levers for one objective invited "which one wins?").',
    },
    defaultZone: 'center',
    minHeight: 320,
  },
  {
    type: 'recommendations',
    role: 'recommendations',
    variantLabel: 'v2 · scored strategy cards',
    variantDefault: true,
    title: 'Recommendations',
    dataSource: 'mixed',
    kind: 'decision-support',
    granularity: 'overview',
    writes: 'simulation',
    status: 'shipped',
    description: 'Scored strategy cards (A/B/C) with a WHY column; accept/reject, route preview.',
    promise: 'Compare ranked AI strategies by score + trade-offs, then accept or reject.',
    grounding:
      'Decision Assistance, Recommendation framing (advisory under Human-in-Control). The signature surface of Recommendation mode.',
    availableModes: ['recommendation'],
    perMode: {
      recommendation: 'The signature surface — scored strategy cards + WHY reasons + accept/reject with countdown.',
      'co-learning': null,
      director: null,
    },
    defaultZone: 'right',
    minHeight: 160,
  },
  {
    type: 'recommendations-classic',
    role: 'recommendations',
    variantLabel: 'v1 · simple card',
    title: 'Recommendations (classic)',
    dataSource: 'simulation',
    kind: 'decision-support',
    granularity: 'overview',
    writes: 'simulation',
    status: 'shipped',
    description: 'AI recommendations: confidence, countdown, accept/reject, route preview.',
    promise: 'Act on a ranked AI suggestion — accept or reject with a reason.',
    grounding:
      'Pre-rebuild variant, kept selectable. Same role as v2 (docs/plans/widget-variants-versioning.md).',
    availableModes: ['recommendation'],
    perMode: {
      recommendation: 'The original single-card suggestion + confidence + accept/reject with countdown.',
      'co-learning': null,
      director: null,
    },
    defaultZone: 'right',
    minHeight: 160,
    spec: 'docs/plans/widget-variants-versioning.md',
  },
  {
    catalogId: 'C1',
    type: '',
    title: 'Trade-off Frontier / Scenario Small-multiples',
    dataSource: 'simulation',
    kind: 'decision-support',
    granularity: 'overview',
    writes: 'none',
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
    dataSource: 'mixed',
    kind: 'event',
    granularity: 'overview',
    writes: 'view',
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
    dataSource: 'none',
    kind: 'control',
    granularity: 'overview',
    writes: 'simulation',
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
    dataSource: 'none',
    kind: 'control',
    granularity: 'overview',
    writes: 'simulation',
    status: 'shipped',
    description: 'KPI weight sliders (time / energy / platform / routing) as dot meters.',
    promise: 'Express which KPIs matter, shaping how options are ranked.',
    grounding: 'Operator priority elicitation; offered in no mode — the Director directive lever is `strategy-options`.',
    availableModes: [],
    perMode: {
      recommendation: null,
      'co-learning': null,
      director: null,
    },
    defaultZone: 'left',
    minHeight: 160,
  },
  {
    type: 'director-weights',
    title: 'Director Weights',
    dataSource: 'simulation',
    kind: 'control',
    granularity: 'overview',
    writes: 'simulation',
    status: 'shipped',
    description: 'Planner point meters (punctuality / connections / stability, 0-5 dots each) + committed-plan scorecard, what-if compare and gated mid-episode re-planning.',
    promise: 'Steer what the autonomous plan optimises, see what the committed plan promises and where it came from, and test or trigger a re-plan from the current state.',
    grounding: 'Adjustable autonomy (WP 3.4): high-level directives to the goal_directed planner; provenance per Evaluative AI; what-if per the A3S restore/simulate/report contract.',
    availableModes: [],
    perMode: {
      recommendation: null,
      'co-learning': null,
      director:
        'Withdrawn in favour of `strategy-options`, which sets the same three weights but says what each setting costs; two levers for one objective made it unclear which one governs. Offered in no mode (empty ≠ absent), kept wired so re-enabling is a config flip — the raw dials plus the plan scorecard (source: search vs baseline, predicted per-axis utilities) are still the better surface for debugging the planner.',
    },
    defaultZone: 'right',
    minHeight: 200,
  },
  {
    type: 'layer-visibility',
    title: 'Layer Visibility',
    dataSource: 'none',
    kind: 'control',
    granularity: 'overview',
    writes: 'view',
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
    dataSource: 'none',
    kind: 'control',
    granularity: 'overview',
    writes: 'simulation',
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
    dataSource: 'none',
    kind: 'control',
    granularity: 'overview',
    writes: 'simulation',
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
    dataSource: 'simulation',
    kind: 'capitalization',
    granularity: 'detail',
    writes: 'record',
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
    type: 'strategy-reflection',
    title: 'Strategy Reflection',
    dataSource: 'derived',
    kind: 'capitalization',
    granularity: 'overview',
    writes: 'record',
    status: 'shipped',
    description: 'Plays a committed strategy back with its price, then asks: as a rule / just this once / no.',
    promise: 'Have your objective choice answered, and decide whether it becomes a standing preference.',
    grounding:
      'The reflection agent\'s voice in Director. Mirroring [MR] per the FHNW Supportive-AI modes (Hamouche et al., T3.3), reusing the same `operator-model.service` / `ValueAxis` machinery as `co-learning-reflection`. The "just this once" option is the overfitting guard — a single situational choice must not silently become a profile.',
    availableModes: ['director'],
    perMode: {
      recommendation: null,
      'co-learning': null,
      director:
        'Director suppresses the per-train "why did you hold train 7?" prompt (the human does not dispatch), which left the operator model with no evidence at all and "what the AI learned about you" permanently empty. This is the one decision the mode does ask, so it is the one place the co-learning loop can close. Contradictions against a carried-over profile are raised as a question, never as a correction.',
    },
    defaultZone: 'right',
    minHeight: 160,
  },
  {
    type: 'co-learning-effect',
    title: 'Co-Learning Effect',
    dataSource: 'derived',
    kind: 'capitalization',
    granularity: 'overview',
    writes: 'simulation',
    status: 'shipped',
    description: '"Because you taught me this…" — names the confirmed learning behind a re-ranking, and offers the weights it implies.',
    promise: 'See what your confirmed preferences actually changed, and apply them if you want to.',
    grounding:
      'The visible half of Level B (`docs/plans/co-learning-direction.md`): making the *consequence* of confirmed preferences explicit instead of only counting them. Strictly opt-in — the AI never moves the dials on its own; a ranking nudge, not a hard rule.',
    availableModes: ['director'],
    perMode: {
      recommendation:
        'Not offered yet. Strong candidate: the same "because you taught me this" callout would explain why a recommendation is ranked where it is.',
      'co-learning':
        'Not offered yet, despite the name — a gap worth closing. Co-Learning is the mode that generates the confirmed learnings; today only Director shows what they did.',
      director:
        'Names the learning behind the operator model\'s re-ranking hint, and proposes the punctuality / connections / stability weights inferred from the operator\'s own deliberate decisions.',
    },
    defaultZone: 'right',
    minHeight: 160,
  },
  {
    type: 'shift-review',
    title: 'Shift Review (Schichtabschluss)',
    dataSource: 'mixed',
    kind: 'capitalization',
    granularity: 'detail',
    writes: 'record',
    status: 'shipped',
    description: 'End-of-shift debrief: how it ended, at most three moments worth discussing, what the AI learned.',
    promise: 'Close a shift by reviewing what happened and what the AI took from it — not just a survey link.',
    grounding:
      'Post-run reflection module per the FHNW Co-Learning HMI (T3.3): statistics plus open questions. Moments are picked by transparent scoring (`core/reflection-moments.ts`) with the trace shown, so the selection can be argued with rather than trusted. No LLM — every sentence is a template over measured values.',
    availableModes: ['director'],
    perMode: {
      recommendation:
        'Not offered yet. The material (decision log, accept/override record) exists; the debrief structure would transfer directly.',
      'co-learning':
        'Not offered yet. Overlaps `co-learning-reflection`, which covers the in-run reflection — the open question is whether the two merge into one shared closing surface.',
      director:
        'Bilanz (how the shift ended, how much the AI ran alone) · Momente (≤3 scored decisions) · Was die KI gelernt hat (confirmed preferences, implied weights, one-offs kept apart, open tensions). Takes over the screen rather than sharing a column: a debrief competing with a live simulation for attention had ~330px to say what a shift amounted to.',
    },
    defaultZone: 'floating',
    minHeight: 400,
  },
  {
    type: 'co-learning-reflection',
    title: 'Co-Learning Reflection',
    dataSource: 'mixed',
    kind: 'capitalization',
    granularity: 'detail',
    writes: 'record',
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
    dataSource: 'derived',
    kind: 'trust',
    granularity: 'overview-detail',
    writes: 'none',
    status: 'first-cut',
    description: 'Reliability, confidence & uncertainty band; Accept/Override with reasons.',
    promise: 'Judge whether to rely on the AI here, with honest uncertainty shown.',
    grounding:
      'AI4REALNET/RL_agent_failure_forecast (INESC, evidential NN) — epistemic/aleatoric. Confidence now comes from the backend branch ensemble (margin vs. dispersion, recommendation_generator.estimate_confidence); still uncalibrated, so the label stays "model-reported confidence".',
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
    dataSource: 'mixed',
    kind: 'trust',
    granularity: 'overview',
    writes: 'none',
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
    dataSource: 'simulation',
    kind: 'trust',
    granularity: 'detail',
    writes: 'none',
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
