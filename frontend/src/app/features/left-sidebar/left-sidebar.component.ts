import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  computed,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { SessionStore } from '../../core/session.store';
import { AgentColorService } from '../../core/agent-color.service';
import { TrainActionService } from '../../core/dispatch/train-action.service';
import { AgentDTO } from '../../core/models';

type AgentGroup = 'MOVING' | 'WAITING' | 'DONE';

@Component({
  selector: 'app-left-sidebar',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './left-sidebar.component.html',
  styleUrl: './left-sidebar.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class LeftSidebarComponent {
  store = inject(SessionStore);
  private agentColors = inject(AgentColorService);
  /** Acting on a train goes through the dispatch seam, never straight to the
   *  store — see core/dispatch/train-action.service.ts. */
  private trainActions = inject(TrainActionService);

  // Collapsed state per group (default: all open).
  readonly collapsed = signal<Record<AgentGroup, boolean>>({
    MOVING: false,   // header is decorative, not clickable
    WAITING: true,
    DONE: false,
  });

  readonly totalCount = computed(() => this.store.agents().length);

  // ── "Nur Konflikte" filter ────────────────────────────────────────────────
  // HMI review: "Alle Züge oder nur die mit Konflikt?" — the list showed
  // every train with no way to narrow it to the ones that need a decision.

  /** The conflict set is defined once in the store — the disposition table asks
   *  the same question and must get the same answer. */
  readonly conflictCount = computed(() => this.store.conflictHandles().size);

  readonly conflictsOnly = signal(false);

  toggleConflictsOnly(): void {
    this.conflictsOnly.update((v) => !v);
  }

  /** Narrow a group to the conflict set while the filter is on. */
  private applyConflictFilter(list: AgentDTO[]): AgentDTO[] {
    if (!this.conflictsOnly()) return list;
    const handles = this.store.conflictHandles();
    return list.filter((a) => handles.has(a.handle));
  }

  /** MOVING includes anyone currently *acting* on the map:
   *  READY_TO_DEPART, MOVING, STOPPED, MALFUNCTION. */
  readonly movingAgents = computed<AgentDTO[]>(() => {
    const list = this.applyConflictFilter(
      this.store.agents().filter((a) => this.isMovingGroupAgent(a)),
    );

    // Malfunctions first, then most urgent deadlines.
    return list.sort((a, b) => {
      const ma = this.isMalfunctioning(a) ? 0 : 1;
      const mb = this.isMalfunctioning(b) ? 0 : 1;
      if (ma !== mb) return ma - mb;

      const ta = a.time_to_deadline ?? Number.POSITIVE_INFINITY;
      const tb = b.time_to_deadline ?? Number.POSITIVE_INFINITY;
      return ta - tb;
    });
  });

  readonly waitingAgents = computed<AgentDTO[]>(() => {
    const list = this.applyConflictFilter(
      this.store.agents().filter((a) => this.isWaitingGroupAgent(a)),
    );

    return list.sort((a, b) => {
      const ea = a.earliest_departure ?? Number.POSITIVE_INFINITY;
      const eb = b.earliest_departure ?? Number.POSITIVE_INFINITY;
      return ea - eb;
    });
  });

  readonly doneAgents = computed<AgentDTO[]>(() => {
    const list = this.applyConflictFilter(
      this.store.agents().filter((a) => this.isDoneGroupAgent(a)),
    );
    return list.sort((a, b) => a.handle - b.handle);
  });

  /** Unfiltered — the header count must keep meaning the same when the
   *  "nur Konflikte" filter narrows the visible lists. */
  readonly activeCount = computed(
    () => this.store.agents().filter((a) => this.isMovingGroupAgent(a)).length,
  );

  /** Total delay across all overdue agents (sum), and how many are delayed.
   *  Used for the global header badge. */
  readonly delaySummary = computed(() => {
    const overdue = this.store.agents().filter((a) => (a.delay ?? 0) > 0);
    const totalDelay = overdue.reduce((sum, a) => sum + (a.delay ?? 0), 0);
    return { count: overdue.length, totalDelay };
  });

  toggleGroup(group: AgentGroup): void {
    if (group === 'MOVING') return; // not collapsible
    this.collapsed.update((c) => ({ ...c, [group]: !c[group] }));
  }

  agentColor(handle: number): string {
    const state = this.isSelected(handle) ? 'focus' : 'default';
    return this.agentColors.getColor(handle, state);
  }

  isSelected(handle: number): boolean {
    return this.store.selectedHandles().has(handle);
  }

  isNotificationHovered(handle: number): boolean {
    return this.store.notificationHoverHandles().has(handle);
  }

  onAgentMouseEnter(handle: number): void {
    this.store.setAgentHoverAgent(handle);
  }

  onAgentMouseLeave(): void {
    this.store.clearAgentHoverAgents();
  }


  toggleSelect(handle: number): void {
    this.store.toggleAgentSelection(handle);
  }

  onActionClick(handle: number, action: number, _isOverride: boolean): void {
    this.trainActions.toggle(handle, action, 'roster');
  }

  isOverrideOption(handle: number, action: number): boolean {
    return this.trainActions.isActive(handle, action);
  }

  // ── group semantics ───────────────────────────────────────────────
  //
  // UI has three operational groups:
  // - WAITING: not ready to depart yet
  // - MOVING: ready/active and not done, including stopped/malfunction
  // - DONE: completed
  //
  // Do not rely only on exact Flatland state strings. Some versions expose
  // malfunction/off-map variants. Those must still be visible under MOVING.
  isMalfunctioning(a: AgentDTO): boolean {
    return !!a.is_malfunctioning
      || (a.malfunction_remaining ?? 0) > 0
      || String(a.state ?? '').toUpperCase().includes('MALFUNCTION');
  }

  isDoneGroupAgent(a: AgentDTO): boolean {
    return String(a.state ?? '').toUpperCase() === 'DONE';
  }

  isWaitingGroupAgent(a: AgentDTO): boolean {
    if (this.isDoneGroupAgent(a)) return false;
    if (this.isMalfunctioning(a)) return false;

    const state = String(a.state ?? '').toUpperCase();

    // Off-map / not ready yet.
    // READY_TO_DEPART is NOT waiting; it belongs to MOVING.
    if (state === 'WAITING') {
      return (a.eta_to_depart ?? 0) > 0;
    }

    return false;
  }

  isMovingGroupAgent(a: AgentDTO): boolean {
    if (this.isDoneGroupAgent(a)) return false;
    if (this.isWaitingGroupAgent(a)) return false;

    // Everything active/not-done goes here:
    // READY_TO_DEPART, MOVING, STOPPED, MALFUNCTION,
    // MALFUNCTION_OFF_MAP, and future Flatland active states.
    return true;
  }

  // ── presentation helpers ──────────────────────────────────────────

  /** READY_TO_DEPART with the departure window already open. */
  isOutsideReady(a: AgentDTO): boolean {
    return a.state === 'READY_TO_DEPART' && (a.eta_to_depart ?? 0) === 0;
  }

  isOverdue(a: AgentDTO): boolean {
    return (a.delay ?? 0) > 0;
  }


  /** Background colour for the time-to-deadline badge.
   *  Goes grey → orange as intensity grows, then deep orange when overdue. */
  deadlineBadgeStyle(a: AgentDTO): { [key: string]: string } {
    const t = a.delay_color_intensity ?? 0;
    // Grey base #d2d2d2, warm orange target #f59e0b (Tailwind amber-500).
    const r = Math.round(210 + (245 - 210) * t);
    const g = Math.round(210 + (158 - 210) * t);
    const b = Math.round(210 + (11 - 210) * t);
    const fg = t > 0.5 ? '#fff' : '#333';
    return {
      background: `rgb(${r}, ${g}, ${b})`,
      color: fg,
    };
  }

  /** Format the time-to-deadline as `-12` or `+5`. */
  /** Steps of slack against the latest arrival.
   *
   *  Used to render as a bare "−80", which the HMI review read as a
   *  deficit ("−80 = ?"). It is the opposite: 80 steps still in hand. The sign
   *  alone cannot carry that, so the badge says which side of the deadline the
   *  train is on. */
  formatDeadlineDelta(a: AgentDTO): string {
    const t = a.time_to_deadline;
    if (t === null || t === undefined) return '–';
    if (t >= 0) return `noch ${t}`;   // slack left before latest arrival
    return `+${-t} spät`;             // past the latest arrival
  }

  deadlineTooltip(a: AgentDTO): string {
    const t = a.time_to_deadline;
    const target = a.latest_arrival ?? '–';
    if (t === null || t === undefined) return `Späteste Ankunft: ${target}`;
    return t >= 0
      ? `Noch ${t} Schritt(e) Puffer bis zur spätesten Ankunft (${target})`
      : `${-t} Schritt(e) über der spätesten Ankunft (${target})`;
  }

  /** True when one of the offered actions is the override currently set on this
   *  train — i.e. when the red styling appears and needs explaining. */
  hasOverrideOption(a: AgentDTO): boolean {
    return (a.next_decision?.options ?? []).some(
      (opt) => this.isOverrideOption(a.handle, opt.action),
    );
  }

  formatEta(a: AgentDTO): string {
    const eta = a.eta_to_depart;
    if (eta === null || eta === undefined) return '–';
    if (eta === 0) return 'now';
    return `in ${eta}`;
  }
}
