import { CommonModule } from '@angular/common';
import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import {
  ApiService,
  DirectorFocus,
  DirectorPlanPaths,
  DirectorReportedFigures,
  DirectorStrategies,
  DirectorStrategy,
  DirectorWeights,
} from '../../core/api.service';
import { SessionStore } from '../../core/session.store';
import { OperatorModelService } from '../../core/operator-model.service';
import {
  FOCUS_BY_VALUE_AXIS,
  FOCUS_LABEL,
  FOCUS_ORDER,
  STRATEGY_COPY,
  StrategyCopy,
  VALUE_AXIS_BY_FOCUS,
  strategyHypothesis,
} from '../../core/director-strategy-copy';
import { signalsFromFocusDelta } from '../../core/strategy-forecast';

/**
 * What to put on the card for one axis.
 *
 * Punctuality's utility is a readable blend of "all trains arrive" and the delay
 * buckets, so it is shown as is. The other two are not:
 *
 * - **connections** is the geometric mean of the per-transfer keep
 *   probabilities, clamped at 1e-4. Over 35 transfers a handful of hopeless ones
 *   pull it to ~2 % while 38 % of transfers actually hold. Correct as the
 *   search's veto signal, wrong on a card — so the plain kept share is shown,
 *   which the backend explicitly calls "the number to report".
 * - **stability** is `slack × deadlock × track × cascade`. Measured example:
 *   0.69 × 0.007 × 0.72 × 0.50 = 0.0017, i.e. "0 %" — while three of the four
 *   reserves are fine and only the deadlock risk is critical. The product is
 *   kept (it is the honest aggregate) and the limiting factor is named next to
 *   it, which turns an opaque 0 % into a diagnosis.
 */
function displayPct(
  focus: DirectorFocus,
  utilities: { punctuality: number; connections: number; stability: number },
  reported?: DirectorReportedFigures | null,
): number {
  if (focus === 'connections' && reported?.keptRatio != null) {
    return Math.round(reported.keptRatio * 100);
  }
  return Math.round(utilities[focus] * 100);
}

const SAFETY_FACTOR_LABEL: Record<string, string> = {
  slack: 'Puffer',
  deadlock: 'Deadlock-Risiko',
  track: 'Gleisbelegung',
  cascade: 'Folgekonflikte',
};

/** The weakest of the four stability factors — the one that makes the product
 *  small. Null when nothing stands out or the figures are missing. */
function limitingFactorHint(reported?: DirectorReportedFigures | null): string | null {
  const safety = reported?.safety;
  if (!safety) return null;
  const entries = Object.entries(safety).filter(
    (e): e is [string, number] => typeof e[1] === 'number',
  );
  if (entries.length === 0) return null;
  const [key, value] = entries.reduce((a, b) => (a[1] <= b[1] ? a : b));
  // Only worth naming when it is actually the bottleneck.
  if (value > 0.5) return null;
  // Rounding 0.007 to "0 %" makes the diagnosis look like a placeholder; below
  // one percent the honest statement is that it is under one percent.
  const shown = value < 0.005 ? '<1 %' : `${Math.round(value * 100)} %`;
  return `begrenzt durch ${SAFETY_FACTOR_LABEL[key] ?? key} (${shown})`;
}

/**
 * The routes worth drawing for one focus: only the trains it reroutes.
 *
 * All eight planned routes look nearly identical between the three options —
 * most trains keep their path — so drawing all of them added clutter without
 * distinguishing anything. `plan.changed` names the trains that actually move
 * differently, which is what "how do the trains get around it" means.
 *
 * Returns null when there is nothing to show: no plan, no changed train, or no
 * changed train that still has a future path (a train that already arrived has
 * an empty one).
 */
function drawablePaths(s: DirectorStrategy): DirectorPlanPaths | null {
  if (!s.paths) return null;
  const out: DirectorPlanPaths = {};
  for (const [handle, points] of Object.entries(s.paths)) {
    // A single remaining cell cannot be drawn as a line (arrived trains have one
    // or none).
    if (points && points.length >= 2) out[handle] = points;
  }
  return Object.keys(out).length > 0 ? out : null;
}

