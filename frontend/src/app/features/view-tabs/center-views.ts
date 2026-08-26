import { Type } from '@angular/core';
import { PanelInstance } from '../../core/layout/models/layout.models';
import { FlatlandMapComponent } from '../flatland-map/flatland-map.component';
import { GraphicTimetableComponent } from '../graphic-timetable/graphic-timetable.component';
import { TimetableComponent } from '../timetable/timetable.component';
import { GoalAchievementPanelComponent } from '../../shared/layout/panels/goal-achievement-panel/goal-achievement-panel.component';

/**
 * A center "view" that can be a tab in the View-Tabs container. This registry is
 * the single source of truth: the tab list and the rendering both come from it,
 * so nothing is hardwired in the view-tabs template. Adding a new center view
 * (e.g. a power diagram) = one entry here — it then becomes selectable as a tab.
 *
 * `inputs` returns the per-view input bag passed via NgComponentOutlet, so each
 * component keeps its own input shape (e.g. goal-achievement needs `panel`)
 * without the container knowing about it.
 */
export interface CenterViewDef {
  /** Panel `type` key (matches widget-catalog / panel-plugin-host). */
  type: string;
  /** Short tab label. */
  label: string;
  component: Type<unknown>;
  inputs?: (ctx: { panel: PanelInstance | null }) => Record<string, unknown>;
}

export const CENTER_VIEWS: CenterViewDef[] = [
  { type: 'flatland-map', label: 'Map', component: FlatlandMapComponent },
  { type: 'marey', label: 'Marey', component: GraphicTimetableComponent },
  { type: 'timetable', label: 'Timetable', component: TimetableComponent, inputs: () => ({ embedded: true }) },
  {
    type: 'goal-achievement',
    label: 'Goal Achievement',
    component: GoalAchievementPanelComponent,
    inputs: ({ panel }) => ({ embedded: true, panel }),
  },
];

export function centerViewByType(type: string): CenterViewDef | undefined {
  return CENTER_VIEWS.find((v) => v.type === type);
}
