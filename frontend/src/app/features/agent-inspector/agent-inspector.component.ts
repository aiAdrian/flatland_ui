import { Component, CUSTOM_ELEMENTS_SCHEMA, computed, inject } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { AgentDTO } from '../../core/models';
import { AgentColorService } from '../../core/agent-color.service';
import { TrainActionService } from '../../core/dispatch/train-action.service';

@Component({
  selector: 'app-agent-inspector',
  standalone: true,
  templateUrl: './agent-inspector.component.html',
  styleUrl: './agent-inspector.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AgentInspectorComponent {
  store = inject(SessionStore);
  private agentColors = inject(AgentColorService);
  /** Acting goes through the dispatch seam, never straight to the store. */
  private trainActions = inject(TrainActionService);

  readonly activeAgent = computed<AgentDTO | null>(() => {
    const agents = this.store.agents();

    // 1) Explicit click/selection wins.
    const selected = this.store.selectedHandle();
    if (selected != null) {
      return agents.find((a) => a.handle === selected) ?? null;
    }

    // 2) Hover/cross-highlight fallback.
    const hovered = Array.from(this.store.notificationHoverHandles?.() ?? []);
    if (hovered.length > 0) {
      return agents.find((a) => a.handle === hovered[0]) ?? null;
    }

    return null;
  });

  agentColor(handle: number): string {
    return this.agentColors.getColor(handle, 'default');
  }

  isMalfunctioning(a: AgentDTO | null): boolean {
    if (!a) return false;
    return !!a.is_malfunctioning
      || (a.malfunction_remaining ?? 0) > 0
      || String(a.state ?? '').includes('MALFUNCTION');
  }

  clearSelection() {
    this.store.clearSelection();
  }

  /** Absolute step at which a malfunctioning train is expected to resume. */
  resumeStep(a: AgentDTO): number {
    return this.store.elapsedSteps() + Math.max(0, a.malfunction_remaining ?? 0);
  }

  /** Apply or clear a per-agent override from the overlay action buttons. */
  onActionClick(handle: number, action: number, _isOverride: boolean): void {
    this.trainActions.toggle(handle, action, 'inspector');
  }

  isOverrideOption(handle: number, action: number): boolean {
    return this.trainActions.isActive(handle, action);
  }
}
