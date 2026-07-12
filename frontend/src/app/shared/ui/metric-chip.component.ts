import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

/**
 * Presentational metric chip — label over a value, tinted by quality level.
 * Deck slides 1–2: the "Delay +2 min / Connection Excellent / Ripple Low"
 * sub-metrics under each strategy card. No store access; tokens only.
 */
@Component({
  selector: 'app-metric-chip',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="metric-chip" [class]="'level-' + level">
      <span class="metric-label">{{ label }}</span>
      <span class="metric-value">{{ value }}</span>
    </div>
  `,
  styleUrl: './metric-chip.component.scss',
})
export class MetricChipComponent {
  @Input() label = '';
  @Input() value = '';
  /** good → positive, fair → warn, low → error. `neutral` when no signal. */
  @Input() level: 'good' | 'fair' | 'low' | 'neutral' = 'neutral';
}