function reroutePaths(s: DirectorStrategy): DirectorPlanPaths | null {
  // Prefer the divergence: it is what the map draws, so gating the button on
  // anything else let it be pressed while nothing appeared. `plan.changed` names
  // trains the planner *re-planned*, which includes ones whose cells stay
  // identical and only their timing shifts — no route to show.
  const divergence = s.divergence;
  if (divergence) {
    const out: DirectorPlanPaths = {};
    for (const [handle, entry] of Object.entries(divergence.reroutes)) {
      if (entry.points.length >= 2) out[handle] = entry.points;
    }
    if (Object.keys(out).length > 0) return out;
    // Holds have no route but are still a visible difference (a wait mark).
    return divergence.holds.length > 0 ? {} : null;
  }

  if (!s.plan || !s.paths) return null;
  const changed = new Set(s.plan.changed.map((h) => String(h)));
  const out: DirectorPlanPaths = {};
  for (const [handle, points] of Object.entries(s.paths)) {
    if (changed.size > 0 && !changed.has(handle)) continue;
    if (!points || points.length < 2) continue;
    out[handle] = points;
  }
  return Object.keys(out).length > 0 ? out : null;
}

/**
 * How many trains this focus really moves differently — counted from the same
 * source the map draws and the button gates on.
 *
 * `plan.changed` counts trains the planner **re-planned**, which includes trains
 * whose cells stay identical and only their timing shifts. Measured: a focus
 * with `changed = [0..7]` had four actual reroutes, and another had none at all.
 * The tile therefore read "Leitet 8 Züge um" right next to a dead "Auf Karte"
 * button — two statements from two sources, one of them wrong.
 */
function divergingTrains(s: DirectorStrategy): { reroutes: number; holds: number } | null {
  if (s.divergence) {
    return {
      reroutes: Object.keys(s.divergence.reroutes).length,
      holds: s.divergence.holds.length,
    };
  }
  // No divergence computed (older backend): the re-plan count is all there is.
  return s.plan ? { reroutes: s.plan.changed.length, holds: 0 } : null;
}

/** A tile as the template consumes it. */
export interface StrategyTile {
  strategy: DirectorStrategy;
  ident: string;
  copy: StrategyCopy;
  /** Utilities in a fixed axis order, or null while unplanned. `delta` is the
   *  change against the plan currently driving (null when unknown). */
  axes: Array<{
    focus: DirectorFocus;
    label: string;
    pct: number | null;
    delta: number | null;
    isFocus: boolean;
    /** For stability: which of the four factors limits it. */
    hint: string | null;
    /** For connections: how many transfers the percentage refers to. */
    scope: string | null;
  }>;
  /** How many trains this focus would reroute vs. the running plan — from the
   *  divergence, i.e. the same count the map marks. */
  changed: number | null;
  /** How many it would hold instead of rerouting. */
  holds: number | null;
  /** Score on the very axis this focus optimises — 0 means the situation
   *  offers no room there, which is worth saying rather than looking broken. */
  focusPct: number | null;
  /** Which of the four stability factors limits the product, if any. */
  stabilityHint: string | null;
  /**
   * What the map should draw for this focus: the routes of the trains it
   * actually **reroutes**, not all of them.
   *
   * Drawing all eight planned routes put eight more dashed lines onto an already
   * dense grid and — worse — showed the same picture for every option, because
   * most routes are identical between them. The changed ones are the answer to
   * "how do the trains get around it". Null when the focus changes nothing, in
   * which case there is no reroute to preview at all.
   */
  previewPaths: DirectorPlanPaths | null;
  /**
   * Every planned route of this option, for the case where it deviates from the
   * running plan nowhere.
   *
   * A disabled map button is what "Auf Karte funktioniert nicht" looks like, and
   * tile A frequently lands in exactly that state because its plan equals the one
   * already driving. The routes are still worth seeing — they just answer "where
   * is everyone headed?" instead of "what would change?".
   */
  fullPaths: DirectorPlanPaths | null;
  isActive: boolean;
  isPreviewed: boolean;
  /** This focus matches the preference learned from earlier decisions. A nudge
   *  with its evidence attached, never a re-ranking — the tile order stays. */
  isPreferred: boolean;
  /** Why it is marked, in the operator's own history. Null unless marked. */
  preferredWhy: string | null;
}

/**
 * Which tile the learned preference points at, and on what basis.
 *
 * Two sources, in order of strength:
 *  1. a **confirmed** learning ('yes' — an explicit rule),
 *  2. the dominant axis of the deliberate decisions.
 *
 * Guarded by the same evidence floor the reflection surfaces use: a single
 * choice is not a preference, and a mark that appears after one click would
 * teach the operator that the AI over-reads them. A throughput-first profile
 * marks nothing — Director offers no such preset, and rounding it onto a
 * neighbouring tile would be an invention.
 */
