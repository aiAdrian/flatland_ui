import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input } from '@angular/core';
import { LeftSidebarComponent } from '../left-sidebar/left-sidebar.component';

@Component({
  selector: 'app-agents-panel',
  standalone: true,
  imports: [LeftSidebarComponent],
  templateUrl: './agents-panel.component.html',
  styleUrl: './agents-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AgentsPanelComponent {
  @Input() embedded = false;
  /** Zone rule: render without dispatch controls (see panel-plugin-host). */
  @Input() viewOnly = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }
}

