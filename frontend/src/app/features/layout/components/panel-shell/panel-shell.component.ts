import '@sbb-esta/lyne-elements/expansion-panel.js';

import { Component, CUSTOM_ELEMENTS_SCHEMA, Input } from '@angular/core';
import { PanelInstance } from '../../../../core/layout';

@Component({
  selector: 'app-panel-shell',
  standalone: true,
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './panel-shell.component.html',
  styleUrl: './panel-shell.component.scss',
})
export class PanelShellComponent {
  @Input({ required: true }) panel!: PanelInstance;

  get expandedAttribute(): '' | null {
    return this.panel.collapsed ? null : '';
  }
}
