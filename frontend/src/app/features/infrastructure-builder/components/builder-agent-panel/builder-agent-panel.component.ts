import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InfrastructureBuilderStoreService } from '../../services/infrastructure-builder-store.service';

@Component({
  selector: 'app-builder-agent-panel',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './builder-agent-panel.component.html',
  styleUrl: './builder-agent-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class BuilderAgentPanelComponent {
  readonly store = inject(InfrastructureBuilderStoreService);
}
