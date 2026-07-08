import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InfrastructureBuilderTool, MVP_TOOLS } from '../../models/tool.model';
import { InfrastructureBuilderStoreService } from '../../services/infrastructure-builder-store.service';
import { BuilderAgentPanelComponent } from '../builder-agent-panel/builder-agent-panel.component';
import { BuilderExportPanelComponent } from '../builder-export-panel/builder-export-panel.component';
import { BuilderValidationPanelComponent } from '../builder-validation-panel/builder-validation-panel.component';

@Component({
  selector: 'app-builder-left-sidebar',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    BuilderAgentPanelComponent,
    BuilderExportPanelComponent,
    BuilderValidationPanelComponent,
  ],
  templateUrl: './builder-left-sidebar.component.html',
  styleUrl: './builder-left-sidebar.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class BuilderLeftSidebarComponent {
  readonly store = inject(InfrastructureBuilderStoreService);
  readonly tools = MVP_TOOLS;
  readonly draftWidth = signal(this.store.scene().grid.width);
  readonly draftHeight = signal(this.store.scene().grid.height);

  applyGrid(): void {
    this.store.updateGrid(this.draftWidth(), this.draftHeight());
  }

  resetGrid(): void {
    this.store.newScene(this.draftWidth(), this.draftHeight());
  }

  selectTool(event: Event): void {
    const value = (event.target as HTMLElement & { value?: string }).value;
    if (this.tools.some((tool) => tool.id === value)) {
      this.store.activeTool.set(value as InfrastructureBuilderTool);
    }
  }
}
