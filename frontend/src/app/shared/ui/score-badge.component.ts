import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Presentational score badge — big number `/100` with an optional state.
 * Used by the scored strategy cards (deck slides 1–2: "Score 84 /100 ·
 * ACTIVE · RECOMMENDED"). No store access; colours come from app tokens only.
 */
@Component({
  selector: 'app-score-badge',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="score-badge" [class]="'is-' + state">
      <span class="score-num">{{ score }}</span><span class="score-den">/100</span>
      @if (label) {
        <span class="score-label">{{ label }}</span>
      }
    </div>
  `,
  styleUrl: './score-badge.component.scss',
})
export class ScoreBadgeComponent {
  /** 0–100. */
  @Input() score = 0;
  /** Visual emphasis. `recommended`/`active` use the positive cluster. */
  @Input() state: 'neutral' | 'recommended' | 'active' = 'neutral';
  /** Optional small caption under the number (e.g. "ACTIVE · RECOMMENDED"). */
  @Input() label = '';
}