const MIN_EVIDENCE_FOR_PREFERRED = 3;

function preferredFocus(
  profile: ReturnType<OperatorModelService['profile']>,
): { focus: DirectorFocus; why: string } | null {
  if (!profile) return null;

  const confirmed = profile.confirmedLearnings.at(-1);
  if (confirmed) {
    const focus = FOCUS_BY_VALUE_AXIS[confirmed.targetValue];
    if (focus) {
      return { focus, why: `Von dir bestätigt: „${confirmed.statement}“` };
    }
  }

  const vp = profile.valueProfile;
  if (!vp?.dominant || vp.total < MIN_EVIDENCE_FOR_PREFERRED) return null;
  const focus = FOCUS_BY_VALUE_AXIS[vp.dominant];
  if (!focus) return null;
  const shifts = profile.priorSessions;
  const base =
    shifts > 0
      ? `${vp.total} bewusste Entscheidungen, davon ${shifts} abgeschlossene Schicht(en)`
      : `${vp.total} bewusste Entscheidungen`;
  return { focus, why: `${vp.dominantPct} % deiner Entscheidungen (${base})` };
}

/**
 * Director mode: the A/B/C strategy tiles.
 *
 * The supervisory decision is *which objective* the autonomous plan should
 * pursue — minimise delay, hold connections, maximise stability. So each tile
 * is a dial preset for the goal-directed planner, answered by an actual plan
 * under those dials (`GET /director/strategies`): the per-axis utilities it
 * promises, how many trains it reroutes, and the reroute itself as a map
 * look-ahead.
 *
 * Two deliberate constraints:
 *
 * - **No fabricated numbers.** Planning three branches costs ~15 s, so it runs
 *   on an explicit trigger with a spinner and the result is labelled with the
 *   step it was computed for. Without models installed the tiles still work as
 *   pure directives and say so, instead of showing made-up KPIs.
 * - **No dominated option.** Each focus wins on its own axis and pays on the
 *   others (see `director-strategy-copy.ts`), so choosing is a statement about
 *   values — which is exactly what the operator model may learn from.
 */
