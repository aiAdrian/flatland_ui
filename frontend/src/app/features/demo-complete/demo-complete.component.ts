import { Component, CUSTOM_ELEMENTS_SCHEMA, EventEmitter, Output } from '@angular/core';

/**
 * Guided-demo completion screen, shown full-pane once all three modes'
 * surveys are done — mirrors app-mode-intro (full-pane, not a thin banner)
 * so the finished dashboard/session state doesn't show through underneath.
 */
@Component({
  selector: 'app-demo-complete',
  standalone: true,
  templateUrl: './demo-complete.component.html',
  styleUrl: './demo-complete.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class DemoCompleteComponent {
  @Output() restart = new EventEmitter<void>();
  @Output() exit = new EventEmitter<void>();
}
