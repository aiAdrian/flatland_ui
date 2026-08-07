import { CommonModule } from '@angular/common';
import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  OnDestroy,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { ApiService, DirectorActivity, DirectorActivityEntry } from '../../core/api.service';
import { SessionStore } from '../../core/session.store';

/**
 * "Was die KI macht" — the supervisory feed for Director mode.
 *
 * It replaces the notifications panel here, which was the wrong channel: that
 * one reports malfunctions, *operator overrides* and per-train "decision
 * pending" hints. Two of those cannot occur in Director (the human does not
 * override, and the goal-directed planner drives via schedules rather than the
 * per-cell lookahead the hint reads), so it stayed permanently empty — measured
 * over 120 steps: zero entries.
 *
 * The material for a real feed already existed and was unreachable: every
 * committed planner decision and every mid-episode re-plan, including the ones
 * the planner decided *against*. Three things now show up here:
 *
 * 1. **Disruptions** — the trigger, from the notifications the backend derives
 *    from live env state.
 * 2. **What the AI just did** — committed decisions up to the current step, and
 *    re-plans with their verdict.
 * 3. **What it is about to do** — decisions the plan has scheduled ahead. Kept
 *    separate from (2) because the trace holds *planned* times; merging them
 *    would announce a decision 30 steps in the future as having just happened.
 */
@Component({
  selector: 'app-ai-activity',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ai-activity.component.html',
  styleUrl: './ai-activity.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AiActivityComponent implements OnDestroy {
  store = inject(SessionStore);
  private api = inject(ApiService);

  readonly activity = signal<DirectorActivity | null>(null);
  readonly collapsed = signal(false);

  private _poll: ReturnType<typeof setInterval> | null = null;
  private _pollSession: string | null = null;

  constructor() {
    effect(() => {
      const sid = this.store.session()?.id ?? null;
      if (sid === this._pollSession) return;
      this._stopPoll();
      this._pollSession = sid;
      this.activity.set(null);
      if (!sid) return;
      this._fetch(sid);
      this._poll = setInterval(() => this._fetch(sid), 2500);
    });
  }

  ngOnDestroy(): void {
    this._stopPoll();
  }

  private _stopPoll(): void {
    if (this._poll) {
      clearInterval(this._poll);
      this._poll = null;
    }
  }

  private _fetch(sid: string): void {
    this.api.getDirectorActivity(sid, 6).subscribe({
      next: (a) => {
        this.activity.set(a);
        // Publish the operator's real deadline: the plan's next committed
        // decision. Nothing here expires, but without any indication the
        // question "how long do I have?" had no answer on screen.
        const next = a.upcoming[0];
        this.store.directorNextDecision.set(
          next
            ? { step: next.step, inSteps: Math.max(0, next.step - a.step), handle: next.handle ?? null }
            : null,
        );
        // The shift review needs "what did the AI do alone" and this poll already
        // has it; a second fetch at shift end would be a needless round trip.
        this.store.directorAiWorkload.set({
          decisions: a.totalDecisions,
          replans: a.totalReplans,
        });
      },
      error: () => {},
    });
  }

  toggleCollapsed(): void {
    this.collapsed.update((v) => !v);
  }

  /** Live disruptions — the reason the AI has anything to react to. */
  readonly disruptions = computed(() =>
    this.store.notifications().filter((n) => n.kind === 'error'),
  );

  readonly replans = computed(() => this.activity()?.replans ?? []);
  readonly recent = computed(() => this.activity()?.recent ?? []);
  readonly upcoming = computed(() => this.activity()?.upcoming ?? []);

  readonly hasAnything = computed(
    () =>
      this.disruptions().length > 0 ||
      this.replans().length > 0 ||
      this.recent().length > 0 ||
      this.upcoming().length > 0,
  );

  /** Provenance of the plan driving: model-guided search vs. a baseline. */
  readonly sourceLabel = computed(() => {
    const s = this.activity()?.source;
    if (!s) return null;
    switch (s) {
      case 'search':
        return 'modellgeführte Suche';
      case 'lines':
        return 'Baseline: Linienplan';
      case 'avoidance':
        return 'Baseline: Konfliktvermeidung';
      case 'avoidance (no models)':
        return 'Fallback: keine Modelle installiert';
      case 'unroutable':
        return 'kein Plan: nicht routbar';
      default:
        return s;
    }
  });

  /**
   * The trigger of a re-plan, in German and without the misleading part.
   *
   * The backend phrases it as `malfunction on train 3 until t=16` — where `t` is
   * the malfunction counter, not the simulation step, so next to an event at
   * `t=87` it reads as if the disruption ended 70 steps earlier. The remaining
   * duration is already visible in the disruption list above, so this drops it
   * rather than explaining a second time base. Unknown reasons pass through
   * verbatim instead of being guessed at.
   */
  private reasonLabel(reason?: string | null): string {
    if (!reason) return 'Auslöser unbekannt';
    const malfunction = /^malfunction on train (\d+)/i.exec(reason);
    if (malfunction) return `Störung an Zug ${malfunction[1]}`;
    if (reason === 'manual') return 'Manuell ausgelöst';
    if (reason === 'weights change') return 'Zielvorgabe geändert';
    return reason;
  }

  /** One line per entry. Numbers only where they mean something. */
  line(e: DirectorActivityEntry): string {
    if (e.kind === 'replan') {
      const reason = this.reasonLabel(e.reason);
      if (e.verdict === 'research') {
        return `${reason}: ${e.changed} Zug/Züge umgeplant`;
      }
      if (e.gate === 'rollout-veto') {
        return `${reason}: Plan behalten — die Simulation hat den Wechsel abgelehnt`;
      }
      return `${reason}: Plan behalten (der Wechsel war nicht besser)`;
    }
    if (e.stuck) {
      return `Zug ${e.handle}: kein befahrbarer Zweig`;
    }
    const hold = e.wait && e.wait > 0 ? `${e.wait} min halten, ` : '';
    return `Zug ${e.handle}: ${hold}weiter über Knoten ${e.toNode}`;
  }

  /**
   * The evidence behind the line, not decoration: for a decision how many
   * alternatives were weighed, for a re-plan the two scores that produced the
   * verdict — without them "kept the plan" is an assertion.
   */
  detail(e: DirectorActivityEntry): string | null {
    if (e.kind === 'replan') {
      const r = e.scoreResearch;
      const c = e.scoreContinue;
      if (r == null || c == null) return null;
      return `umplanen ${r.toFixed(3)} vs. weiterfahren ${c.toFixed(3)}`;
    }
    if (e.stuck || !e.optionCount) return null;
    return `${e.optionCount} Optionen geprüft`;
  }

  isHold(e: DirectorActivityEntry): boolean {
    return e.kind === 'decision' && !!e.wait && e.wait > 0;
  }

  trackEntry = (_: number, e: DirectorActivityEntry) =>
    `${e.kind}_${e.step}_${e.handle ?? 'x'}_${e.toNode ?? 'x'}`;
}
