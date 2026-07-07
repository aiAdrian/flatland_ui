import { Component, CUSTOM_ELEMENTS_SCHEMA, EventEmitter, Output, signal } from '@angular/core';
import { INTERACTION_MODES } from '../../core/interaction-modes';

/**
 * Help & About overlay. Two tabs: "About" (what the project is) and "Help"
 * (how to use it). Content is deliberately short — the goal is orientation,
 * not a manual. Mode one-liners mirror the header switcher so they stay
 * consistent with the app.
 */
@Component({
  selector: 'app-help-about',
  standalone: true,
  templateUrl: './help-about.component.html',
  styleUrl: './help-about.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class HelpAboutComponent {
  @Output() closed = new EventEmitter<void>();

  readonly tab = signal<'about' | 'help'>('about');

  readonly modes = INTERACTION_MODES;

  close(): void {
    this.closed.emit();
  }
}
