import { CommonModule } from '@angular/common';
import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  HostBinding,
  HostListener,
  Input,
  OnDestroy,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import {
  ApiService,
  DirectorPlanInfo,
  DirectorReplanEvent,
  DirectorTraceEntry,
  DirectorVerification,
  DirectorWeights,
  DirectorWhatIf,
} from '../../core/api.service';
import { SessionStore } from '../../core/session.store';

interface DialDef {
  key: keyof DirectorWeights;
  label: string;
  hint: string;
}

/**
 * Director-mode dials for the goal_directed planner: how much the
 * autonomous plan should value punctuality, connections and stability.
 * Each metric gets 0–5 discrete points (dot meters, the design taken
 * from the retired KPI filter): small continuous nudges barely move a
 * normalised weight ratio, so bucketing makes every click a change the
 * planner can actually respond to. The weight relation is the point
 * ratio. Changing points re-plans immediately; the scorecard below
 * shows what the committed plan promises and where it came from
 * (search vs baseline — the Evaluative-AI provenance, not just a score).
 */
@Component({
  selector: 'app-director-weights',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './director-weights.component.html',
  styleUrl: './director-weights.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class DirectorWeightsComponent implements OnDestroy {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  /** While the mouse is on this widget, the map highlights the committed
   *  plan's train paths — the gut-check for what the dials produce. */
  @HostListener('mouseenter')
  onMouseEnter(): void {
    this.store.directorPlanHover.set(true);
  }

  @HostListener('mouseleave')
  onMouseLeave(): void {
    this.store.directorPlanHover.set(false);
  }

  store = inject(SessionStore);
  private api = inject(ApiService);

  readonly dials: DialDef[] = [
    { key: 'punctuality', label: 'Punctuality', hint: 'arrivals & low delay' },
    { key: 'connections', label: 'Connections', hint: 'transfers reached' },
    { key: 'stability', label: 'Stability', hint: 'disturbance headroom' },
  ];

  /** Points per metric (0–5). Only the ratio matters — the backend
   *  normalises — so the points go over the wire as they are. */
  readonly MAX_POINTS = 5;

  /** Local point state; pushed to the backend debounced. */
  readonly weights = signal<DirectorWeights>({
    punctuality: 5,
    connections: 5,
    stability: 5,
  });
  readonly plan = signal<DirectorPlanInfo | null>(null);
  readonly planPending = signal<boolean>(false);
  readonly verification = signal<DirectorVerification | null>(null);
  readonly verifying = signal<boolean>(false);
  readonly replanning = signal<boolean>(false);
  readonly whatIf = signal<DirectorWhatIf | null>(null);
  readonly whatIfRunning = signal<boolean>(false);
  readonly replans = computed<DirectorReplanEvent[]>(
    () => this.plan()?.replans ?? []);
  readonly usingDirectorPolicy = computed(
    () => this.store.activePolicy() === 'goal_directed');
  /** A new plan is being computed (slider settle or manual re-plan):
   *  the widget grays out under a spinner and blocks input until the
   *  response replaces the stale scorecard. */
  readonly busy = computed(() => this.planPending() || this.replanning());

  private _pushTimer: ReturnType<typeof setTimeout> | null = null;
  private _pollSession: string | null = null;
  private _poll: ReturnType<typeof setInterval> | null = null;
  /** Session whose initial plan this panel already materialised — the
   *  Director plans lazily (first planned action or weights push), so
   *  without this nudge the scorecard and map overlay stay empty until
   *  the user happens to move a slider. Once per session: a session
   *  that stays plan-less (unroutable, no models) must not retry-loop. */
  private _autoPlannedSession: string | null = null;

  constructor() {
    // Follow the active session: reload its dials, poll its scorecard.
    effect(() => {
      const sid = this.store.session()?.id ?? null;
      if (sid === this._pollSession) return;
      this._stopPoll();
      this._pollSession = sid;
      this.whatIf.set(null);
      this.verification.set(null);
      if (!sid) return;
      this._fetch(sid);
      this._poll = setInterval(() => this._fetch(sid), 2000);
    });
  }

  ngOnDestroy(): void {
    this._stopPoll();
    if (this._pushTimer) clearTimeout(this._pushTimer);
    // A panel removed mid-hover must not leave the overlay stuck on.
    this.store.directorPlanHover.set(false);
  }

  /** Click dot `points` to set that many; clicking the current top dot
   *  steps down one, so 0 stays reachable. A click that would zero the
   *  total is ignored — the planner needs at least one point somewhere. */
  setPoints(key: keyof DirectorWeights, points: number): void {
    const current = this.weights()[key];
    const value = Math.max(
      0, Math.min(this.MAX_POINTS, points === current ? points - 1 : points));
    if (value === current) return;
    const next = { ...this.weights(), [key]: value };
    if (next.punctuality + next.connections + next.stability <= 0) return;
    this.weights.set(next);
    this._schedulePush();
  }

  /** Filled state per dot, for the meter row. */
  dots(value: number): boolean[] {
    return Array.from({ length: this.MAX_POINTS }, (_, i) => i < value);
  }

  /** Share of the total each dial gets — what the planner actually sees. */
  share(key: keyof DirectorWeights): string {
    const w = this.weights();
    const total = w.punctuality + w.connections + w.stability;
    if (total <= 0) return '–';
    return `${Math.round((w[key] / total) * 100)}%`;
  }

  utilityPct(value: number | undefined): number {
    return Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100);
  }

  /** Provenance kind for the badge: the plan may come from the search or
   *  from a baseline planner (portfolio guarantee), a mid-episode
   *  re-plan, or a model-free fallback when no checkpoints are
   *  installed. */
  sourceKind(source: string): 'search' | 'baseline' | 'fallback' {
    if (source === 'search' || source.startsWith('replan-')) return 'search';
    if (source === 'lines' || source === 'avoidance') return 'baseline';
    return 'fallback';
  }

  sourceLabel(source: string): string {
    switch (source) {
      case 'search': return 'model-guided search';
      case 'lines': return 'baseline: line plan';
      case 'avoidance': return 'baseline: conflict avoidance';
      case 'avoidance (no models)': return 'fallback: no models installed';
      case 'unroutable': return 'no plan: unroutable';
      case 'replan-research': return 're-planned mid-episode';
      default: return source;
    }
  }

  verify(): void {
    const sid = this.store.session()?.id;
    if (!sid || this.verifying()) return;
    this.verifying.set(true);
    this.api.verifyDirectorPlan(sid).subscribe({
      next: (result) => {
        this.verification.set(result);
        this.verifying.set(false);
      },
      error: () => this.verifying.set(false),
    });
  }

  /** Re-plan the remainder from the current state, now — the manual
   *  counterpart of the malfunction trigger. */
  replanNow(): void {
    const sid = this.store.session()?.id;
    if (!sid || this.replanning()) return;
    this.replanning.set(true);
    this.api.replanDirectorNow(sid).subscribe({
      next: (result) => {
        this.plan.set(result.plan);
        this.verification.set(null);
        this.replanning.set(false);
        this.store.directorPlanPaths.set(result.paths);
      },
      error: () => this.replanning.set(false),
    });
  }

  /** Simulate continue-vs-re-plan under the current dials on forks of
   *  the live episode; nothing is committed. */
  runWhatIf(): void {
    const sid = this.store.session()?.id;
    if (!sid || this.whatIfRunning()) return;
    this.whatIfRunning.set(true);
    this.api.whatIfDirector(sid, this.weights()).subscribe({
      next: (result) => {
        this.whatIf.set(result);
        this.whatIfRunning.set(false);
      },
      error: () => this.whatIfRunning.set(false),
    });
  }

  /** One-liner for a re-plan event in the history list. */
  replanSummary(event: DirectorReplanEvent): string {
    const verdict = event.source === 'research'
      ? `re-planned ${event.changed.length} trains`
      : event.gate === 'rollout-veto'
        ? 'kept the plan (simulation vetoed the switch)'
        : 'kept the plan';
    return `t=${event.step} · ${event.reason}: ${verdict} `
      + `(${event.considered.research.toFixed(3)} vs `
      + `${event.considered.continue.toFixed(3)})`;
  }

  /** Per-decision one-liner for the trace list: what was committed. */
  traceSummary(entry: DirectorTraceEntry): string {
    if (entry.stuck || entry.chosen === undefined) {
      return `t=${Math.round(entry.time)} · train ${entry.handle}: no viable branch`;
    }
    const chosen = entry.options[entry.chosen];
    const hold = chosen.wait > 0 ? `hold ${chosen.wait} min, ` : '';
    return `t=${Math.round(entry.time)} · train ${entry.handle}: `
      + `${hold}via node ${chosen.to_node} `
      + `(${entry.options.length} options, score ${chosen.weighted.toFixed(3)})`;
  }

  private _schedulePush(): void {
    if (this._pushTimer) clearTimeout(this._pushTimer);
    this._pushTimer = setTimeout(() => {
      this._pushTimer = null;
      this._push();
    }, 400);
  }

  private _push(): void {
    const sid = this.store.session()?.id;
    if (!sid) return;
    const w = this.weights();
    if (w.punctuality + w.connections + w.stability <= 0) return;
    // Ask for an immediate (re-)plan so the response carries the new
    // plan and its paths — the map overlay updates the moment the
    // slider settles, not on the next step.
    this.planPending.set(true);
    this.verification.set(null);
    this.api.setDirectorWeights(sid, w, true).subscribe({
      next: (result) => {
        this.plan.set(result.plan);
        this.planPending.set(false);
        this.store.directorPlanPaths.set(result.paths);
      },
      error: () => this.planPending.set(false),
    });
  }

  private _fetch(sid: string): void {
    this.api.getDirectorState(sid).subscribe({
      next: (state) => {
        // While a push or manual re-plan is in flight, its response owns
        // the panel — a poll that raced it would clear the busy overlay
        // early and paint stale plan/paths over the fresh ones.
        if (this.planPending() || this.replanning()) return;
        this.plan.set(state.plan);
        this.store.directorPlanPaths.set(state.paths);
        // Adopt backend dials only while the user is not mid-drag. Only
        // the ratios matter (the planner normalises), so rescale to the
        // slider range rather than trusting the stored magnitude.
        if (!this._pushTimer) {
          this.weights.set(this._rescaled(state.weights));
        }
        if (!state.plan && this._autoPlannedSession !== sid) {
          this._autoPlannedSession = sid;
          this._push();
        }
      },
      error: () => {},
    });
  }

  /** Map arbitrary stored weights onto the 0–5 point grid, largest → 5.
   *  Only the ratio matters; a non-zero weight never rounds to 0 (that
   *  would silently erase an axis the user cared about). */
  private _rescaled(w: DirectorWeights): DirectorWeights {
    const top = Math.max(w.punctuality, w.connections, w.stability);
    if (top <= 0) {
      return {
        punctuality: this.MAX_POINTS,
        connections: this.MAX_POINTS,
        stability: this.MAX_POINTS,
      };
    }
    const point = (v: number) => (
      v <= 0 ? 0 : Math.max(1, Math.round((v / top) * this.MAX_POINTS)));
    return {
      punctuality: point(w.punctuality),
      connections: point(w.connections),
      stability: point(w.stability),
    };
  }

  private _stopPoll(): void {
    if (this._poll) {
      clearInterval(this._poll);
      this._poll = null;
    }
  }
}
