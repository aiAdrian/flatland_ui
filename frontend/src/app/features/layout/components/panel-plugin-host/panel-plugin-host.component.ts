import { Component, Input } from '@angular/core';
import { PanelInstance } from '../../../../core/layout';

@Component({
  selector: 'app-panel-plugin-host',
  standalone: true,
  templateUrl: './panel-plugin-host.component.html',
  styleUrl: './panel-plugin-host.component.scss',
})
export class PanelPluginHostComponent {
  @Input({ required: true }) panel!: PanelInstance;
}
