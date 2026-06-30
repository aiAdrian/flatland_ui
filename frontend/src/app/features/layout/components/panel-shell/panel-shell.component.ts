import '@sbb-esta/lyne-elements/expansion-panel.js';

import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  HostBinding,
  Input,
  OnChanges,
  SimpleChanges,
  signal,
} from '@angular/core';
import { PanelInstance } from '../../../../core/layout';
import { PanelPluginHostComponent } from '../panel-plugin-host/panel-plugin-host.component';

@Component({
  selector: 'app-panel-shell',
  standalone: true,
  imports: [PanelPluginHostComponent],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './panel-shell.component.html',
  styleUrl: './panel-shell.component.scss',
})
export class PanelShellComponent implements OnChanges {
  @Input({ required: true }) panel!: PanelInstance;

  private currentPanelId: string | null = null;
  readonly expanded = signal(true);

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['panel'] || !this.panel) {
      return;
    }

    if (this.currentPanelId !== this.panel.id) {
      this.currentPanelId = this.panel.id;
      this.expanded.set(this.isCanvasPanel || !this.panel.collapsed);
    }
  }

  @HostBinding('attr.data-panel-type')
  get hostPanelType(): string | null {
    return this.panel?.type ?? null;
  }

  @HostBinding('attr.data-panel-zone')
  get hostPanelZone(): string | null {
    return this.panel?.zone ?? null;
  }

  @HostBinding('class.layout-panel-shell-host--canvas')
  get isCanvasPanel(): boolean {
    return this.panel?.type === 'flatland-map' || this.panel?.type === 'graphic-timetable';
  }

  @HostBinding('class.layout-panel-shell-host--accordion')
  get isAccordionPanel(): boolean {
    return !this.isCanvasPanel;
  }

  get expandedAttribute(): '' | null {
    return this.expanded() ? '' : null;
  }

  isExpanded(): boolean {
    return this.expanded();
  }

  toggleExpanded(): void {
    if (this.isCanvasPanel) {
      this.expanded.set(true);
      this.panel.collapsed = false;
      return;
    }

    const next = !this.expanded();
    this.expanded.set(next);
    this.panel.collapsed = !next;
  }
}
