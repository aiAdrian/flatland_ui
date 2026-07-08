import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, inject } from '@angular/core';
import { InfrastructureBuilderStoreService } from '../../services/infrastructure-builder-store.service';

@Component({
  selector: 'app-builder-inspector',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './builder-inspector.component.html',
  styleUrl: './builder-inspector.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class BuilderInspectorComponent {
  readonly store = inject(InfrastructureBuilderStoreService);
}
