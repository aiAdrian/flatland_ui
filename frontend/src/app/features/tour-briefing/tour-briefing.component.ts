import { Component, CUSTOM_ELEMENTS_SCHEMA, EventEmitter, Input, Output } from '@angular/core';
import { TourBriefing } from '../../core/demo/tour-briefings';

/**
 * Opening and closing page of a tour that carries a briefing
 * (`Tour.briefingId`). Full-pane like `app-mode-intro` / `app-demo-complete`,
 * so the session underneath does not show through.
 */
@Component({
  selector: 'app-tour-briefing',
  standalone: true,
  templateUrl: './tour-briefing.component.html',
  styleUrl: './tour-briefing.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class TourBriefingComponent {
  @Input({ required: true }) briefing!: TourBriefing;
  @Input({ required: true }) page!: 'opening' | 'closing';

  @Output() proceed = new EventEmitter<void>();
  @Output() restart = new EventEmitter<void>();
  @Output() exit = new EventEmitter<void>();
}
