import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, inject } from '@angular/core';
import { InfrastructureBuilderStoreService } from '../../services/infrastructure-builder-store.service';

@Component({
  selector: 'app-builder-validation-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './builder-validation-panel.component.html',
  styleUrl: './builder-validation-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class BuilderValidationPanelComponent {
  readonly store = inject(InfrastructureBuilderStoreService);
}
