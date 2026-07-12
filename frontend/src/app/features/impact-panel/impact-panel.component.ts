import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, OnDestroy, computed, effect, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { ApiService } from '../../core/api.service';
import { AgentColorService } from '../../core/agent-color.service';
import { ImpactItem, ImpactOption } from '../../core/events/event-types';
import { ActionInt } from '../../core/models';

/**
 * Impact analysis panel (Phase 1): when a train malfunctions, shows which other
 * trains are affected (blocked on their path before the block clears) and a
 * coarse recommendation per train. Framing follows optionPresentation:
 *  - recommendation: the recommended action is highlighted + applicable
 *  - co-learning: affected trains shown neutrally (inspect & decide yourself)
 *  - director: overview only (AI handles it)
 */
@Component({
  selector: 'app-impact-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './impact-panel.component.html',
  styleUrl: './impact-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ImpactPanelComponent implements OnDestroy {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  store = inject(SessionStore);
  private api = inject(ApiService);
  private colors = inject(AgentColorService);

  private static readonly STOP = 4;
  private _pollHandle: any = null;
  private _pollSession: string | null = null;
  private _hadImpact = false;

  /** Items the user has acted on (applied) → hidden from the list. */
  readonly applied = signal<Set<number>>(new Set<number>());

  /** Affected trains the system is currently holding (localized blocking,
   *  Co-Learning): they wait for the human's decision while the rest runs. */
  private readonly _held = signal<Set<number>>(new Set<number>());
  readonly heldCount = computed(() => this._held().size);
  isHeld(handle: number): boolean { return this._held().has(handle); }

  /** Hold every still-affected train (STOP) and remember it as held. */
  private _holdAffected(): void {
    const next = new Set(this._held());
    for (const item of this.items()) {
      if (!next.has(item.handle)) {
        this.store.systemHold(item.handle);
        next.add(item.handle);
      }
    }
    this._held.set(next);
  }

  // Stabilized display list. The live impact poll (1.5s) makes rows pop in/out
  // and reorder, which felt chaotic. We keep a short grace window so transient
  // blips don't flash, hold a stable order (by handle), and keep held rows.
  private static readonly GRACE_MS = 3000;
  private readonly _cache = new Map<number, ImpactItem>();
  private readonly _seenAt = new Map<number, number>();
  private readonly _stable = signal<ImpactItem[]>([]);

  /** Affected trains still pending an action (acted-on ones removed). */
  readonly items = computed<ImpactItem[]>(() =>
    this._stable().filter((i) => !this.applied().has(i.handle)),
  );

  /** Panel stays visible always; auto-expands when trains are affected,
   *  auto-collapses when nothing is going on. User can still toggle. */
  readonly collapsed = signal<boolean>(false);
  private _lastHasImpact = false;

  /** Decision countdown (seconds left) before the system auto-applies the
   *  recommended option; null = inactive. */
  readonly countdownRemaining = signal<number | null>(null);
  private _tickHandle: any = null;

  /** Countdown progress 0..1 (for the bar). */
  readonly countdownPct = computed(() => {
    const rem = this.countdownRemaining();
    const total = this.store.decisionCountdownSeconds();
    if (rem == null || total <= 0) return 0;
    return Math.max(0, Math.min(1, rem / total));
  });

  /**
   * How this panel behaves per interaction mode — the single place mode is
   * branched on inside this component (framing is handled in the template via
   * store.optionPresentation()). See docs/reference/panel-mode-matrix.md.
   *  - decisionMoment: how a new conflict engages the human.
   *      'countdown' → gentle global pause + auto-apply countdown (Recommendation)
   *      'hold'      → localized hold of affected trains, world keeps running (Co-Learning)
   *      'none'      → AI handles it, no decision moment (Director)
   *  - reflectAfterDecision: nudge the reflection panel once the last decision lands.
   */
  readonly modeBehavior = computed<{ decisionMoment: 'countdown' | 'hold' | 'none'; reflectAfterDecision: boolean }>(() => {
    switch (this.store.interactionMode()) {
      case 'recommendation': return { decisionMoment: 'countdown', reflectAfterDecision: false };
      case 'co-learning':    return { decisionMoment: 'hold', reflectAfterDecision: true };
      case 'director':       return { decisionMoment: 'none', reflectAfterDecision: false };
    }
  });

  constructor() {
    // Auto-EXPAND when conflicts appear; never auto-collapse (that open/close
    // thrash was part of the chaotic feel). The user can collapse manually.
    effect(() => {
      const has = this.items().length > 0;
      if (has && !this._lastHasImpact) this.collapsed.set(false);
      this._lastHasImpact = has;
    });

    // Keep the stabilized display list in sync with store.impact() from ANY
    // source — the live poll below, or a value set elsewhere (e.g. a pre-seeded
    // gallery fixture with no backend behind it). The poll additionally rebuilds
    // synchronously inside _fetchImpact for its engage/countdown logic; this
    // effect covers the non-poll sources. Safe: _rebuildStable writes _stable
    // (not store.impact), so there is no feedback loop, and its merge is
    // idempotent, so the redundant rebuild on the poll path is harmless.
    effect(() => {
      this._rebuildStable(this.store.impact());
    });

    // Impact is cheap to compute → poll it live (~1.5s) so conflicts surface
    // while the simulation runs, not only on pause. Scenarios stay throttled.
    effect(() => {
      const sid = this.store.session()?.id ?? null;
      if (sid !== this._pollSession) {
        this._pollSession = sid;
        this._stopPoll();
        this.applied.set(new Set<number>());
        if (sid) {
          this._fetchImpact(sid);
          this._pollHandle = setInterval(() => {
            const cur = this.store.session()?.id;
            if (cur) this._fetchImpact(cur);
          }, 1500);
        }
      }
    });
  }

  private _fetchImpact(sid: string): void {
    this.api.getImpact(sid).subscribe({
      next: (live) => {
        this.store.impact.set(live);
        this._rebuildStable(live);

        const has = live.length > 0;
        const newConflict = has && !this._hadImpact;
        const strategy = this.modeBehavior().decisionMoment;
        const engage = newConflict && this.store.demoActive() && this.store.playing()
          && strategy !== 'none'
          && this.store.autoPauseOnConflict();

        if (engage) {
          // Open the decision-dwell window for each affected train so the
          // Decision Log can record decisionTimeMs when the human (or AI
          // auto-decide) eventually acts on it.
          for (const item of this.items()) {
            this.store.openDecisionWindow(item.handle);
          }
          if (strategy === 'hold') {
            // Localized blocking (Co-Learning): hold the affected trains, keep the
            // world running. The human releases them by deciding (no global pause,
            // no auto-apply). Delay accrues = realistic pressure.
            this._holdAffected();
          } else {
            // Recommendation: keep the gentle global pause + decision countdown.
            this.store.pause();
            this._startCountdown();
          }
        }

        if (!has) this._stopCountdown();
        this._hadImpact = has;
      },
      error: () => {},
    });
  }

  /** Merge the live impact into a stable display list: refresh cached rows,
   *  keep rows for a short grace window (and held rows indefinitely) so they
   *  don't flicker out, prune the rest, and sort by handle for a stable order. */
  private _rebuildStable(live: ImpactItem[]): void {
    const now = Date.now();
    for (const it of live) {
      this._cache.set(it.handle, it);
      this._seenAt.set(it.handle, now);
    }
    const out: ImpactItem[] = [];
    for (const [handle, item] of this._cache) {
      const fresh = now - (this._seenAt.get(handle) ?? 0) <= ImpactPanelComponent.GRACE_MS;
      if (fresh || this._held().has(handle)) {
        out.push(item);
      } else {
        this._cache.delete(handle);
        this._seenAt.delete(handle);
      }
    }
    out.sort((a, b) => a.handle - b.handle);
    this._stable.set(out);
  }

  private _stopPoll(): void {
    if (this._pollHandle !== null) {
      clearInterval(this._pollHandle);
      this._pollHandle = null;
    }
  }

  ngOnDestroy(): void {
    this._stopPoll();
    this._stopCountdown();
  }

  // ── Decision countdown → auto-apply recommended option ───────────────
  private _startCountdown(): void {
    this._stopCountdown();
    this.countdownRemaining.set(this.store.decisionCountdownSeconds());
    this._tickHandle = setInterval(() => {
      const rem = (this.countdownRemaining() ?? 0) - 1;
      if (rem <= 0) {
        this._autoDecide();
      } else {
        this.countdownRemaining.set(rem);
      }
    }, 1000);
  }

  private _stopCountdown(): void {
    if (this._tickHandle !== null) {
      clearInterval(this._tickHandle);
      this._tickHandle = null;
    }
    this.countdownRemaining.set(null);
  }

  /** Time's up: apply each train's recommended option (hold = safe default) and
   *  resume the run. Owner = 'ai' (the policy auto-applied because the human
   *  didn't intervene in time) — surfaces in the Decision Log as an autonomous
   *  decision, distinct from a human accept/override. */
  private _autoDecide(): void {
    for (const item of this.items()) {
      // Apply the recommended option; reroute uses the alternative-branch
      // override when available, otherwise hold is the safe fallback.
      const rec = item.recommended_action;
      if (!(rec === 'reroute' && this._apply(item, 'reroute', 'ai'))) {
        this.store.setOverride(item.handle, ImpactPanelComponent.STOP, 'ai');
      }
      this.dismiss(item.handle);
    }
    this._stopCountdown();
    if (!this.store.episodeDone()) {
      this.store.play(this.store.activePolicy(), this.store.playSpeed());
    }
  }

  private dismiss(handle: number): void {
    this.applied.update((s) => new Set(s).add(handle));
    // The human decided for this train → it's no longer a system hold.
    if (this._held().has(handle)) {
      this._held.update((s) => { const n = new Set(s); n.delete(handle); return n; });
    }
    if (this.items().length === 0) this._stopCountdown();
  }

  toggleCollapsed(): void {
    this.collapsed.update((v) => !v);
  }

  agentColor(handle: number): string {
    return this.colors.getColorSolid(handle);
  }

  // ── Co-Learning reciprocity: AI feedback on the human's PROPOSED option ──
  // Hovering an option forward-simulates that choice (read-only) and shows
  // the consequence, so the human gets feedback before committing.
  readonly optionFeedback = signal<Record<string, { loading: boolean; summary: string }>>({});
  readonly hoveredOpt = signal<{ handle: number; action: string; label: string } | null>(null);

  /** Cache key includes the step so feedback invalidates as the sim advances
   *  (during the Co-Learning decision moment the run is paused → key stable). */
  private optKey(handle: number, action: string): string {
    return `${handle}:${action}:${this.store.elapsedSteps()}`;
  }

  /** The consequence line for whatever option is currently hovered. */
  readonly hoveredFeedback = computed<{ loading: boolean; summary: string } | null>(() => {
    const h = this.hoveredOpt();
    if (!h) return null;
    return this.optionFeedback()[this.optKey(h.handle, h.action)] ?? null;
  });

  onOptionHover(item: ImpactItem, opt: ImpactOption): void {
    this.hoveredOpt.set({ handle: item.handle, action: opt.action, label: opt.label });
    const sess = this.store.session();
    if (!sess || !opt.available) return;

    const key = this.optKey(item.handle, opt.action);
    if (this.optionFeedback()[key]) return; // cached for this step

    // "proceed" = stay on the current course (no deviation from baseline).
    if (opt.action === 'proceed') {
      this._setFeedback(key, { loading: false, summary: 'current course (no change)' });
      return;
    }
    const action: ActionInt | null =
      opt.action === 'hold' ? 4 :
      opt.action === 'reroute' ? ((item.reroute_action ?? null) as ActionInt | null) :
      null;
    if (action == null) {
      this._setFeedback(key, { loading: false, summary: '' });
      return;
    }

    this._setFeedback(key, { loading: true, summary: '' });
    this.api.whatIfOverride(sess.id, { [item.handle]: action }).subscribe({
      next: (r) => this._setFeedback(key, { loading: false, summary: r.summary }),
      error: () => this._setFeedback(key, { loading: false, summary: '' }),
    });
  }

  onOptionLeave(): void {
    this.hoveredOpt.set(null);
  }

  private _setFeedback(key: string, val: { loading: boolean; summary: string }): void {
    this.optionFeedback.update((m) => ({ ...m, [key]: val }));
  }

  /** Click a row → select the affected train (map overlay + cross-view highlight). */
  select(item: ImpactItem): void {
    this.store.selectedHandle.set(item.handle);
  }

  /** Hover a row → highlight the affected train across views. */
  onEnter(item: ImpactItem): void {
    this.store.setAgentHoverAgents([item.handle]);
  }

  onLeave(): void {
    this.store.clearAgentHoverAgents();
  }

  /** Apply a chosen option for a train. Stops the countdown (human decided). */
  applyOption(item: ImpactItem, action: 'hold' | 'reroute' | 'proceed'): void {
    this.store.selectedHandle.set(item.handle);
    if (!this._apply(item, action)) {
      // Reroute requested but no branch action available → surface the train in
      // the map overlay so the human can pick a branch manually; keep the item.
      this.store.selectedHandle.set(item.handle);
      this._stopCountdown();
      return;
    }
    this._stopCountdown();
    this.dismiss(item.handle);

    // Co-Learning reciprocity, step 2: once this decision is implemented AND
    // nothing else is pending, this is the natural moment to reflect on it —
    // nudge the reflection panel open. This ADDS to (does not replace) the
    // manual "Reflect now" trigger: the human can still open/close it anytime,
    // this just offers it at the best natural opportunity.
    if (this.modeBehavior().reflectAfterDecision && this.items().length === 0) {
      this.store.reflectionRequested.set(true);
    }
  }

  /** Apply an action's override. Returns false if reroute had no branch action
   *  (so the caller can fall back to manual selection without dismissing).
   *  `owner` threads the decision-log attribution: 'human' for a click, 'ai'
   *  for the countdown auto-decide path. */
  private _apply(
    item: ImpactItem,
    action: 'hold' | 'reroute' | 'proceed',
    owner: 'human' | 'ai' = 'human',
  ): boolean {
    if (action === 'hold') {
      this.store.setOverride(item.handle, ImpactPanelComponent.STOP, owner);
      return true;
    }
    if (action === 'proceed') {
      this.store.clearOverride(item.handle, owner);
      return true;
    }
    // reroute: apply the alternative-branch override (fires at the next switch).
    if (item.reroute_action != null) {
      this.store.setOverride(item.handle, item.reroute_action, owner);
      return true;
    }
    return false;
  }

  /** Select the affected train to inspect/decide (neutral framing). */
  inspect(item: ImpactItem): void {
    this.store.selectedHandle.set(item.handle);
    this._stopCountdown();
  }
}
