import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface ReasoningItem {
  /** Bold lead-in, e.g. "Protects a critical connection". */
  title: string;
  /** Supporting sentence. */
  detail: string;
}

/**
 * Presentational "why" list — check-bulleted reasons behind a recommendation.
 * Deck slides 1–2: the "WHY OPTION B / WHY THIS STRATEGY" column. Reused later
 * by the agent-inspector (plan Phase 3). No store access; tokens only.
 */
@Component({
  selector: 'app-reasoning-list',
  standalone: true,
  imports: [CommonModule],
  template: `
    <ul class="reasoning-list">
      @for (item of items; track item.title) {
        <li class="reason">
          <svg class="reason-mark" viewBox="0 0 16 16" aria-hidden="true">
            <path d="M3.5 8.5l3 3 6-6.5" fill="none" stroke="currentColor"
                  stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span class="reason-body">
            <span class="reason-title">{{ item.title }}</span>
            <span class="reason-detail">{{ item.detail }}</span>
          </span>
        </li>
      }
    </ul>
  `,
  styleUrl: './reasoning-list.component.scss',
})
export class ReasoningListComponent {
  @Input() items: ReasoningItem[] = [];
}
