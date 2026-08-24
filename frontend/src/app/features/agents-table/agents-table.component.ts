import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  HostBinding,
  Input,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { AgentColorService } from '../../core/agent-color.service';
import { TrainActionService } from '../../core/dispatch/train-action.service';
import { AgentDTO } from '../../core/models';

/**
 * Trains — v2 · Dispositionstabelle.
 *
 * Spec: docs/plans/widget-agents-table.md. Variant of the `agents` role
 * (docs/plans/widget-variants-versioning.md), built after the HMI review of
 * 2026-08-22: the operator had to read the left column, the map and the right
 * column and carry a train number across all three. Here one train is one row,
 * with its situation and its available action side by side.
 *
 * Mode-aware through `store.optionPresentation()` — the same projection every
 * other options surface reads; no parallel flag (CLAUDE.md guardrail).
 * Acting goes through `TrainActionService` with origin `'table'`, so a decision
 * taken here lands in the same audit trail as one taken in the roster or on the
 * map, and is distinguishable from it.
 */

type RowGroup = 'moving' | 'waiting' | 'done';

export interface TrainRow {
  agent: AgentDTO;
  handle: number;
  color: string;
  group: RowGroup;
  statusLabel: string;
  malfunctionSteps: number | null;
  /** What is going on with this train, in one phrase. Empty = nothing to say. */
  message: string;
  /** Scheduled step this row is measured against (arrival, or departure while waiting). */
  scheduleLabel: string;
  scheduleValue: string;
  /** Slack against that schedule ("noch 43" / "+12 spät"). */
  slack: string;
  slackLate: boolean;
  nextSwitch: string;
  options: Array<{
    action: number;
    label: string;
    /** The override this operator has set — click again to release it. */
    isMine: boolean;
    /** The AI's recommendation for this train, where one exists (Recommendation
     *  mode only). Never a guess — see `_optionsFor`. */
    isAiRecommended: boolean;
  }>;
  inConflict: boolean;
}

