import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, OnDestroy, computed, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { ApiService } from '../../core/api.service';
import { AgentColorService } from '../../core/agent-color.service';
import { WhatIfResult, WhatIfTrainOutcome } from '../../core/events/event-types';
import { ActionInt } from '../../core/models';

/** One selectable action the human can propose for the target train. */
interface ActionChoice {
  action: ActionInt;
  label: string;
}

/**
 * Widget B1 — What-if Compare ("My solution vs. AI").
 *
 * The §3.3 dual-path core: the human formulates their own action for the
 * selected train and it is forward-simulated side-by-side with the AI's plan,
 * before committing. Reuses the existing what-if backend (api.whatIfOverride →
 * baseline = AI course, branch = human-influenced).
 *
 * Layout: the SELECTED train's own fate is primary (top, big) — "local action";
 * the system-wide KPIs stay as secondary context (bottom, smaller) — "global
 * effect". The teaching point is the link between the two, so neither is dropped.
 *
 * Convention (AI4REALNET A3S/TraceRL): human = blue, AI = yellow. The same two
 * branch paths are drawn on the map via `store.whatIfPreview` (blue = My plan,
 * yellow = AI plan).
 *
 * Mode-aware via `modeBehavior` (one component, not three):
 *  - recommendation: compare against the current course incl. any active suggestion.
 *  - co-learning:    neutral dual-path, no winner marked; committing feeds reflection.
 *  - director:       read-only supervisory what-if (Commit hidden — AI owns actuation).
 */
@Component({
  selector: 'app-whatif-compare',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './whatif-compare.component.html',
  styleUrl: './whatif-compare.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class WhatifCompareComponent implements OnDestroy {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  store = inject(SessionStore);
  private api = inject(ApiService);
  private colors = inject(AgentColorService);

  /** Actions the human can propose. Flatland: 4=STOP(hold), 2=FORWARD, 1=LEFT, 3=RIGHT. */
  readonly actionChoices: ActionChoice[] = [
    { action: 4, label: 'Hold' },
    { action: 2, label: 'Forward' },
    { action: 1, label: 'Left' },
    { action: 3, label: 'Right' },
  ];

  /** The human's currently proposed action ("My plan"). */
  readonly chosenAction = signal<ActionInt | null>(null);
  readonly result = signal<WhatIfResult | null>(null);
  readonly loading = signal(false);
  readonly failed = signal(false);
  /** True once a committed override lands, so the UI can confirm. */
  readonly committed = signal(false);

  /** Target train = the globally selected one (set from agents/impact/map). */
  readonly targetHandle = computed(() => this.store.selectedHandle());

  /** Per-mode behaviour — framing + whether "My plan" can be committed. */
  readonly modeBehavior = computed(() => {
    switch (this.store.interactionMode()) {
      case 'recommendation':
        return { canCommit: true, aiLabel: 'AI plan (current + suggestion)', note: 'Compare your action against the AI’s current course.' };
      case 'co-learning':
        return { canCommit: true, aiLabel: 'AI plan', note: 'Formulate your own action and compare it with the AI — neither is marked “right”.' };
      case 'director':
        return { canCommit: false, aiLabel: 'AI plan (autonomous)', note: 'Supervisory what-if — inspect a branch; the AI keeps actuation under the directive.' };
    }
  });

  /** Colour dot for the target train (matches map/roster). */
  targetColor(): string {
    const h = this.targetHandle();
    return h == null ? 'transparent' : this.colors.getColor(h, 'default');
  }

  targetLabel(): string {
    const h = this.targetHandle();
    return h == null ? '' : `Train ${h}`;
  }

  isChosen(action: ActionInt): boolean {
    return this.chosenAction() === action;
  }

  /** Human picks an action → forward-simulate My plan vs AI plan (read-only). */
  choose(action: ActionInt): void {
    const sess = this.store.session();
    const h = this.targetHandle();
    if (!sess || h == null) return;

    this.chosenAction.set(action);
    this.committed.set(false);
    this.failed.set(false);
    this.loading.set(true);
    this.result.set(null);
    // Drop any stale map preview while we re-simulate; replaced on result.
    this.store.whatIfPreview.set(null);

    this.api.whatIfOverride(sess.id, { [h]: action }).subscribe({
      next: (r) => {
        this.result.set(r);
        this.loading.set(false);
        // Push the two branch paths to the map: blue = My plan, yellow = AI plan.
        if (r.branch_trajectories && r.baseline_trajectories) {
          this.store.whatIfPreview.set({
            baseline: r.baseline_trajectories,
            branch: r.branch_trajectories,
            handles: r.handles ?? [h],
          });
        }
      },
      error: () => {
        this.failed.set(true);
        this.loading.set(false);
        this.store.whatIfPreview.set(null);
      },
    });
  }

  /** Commit "My plan" as an override (not offered in Director). Feeds reflection. */
  commit(): void {
    const h = this.targetHandle();
    const action = this.chosenAction();
    if (h == null || action == null || !this.modeBehavior().canCommit) return;
    this.store.setOverride(h, action);
    this.committed.set(true);
    // The override is now real; drop the what-if map overlay so the live
    // trajectory takes over.
    this.store.whatIfPreview.set(null);
  }

  ngOnDestroy(): void {
    // Same discipline as recommendations-panel previewOff: never leave a
    // dangling what-if overlay on the map when the widget goes away.
    this.store.whatIfPreview.set(null);
  }

  // ── Train-outcome presentation helpers (primary block) ────────────────

  /** Signed delay delta of My plan vs AI plan for the selected train. */
  trainDelayDelta(t: WhatIfTrainOutcome): number {
    return t.branch.delay - t.baseline.delay;
  }

  /** Whether My plan flips arrival vs the AI plan (improvement or regression). */
  trainArrivesChanged(t: WhatIfTrainOutcome): boolean {
    return t.branch.arrived !== t.baseline.arrived;
  }
  /** Whether My plan flips deadlock vs the AI plan. */
  trainDeadlockChanged(t: WhatIfTrainOutcome): boolean {
    return t.branch.deadlocked !== t.baseline.deadlocked;
  }

  /** Signed delta with an arrow; the template binds .good/.bad per metric. */
  deltaArrow(value: number): string {
    if (value > 0) return '▲';
    if (value < 0) return '▼';
    return '·';
  }

  /** Signed integer delta with explicit + sign for non-zero positives. */
  signedDelta(value: number): string {
    if (value > 0) return `+${value}`;
    return `${value}`;
  }
}
