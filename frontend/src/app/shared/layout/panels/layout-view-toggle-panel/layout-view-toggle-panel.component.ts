import { Component, Input, inject } from '@angular/core';
import { LayoutViewToggleService } from '../../../../core/layout-view-toggle.service';

@Component({
  selector: 'app-layout-view-toggle-panel',
  standalone: true,
  templateUrl: './layout-view-toggle-panel.component.html',
  styleUrl: './layout-view-toggle-panel.component.scss',
})
export class LayoutViewTogglePanelComponent {
  @Input() panel?: any;
  @Input() embedded = true;

  readonly viewToggle = inject(LayoutViewToggleService);

  get title(): string {
    return String(this.panel?.title || 'Toggle View');
  }

  toggleFlatlandMap(): void {
    if (!this.viewToggle.flatlandMapAvailable()) {
      return;
    }

    this.viewToggle.toggle('flatland-map');
  }

  toggleMarey(): void {
    if (!this.viewToggle.mareyAvailable()) {
      return;
    }

    this.viewToggle.toggle('marey');
  }
}
