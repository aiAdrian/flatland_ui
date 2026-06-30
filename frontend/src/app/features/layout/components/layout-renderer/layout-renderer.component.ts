import { CommonModule } from '@angular/common';
import { Component, computed, inject } from '@angular/core';
import {
  LayoutColumn,
  LayoutStoreService,
  LayoutZone,
  PanelInstance,
} from '../../../../core/layout';
import { PanelShellComponent } from '../panel-shell/panel-shell.component';

@Component({
  selector: 'app-layout-renderer',
  standalone: true,
  imports: [
    CommonModule,
    PanelShellComponent,
  ],
  templateUrl: './layout-renderer.component.html',
  styleUrl: './layout-renderer.component.scss',
})
export class LayoutRendererComponent {
  readonly store = inject(LayoutStoreService);

  readonly zones: LayoutZone[] = ['left', 'center', 'right'];

  readonly gridTemplateColumns = computed(() => {
    const columns = this.store.layout().columns.filter((column) =>
      this.zones.includes(column.zone),
    );

    if (!columns.length) {
      return '320px minmax(320px, 1fr) 320px';
    }

    return columns.map((column) => this.toCssWidth(column.width)).join(' ');
  });

  panelsByZone(zone: LayoutZone): PanelInstance[] {
    return this.store.panelsByZone(zone);
  }

  columnByZone(zone: LayoutZone): LayoutColumn | undefined {
    return this.store.layout().columns.find((column) => column.zone === zone);
  }

  trackPanel(_index: number, panel: PanelInstance): string {
    return panel.id;
  }

  private toCssWidth(width: number | string): string {
    return typeof width === 'number' ? `${width}px` : width;
  }
}