@Component({
  selector: 'app-agents-table',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './agents-table.component.html',
  styleUrl: './agents-table.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AgentsTableComponent {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  readonly store = inject(SessionStore);
  private readonly colors = inject(AgentColorService);
  private readonly trainActions = inject(TrainActionService);

  /** Mode framing. `recommended` marks the AI's recommendation for a train where
   *  one exists; `neutral` (Co-Learning) shows the options as equal choices so
   *  the operator forms their own view first. `none` (Director) never renders —
   *  the widget is not offered there — but the branch is stated, not assumed. */
  readonly modeBehavior = computed(() => {
    switch (this.store.optionPresentation()) {
      case 'recommended':
        return {
          markAiPlan: true,
          hint: '★ = Empfehlung der KI für diesen Zug · rot = dein gesetzter Eingriff',
        };
      case 'neutral':
        return {
          markAiPlan: false,
          hint: 'Optionen gleichwertig — du entscheidest zuerst · rot = dein gesetzter Eingriff',
        };
      case 'none':
        return { markAiPlan: false, hint: '' };
    }
  });

  readonly conflictsOnly = signal(false);
  toggleConflictsOnly(): void {
    this.conflictsOnly.update((v) => !v);
  }

  readonly conflictCount = computed(() => this.store.conflictHandles().size);
  readonly totalCount = computed(() => this.store.agents().length);

  readonly rows = computed<TrainRow[]>(() => {
    const conflicts = this.store.conflictHandles();
    const impact = this.store.impact();
    const filtered = this.conflictsOnly()
      ? this.store.agents().filter((a) => conflicts.has(a.handle))
      : this.store.agents();

    return filtered
      .map((a) => this._toRow(a, conflicts.has(a.handle), impact))
      .sort((x, y) => {
        // Conflicts first, then the tightest deadline — the order the operator
        // would work the list in anyway.
        if (x.inConflict !== y.inConflict) return x.inConflict ? -1 : 1;
        const gx = GROUP_ORDER[x.group];
        const gy = GROUP_ORDER[y.group];
        if (gx !== gy) return gx - gy;
        const tx = x.agent.time_to_deadline ?? Number.POSITIVE_INFINITY;
        const ty = y.agent.time_to_deadline ?? Number.POSITIVE_INFINITY;
        return tx - ty;
      });
  });

  onAction(handle: number, action: number): void {
    this.trainActions.toggle(handle, action, 'table');
  }

  onRowClick(handle: number): void {
    this.store.toggleAgentSelection(handle);
  }

  isSelected(handle: number): boolean {
    return this.store.selectedHandles().has(handle);
  }

  // ── row construction ──────────────────────────────────────────────────────

  private _toRow(
    a: AgentDTO,
    inConflict: boolean,
    impact: ReturnType<SessionStore['impact']>,
  ): TrainRow {
    const group = this._groupOf(a);
    const malfunctioning = this.store.isMalfunctioning(a);
    const waiting = group === 'waiting';

    return {
      agent: a,
      handle: a.handle,
      color: this.colors.getColor(a.handle, this.isSelected(a.handle) ? 'focus' : 'default'),
      group,
      statusLabel: STATUS_LABEL[group],
      malfunctionSteps: malfunctioning ? (a.malfunction_remaining ?? 0) : null,
      message: this._messageFor(a, malfunctioning, impact),
      scheduleLabel: waiting ? 'Abf.' : 'Ank.',
      scheduleValue: String((waiting ? a.earliest_departure : a.latest_arrival) ?? '–'),
      slack: this._slack(a, waiting),
      slackLate: !waiting && (a.time_to_deadline ?? 0) < 0,
      nextSwitch: a.next_decision
        ? `${a.next_decision.cell_type}${a.position ? ` (${a.position[0]}, ${a.position[1]})` : ''}`
        : '—',
      options: this._optionsFor(a, impact),
      inConflict,
    };
  }

  /**
   * The action cell.
   *
   * `isAiRecommended` is only ever set from a real AI recommendation. There is
   * deliberately **no** per-option "the plan would go this way" marker: the
   * backend's `next_decision` walks the track to the next switch and lists the
   * branches that physically exist (`cell_classifier.lookahead_to_decision`) —
   * its `path` ends *at* the decision point and says nothing about which branch
   * a plan takes. Marking one anyway would be an invented signal.
   *
   * What is real is the impact analysis: for a train a disruption blocks it
   * names `recommended_action` (+ `reroute_action`). That, and only that, gets
   * the star — and only in Recommendation mode. A train with no AI
   * recommendation right now simply shows none, which is the truth.
   */
  private _optionsFor(
    a: AgentDTO,
    impact: ReturnType<SessionStore['impact']>,
  ): TrainRow['options'] {
    const recommendedAction = this.modeBehavior().markAiPlan
      ? this._recommendedActionFor(a.handle, impact)
      : null;

    return (a.next_decision?.options ?? []).map((opt) => ({
      action: opt.action,
      label: opt.label,
      isMine: this.trainActions.isActive(a.handle, opt.action),
      isAiRecommended: recommendedAction != null && opt.action === recommendedAction,
    }));
  }

  /** The AI's recommended action int for this train, if the impact analysis has
   *  one. `hold` maps to STOP; `reroute` to the alternative-branch action. */
  private _recommendedActionFor(
    handle: number,
    impact: ReturnType<SessionStore['impact']>,
  ): number | null {
    const item = impact.find((i) => i.handle === handle);
    if (!item) return null;
    if (item.recommended_action === 'hold') return STOP_ACTION;
    if (item.recommended_action === 'reroute') return item.reroute_action ?? null;
    return null;
  }

  /** One phrase for what is going on. Blocked-by comes from the impact
   *  analysis, which is the only place that knows it. */
  private _messageFor(
    a: AgentDTO,
    malfunctioning: boolean,
    impact: ReturnType<SessionStore['impact']>,
  ): string {
    const parts: string[] = [];

    if (malfunctioning) {
      // "Remaining Steps" in the review sketch was this countdown. A true
      // steps-to-next-decision-point field does not exist in the DTO and is
      // flagged in the spec rather than invented here.
      parts.push(`Störung, noch ${a.malfunction_remaining ?? 0}`);
    }

    const blocked = impact.find((i) => i.handle === a.handle);
    if (blocked) {
      parts.push(`blockiert durch Zug ${blocked.blocked_by} · frei in ${blocked.clears_in_steps}`);
    }

    const blocking = impact.filter((i) => i.blocked_by === a.handle).map((i) => i.handle);
    if (blocking.length) {
      parts.push(`blockiert Zug ${blocking.join(', ')}`);
    }

    return parts.join(' · ');
  }

  private _slack(a: AgentDTO, waiting: boolean): string {
    if (waiting) {
      const eta = a.eta_to_depart;
      if (eta == null) return '–';
      return eta === 0 ? 'jetzt' : `in ${eta}`;
    }
    const t = a.time_to_deadline;
    if (t == null) return '–';
    return t >= 0 ? `noch ${t}` : `+${-t} spät`;
  }

  private _groupOf(a: AgentDTO): RowGroup {
    const state = String(a.state ?? '').toUpperCase();
    if (state === 'DONE') return 'done';
    if (this.store.isMalfunctioning(a)) return 'moving';
    if (state === 'WAITING' && (a.eta_to_depart ?? 0) > 0) return 'waiting';
    return 'moving';
  }
}

/** RailEnvActions.STOP_MOVING — same constant the impact panel uses. */
const STOP_ACTION = 4;

const GROUP_ORDER: Record<RowGroup, number> = { moving: 0, waiting: 1, done: 2 };

const STATUS_LABEL: Record<RowGroup, string> = {
  moving: 'unterwegs',
  waiting: 'wartet',
  done: 'angekommen',
};