@Component({
  selector: 'app-strategy-options',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './strategy-options.component.html',
  styleUrl: './strategy-options.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class StrategyOptionsComponent {
  store = inject(SessionStore);
  private api = inject(ApiService);
  private model = inject(OperatorModelService);

  readonly strategies = signal<DirectorStrategy[]>([]);
  readonly loading = signal<boolean>(false);
  /**
   * Which slow step is running, so the wait can be named instead of shown as a
   * dead panel. Measured on the demo environment: the first plan ~10 s, the three
   * strategy plans ~20 s. That is a long time to look at nothing, which is what
   * made A/B/C feel broken.
   */
  readonly phase = signal<'idle' | 'first-plan' | 'strategies'>('idle');
  /** Simulation step the loaded strategies were planned for. */
  readonly computedAtStep = signal<number | null>(null);
  readonly unavailableReason = signal<string | null>(null);
  readonly applying = signal<string | null>(null);
  /** Per-axis scores of the plan currently driving — the baseline the tiles
   *  are read against. */
  readonly current = signal<DirectorStrategies['current']>(null);
  /** Which focus is committed, derived from the session's own dials. */
  readonly activeFocus = signal<DirectorFocus | null>(null);

  private _loadedSession: string | null = null;
  private _retriedAfterPlan = false;

  constructor() {
    // Reset when the session changes; the presets themselves are static, so a
    // fresh session simply has nothing planned yet.
    effect(() => {
      const sid = this.store.session()?.id ?? null;
      if (sid === this._loadedSession) return;
      this._loadedSession = sid;
      this._retriedAfterPlan = false;
      this.strategies.set([]);
      this.computedAtStep.set(null);
      this.unavailableReason.set(null);
      this.clearPreview();
      if (sid) this.load();
    });

    // A plan may appear without us: stepping under 'goal_directed' plans on the
    // first step, so pressing Play produces one. Pick it up then.
    effect(() => {
      const planned = this.store.directorPlanPaths() !== null;
      if (!planned || this._retriedAfterPlan) return;
      if (this.loading() || this.hasPlans()) return;
      this._retriedAfterPlan = true;
      untracked(() => this.load());
    });

    // Numbers computed mid-run describe a state the episode has already left.
    // Pausing is when the operator actually decides, so refresh once then —
    // the cache makes it free when nothing changed.
    let wasPlaying = false;
    effect(() => {
      const playing = this.store.playing();
      const stopped = wasPlaying && !playing;
      wasPlaying = playing;
      if (!stopped) return;
      untracked(() => {
        if (!this.loading()) this.load(true);
      });
    });
  }

  /**
   * Publish the focus the impact-forecast strip below the map should describe:
   * the one being previewed, else the committed one. Only focuses with a plan
   * qualify — a forecast needs a delta against the running plan to project,
   * and inventing one would be worse than showing nothing.
   */
  private readonly _publishOutlook = effect(() => {
    const previewId = this.store.directorPreviewStrategyId();
    const active = this.activeFocus();
    const planned = this.strategies().filter((s) => s.plan !== null);
    const subject =
      planned.find((s) => s.id === previewId) ??
      planned.find((s) => s.focus === active) ??
      null;
    const current = this.current();

    if (!subject || !current) {
      this.store.directorFocusOutlook.set(null);
      return;
    }
    const delta = {
      punctuality: subject.plan!.utilities.punctuality - current.utilities.punctuality,
      connections: subject.plan!.utilities.connections - current.utilities.connections,
      stability: subject.plan!.utilities.stability - current.utilities.stability,
    };
    this.store.directorFocusOutlook.set({
      subject: `${subject.ident} · ${STRATEGY_COPY[subject.focus].title}`,
      signals: signalsFromFocusDelta(delta),
    });
  });

  /** Stale = the episode moved on since the tiles were planned, so the numbers
   *  describe a state that no longer exists. Said out loud rather than hidden. */
  readonly stale = computed<boolean>(() => {
    const at = this.computedAtStep();
    return at !== null && this.store.elapsedSteps() > at;
  });

  /**
   * The tile the operator model expects, carried over from earlier shifts.
   *
   * Answers "what did the AI actually learn about me?" where the decision is
   * made instead of only in the closing review — and it is the visible half of
   * the warm start: without it a saved preference had no effect the operator
   * could see at the next shift.
   */
  readonly preferred = computed(() => preferredFocus(this.model.profile()));

  readonly tiles = computed<StrategyTile[]>(() => {
    const previewId = this.store.directorPreviewStrategyId();
    const active = this.activeFocus();
    const current = this.current();
    const preferred = this.preferred();
    return this.strategies().map((s) => ({
      strategy: s,
      ident: s.ident,
      copy: STRATEGY_COPY[s.focus],
      axes: FOCUS_ORDER.map((focus) => {
        const pct = s.plan ? displayPct(focus, s.plan.utilities, s.plan.reported) : null;
        const base = current
          ? displayPct(focus, current.utilities, current.reported)
          : null;
        return {
          focus,
          label: FOCUS_LABEL[focus],
          pct,
          delta: pct !== null && base !== null ? pct - base : null,
          isFocus: focus === s.focus,
          hint: focus === 'stability' ? limitingFactorHint(s.plan?.reported) : null,
          scope:
            focus === 'connections' && s.plan?.reported?.connectionCount
              ? `von ${s.plan.reported.connectionCount}`
              : null,
        };
      }),
      changed: divergingTrains(s)?.reroutes ?? null,
      holds: divergingTrains(s)?.holds ?? null,
      focusPct: s.plan ? displayPct(s.focus, s.plan.utilities, s.plan.reported) : null,
      stabilityHint: limitingFactorHint(s.plan?.reported),
      previewPaths: reroutePaths(s),
      fullPaths: drawablePaths(s),
      isActive: active === s.focus,
      isPreviewed: previewId === s.id,
      isPreferred: preferred?.focus === s.focus,
      preferredWhy: preferred?.focus === s.focus ? preferred.why : null,
    }));
  });

  /** True once at least one tile carries a planned answer. */
  readonly hasPlans = computed(() => this.strategies().some((s) => s.plan !== null));

  /** The forecast is waiting for a pause rather than missing. Said out loud so
   *  the tiles do not look broken while the run is going. */
  readonly waitingForPause = computed(
    () => this.store.playing() && !this.loading() && !this.hasPlans(),
  );

  /**
   * All three focuses came back with the same plan — which happens when the
   * situation offers no move that trades the axes against each other yet.
   * Named out loud: three identical bar charts otherwise read as a broken
   * panel, when in truth it is the honest answer "the choice does not bite
   * here". The moment it does bite, the tiles diverge.
   */
  readonly allFocusesAgree = computed<boolean>(() => {
    const planned = this.strategies().filter((s) => s.plan !== null);
    if (planned.length < 2) return false;
    const key = (s: DirectorStrategy) =>
      FOCUS_ORDER.map((f) => s.plan!.utilities[f].toFixed(4)).join('|');
    const first = key(planned[0]);
    return (
      planned.every((s) => key(s) === first) &&
      // Same source as the tiles and the map: `plan.changed` counts re-planned
      // trains, so it stayed non-empty even when no train drove differently.
      planned.every((s) => {
        const d = divergingTrains(s);
        return d !== null && d.reroutes === 0 && d.holds === 0;
      })
    );
  });

  /**
   * The look-ahead button's label.
   *
   * "Auf Karte" on a disabled button is a promise the tile cannot keep, and the
   * reason sat in a native `title` tooltip — so the first click of the demo (tile
   * A, whose plan often equals the one already driving) landed on what looked
   * like a broken button. The label now states the fact instead.
   */
  previewLabel(tile: StrategyTile): string {
    if (tile.isPreviewed) return 'Karte aus';
    if (tile.previewPaths) return 'Auf Karte';
    // No deviation to mark, but there are routes to draw: say which of the two
    // the click delivers instead of promising a look-ahead at a change.
    if (tile.fullPaths) return 'Plan auf Karte';
    return 'Auf Karte';
  }

  focusLabel(focus: DirectorFocus): string {
    return FOCUS_LABEL[focus];
  }

  /**
   * Load (or re-load) the planned strategies for the current state.
   *
   * Skipped while the run is playing unless forced. Measured: three residual
   * plans take ~20 s, and every simulation step invalidates them — so a forecast
   * computed mid-run describes a state the episode has already left before the
   * answer arrives, while competing with the simulation for CPU. Pausing is when
   * the operator decides anyway, and the pause handler below loads then.
   */
  load(force = false): void {
    const sid = this.store.session()?.id;
    if (!sid || this.loading()) return;
    if (!force && this.store.playing()) return;
    this.loading.set(true);
    this.phase.set('strategies');
    this.api.getDirectorStrategies(sid).subscribe({
      next: (res) => {
        this.phase.set('idle');
        this.strategies.set(res.strategies);
        this.current.set(res.current ?? null);
        this.unavailableReason.set(res.available ? null : res.reason);
        this.computedAtStep.set(res.available ? res.step : null);
        this.loading.set(false);
        this._repointLivePreview();
        this._syncActiveFocus();
        if (!res.available) this._materialisePlanOnce();
      },
      error: () => {
        this.loading.set(false);
        this.phase.set('idle');
        this.unavailableReason.set('Strategien konnten nicht geplant werden.');
      },
    });
  }

  /**
   * A Director session plans lazily, so entering the mode finds nothing to
   * compare the focuses against. Trigger that first plan ourselves — with the
   * session's *current* dials, so it commits nothing the operator did not
   * already have — and reload once it exists.
   *
   * This used to be the Director Weights panel's job. That panel is no longer on
   * the Director screen (the tiles are the dial surface now), so the tiles have
   * to stand on their own; without this they would sit empty until someone found
   * the "Optionen berechnen" button.
   */
  private _materialisePlanOnce(): void {
    const sid = this.store.session()?.id;
    if (!sid || this._retriedAfterPlan) return;
    // While the run is going, stepping under 'goal_directed' produces the first
    // plan by itself. Forcing a second one in parallel only competes for the
    // same ~10s of planning and made the panel look stuck for twice as long;
    // the `directorPlanPaths` effect above picks it up instead.
    if (this.store.playing()) return;
    this._retriedAfterPlan = true;
    this.loading.set(true);
    this.phase.set('first-plan');
    this.api.getDirectorState(sid).subscribe({
      next: (state) => {
        if (state.plan) {
          // Already planned — the earlier "unavailable" was about something
          // else (no models, say). Don't re-plan, just stop.
          this.loading.set(false);
          this.phase.set('idle');
          return;
        }
        this.api.setDirectorWeights(sid, state.weights, true).subscribe({
          next: (res) => {
            if (res.paths) this.store.directorPlanPaths.set(res.paths);
            this.loading.set(false);
            this.phase.set('idle');
            if (res.replanned) this.load();
          },
          error: () => {
            this.loading.set(false);
            this.phase.set('idle');
          },
        });
      },
      error: () => {
        this.loading.set(false);
        this.phase.set('idle');
      },
    });
  }

  /**
   * Put this focus on the map, and keep it there. Clicking the shown tile again
   * clears it.
   *
   * Two cases, deliberately both handled: with a divergence the map marks what
   * *changes*; without one it draws the option's routes and says they match the
   * running plan. The second case used to be a disabled button — which is what
   * "Auf Karte funktioniert nicht" looked like, and it hit tile A most often.
   */
  togglePreview(tile: StrategyTile): void {
    const paths = tile.previewPaths ?? tile.fullPaths;
    if (!paths) return;
    if (
      this.store.directorPreviewStrategyId() === tile.strategy.id &&
      !this.store.directorPreviewIsCommitted()
    ) {
      this.clearPreview();
      return;
    }
    // The divergence is what the map draws; the full paths stay available for
    // the one train the operator points at.
    this.store.directorPreviewDivergence.set(
      tile.previewPaths ? tile.strategy.divergence ?? null : null,
    );
    this.store.directorPreviewPaths.set(paths);
    this.store.directorPreviewStrategyId.set(tile.strategy.id);
    this.store.directorPreviewIsCommitted.set(false);
    this.store.directorPreviewIsFullPlan.set(!tile.previewPaths);
    this.store.directorHoverHandle.set(null);
  }

  clearPreview(): void {
    this.store.directorPreviewPaths.set(null);
    this.store.directorPreviewDivergence.set(null);
    this.store.directorPreviewStrategyId.set(null);
    this.store.directorPreviewIsCommitted.set(false);
    this.store.directorPreviewIsFullPlan.set(false);
    this.store.directorHoverHandle.set(null);
  }

  /**
   * After a recompute, point a live look-ahead at the *new* routes.
   *
   * Without this the map kept drawing the routes from the previous computation
   * while the tile still showed as previewed — a stale picture under a fresh
   * label, which is worse than showing nothing. Drops the overlay when the
   * refreshed focus has no reroute left to show.
   */
  private _repointLivePreview(): void {
    const id = this.store.directorPreviewStrategyId();
    if (!id || this.store.directorPreviewIsCommitted()) return;
    const tile = this.tiles().find((t) => t.strategy.id === id);
    const paths = tile?.previewPaths ?? tile?.fullPaths ?? null;
    if (!paths) {
      this.clearPreview();
      return;
    }
    this.store.directorPreviewPaths.set(paths);
    this.store.directorPreviewDivergence.set(
      tile!.previewPaths ? tile!.strategy.divergence ?? null : null,
    );
    this.store.directorPreviewIsFullPlan.set(!tile!.previewPaths);
  }

  /** Why the map button cannot be pressed — stated instead of just greyed out.
   *  Null when it *can* be pressed, including the case where it draws the plan
   *  rather than a deviation. */
  previewBlockedReason(tile: StrategyTile): string | null {
    if (tile.previewPaths) return null;
    // Nothing changes, but the routes are there: the click still delivers
    // something, so this is a hint about *what*, not a blocker.
    if (tile.fullPaths) {
      return 'Dieses Ziel fährt jeden Zug wie der laufende Plan — der Klick zeigt diesen Plan.';
    }
    if (this.loading()) return 'Die Umleitung wird gerade berechnet.';
    if (this.waitingForPause()) {
      return 'Pausiere den Lauf — dann wird die Umleitung berechnet und hier anklickbar.';
    }
    if (!tile.strategy.plan) {
      return 'Erst „Optionen berechnen“ — ohne Plan gibt es keine Route zu zeigen.';
    }
    return 'Für dieses Ziel liegt keine Route vor.';
  }

  /** Commit a focus: the session's dials become the preset and the planner
   *  re-plans immediately, so the map shows the plan actually driving. */
  apply(tile: StrategyTile): void {
    const sid = this.store.session()?.id;
    if (!sid || this.applying()) return;
    this.applying.set(tile.strategy.id);
    this.api.setDirectorWeights(sid, tile.strategy.weights, true).subscribe({
      next: (res) => {
        this.applying.set(null);
        this.activeFocus.set(tile.strategy.focus);
        if (res.paths) {
          // The full committed plan, for the hover overlay that shows every route.
          this.store.directorPlanPaths.set(res.paths);
        }
        // Draw what *changed*, same as the preview did. Clearing the overlay here
        // instead (what this did before) meant committing a focus changed nothing
        // visible beyond a button label; drawing all eight routes instead would
        // bury the change in the lines that stayed the same.
        if (tile.previewPaths) {
          this.store.directorPreviewPaths.set(tile.previewPaths);
          this.store.directorPreviewDivergence.set(tile.strategy.divergence ?? null);
          this.store.directorPreviewStrategyId.set(tile.strategy.id);
          this.store.directorPreviewIsCommitted.set(true);
          this.store.directorPreviewIsFullPlan.set(false);
        } else if (res.paths) {
          // Nothing deviates, so there are no marks to draw — but the committed
          // plan itself is worth showing, and it is now literally the active one.
          this.store.directorPreviewPaths.set(res.paths);
          this.store.directorPreviewDivergence.set(null);
          this.store.directorPreviewStrategyId.set(tile.strategy.id);
          this.store.directorPreviewIsCommitted.set(true);
          this.store.directorPreviewIsFullPlan.set(true);
        } else {
          this.clearPreview();
        }
        this._recordChoice(tile);
        // The committed plan is a new baseline, so every focus's delta refers to
        // something that no longer drives. Free when nothing changed (cached).
        this.load();
      },
      error: () => this.applying.set(null),
    });
  }

  /**
   * Log the committed focus as preference evidence and open its reflection
   * prompt.
   *
   * This is the only decision Director asks of the human, so without it the
   * operator model receives nothing at all in this mode and the "what the AI
   * learned about you" panel stays empty for the whole run. It is also the
   * cleanest signal the app has: the axis is stated, the alternatives were on
   * screen, and their cost was quantified.
   */
  private _recordChoice(tile: StrategyTile): void {
    const traded = this._tradedAway(tile);
    this.store.recordStrategyChoice({
      title: tile.copy.title,
      ident: tile.ident,
      axis: VALUE_AXIS_BY_FOCUS[tile.strategy.focus],
      tradedAway: traded,
      hypothesis: strategyHypothesis(tile.strategy.focus, traded),
    });
  }

  /**
   * The axis this choice gave up the most of, as "44 Punkte Stabilität".
   *
   * The focus's **own** axis is excluded: it produced sentences like "du
   * priorisierst Anschlüsse — auch wenn es 2 Punkte Anschlüsse kostet". A goal
   * cannot be its own price; when the chosen option also scores worse on its own
   * axis that means the option is weak, not that a trade-off was made.
   *
   * The sign is dropped because this reads as a price — "Preis von -44" is a
   * double negation. Null when nothing else regressed: then there was no price.
   */
  private _tradedAway(tile: StrategyTile): string | null {
    const worst = tile.axes
      .filter((a) => a.focus !== tile.strategy.focus)
      .filter((a) => a.delta !== null && a.delta < 0)
      .sort((a, b) => (a.delta ?? 0) - (b.delta ?? 0))[0];
    if (!worst) return null;
    return `${Math.abs(worst.delta!)} Punkte ${worst.label}`;
  }

  /** Which preset (if any) matches the session's current dial ratio. Compared
   *  on the normalised ratio, because the backend stores its own magnitude. */
  private _syncActiveFocus(): void {
    const sid = this.store.session()?.id;
    if (!sid) return;
    this.api.getDirectorState(sid).subscribe({
      next: (state) => {
        const match = this.strategies().find((s) => this._sameRatio(s.weights, state.weights));
        this.activeFocus.set(match ? match.focus : null);
      },
      error: () => {},
    });
  }

  private _sameRatio(a: DirectorWeights, b: DirectorWeights): boolean {
    const norm = (w: DirectorWeights): number[] => {
      const total = w.punctuality + w.connections + w.stability;
      if (total <= 0) return [0, 0, 0];
      return [w.punctuality / total, w.connections / total, w.stability / total];
    };
    const [a1, a2, a3] = norm(a);
    const [b1, b2, b3] = norm(b);
    const close = (x: number, y: number) => Math.abs(x - y) < 0.02;
    return close(a1, b1) && close(a2, b2) && close(a3, b3);
  }
}
