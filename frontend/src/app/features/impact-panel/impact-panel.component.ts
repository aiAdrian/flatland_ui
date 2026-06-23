import { Component, CUSTOM_ELEMENTS_SCHEMA, inject } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { AgentColorService } from '../../core/agent-color.service';
import { ImpactItem } from '../../core/events/event-types';

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
  templateUrl: './impact-panel.component.html',
  styleUrl: './impact-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ImpactPanelComponent {
  store = inject(SessionStore);
  private colors = inject(AgentColorService);

  private static readonly STOP = 4;

  agentColor(handle: number): string {
    return this.colors.getColorSolid(handle);
  }

  /** Apply the recommended action (Recommendation mode). */
  apply(item: ImpactItem): void {
    if (item.recommended_action === 'hold') {
      this.store.setOverride(item.handle, ImpactPanelComponent.STOP);
    } else {
      // Reroute needs a branch choice → select the train so the map overlay
      // shows its decision options.
      this.store.toggleAgentSelection(item.handle);
    }
  }

  /** Select the affected train to inspect/decide (neutral framing). */
  inspect(item: ImpactItem): void {
    this.store.toggleAgentSelection(item.handle);
  }
}
