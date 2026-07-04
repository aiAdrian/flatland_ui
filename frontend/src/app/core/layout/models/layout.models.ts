import { InteractionMode } from '../../events/event-types';

export type LayoutZone =
  | 'left'
  | 'center'
  | 'right'
  | 'bottom'
  | 'floating';

export type PanelSizeMode =
  | 'auto'
  | 'fixed'
  | 'fill';

export interface PanelCapabilities {
  collapsible: boolean;
  movable: boolean;
  resizable: boolean;
  closable: boolean;
  configurable: boolean;
}

export interface PanelDefinition {
  type: string;
  title: string;
  description?: string;
  icon?: string;
  defaultZone: LayoutZone;
  defaultHeight?: number;
  defaultWidth?: number;
  capabilities: PanelCapabilities;
  /**
   * Interaction modes in which this panel type is offered. Omitted / 'all' =
   * available in every mode. Availability is a property of the panel *type*,
   * not of a placed instance; per-mode *behaviour* is handled inside the
   * component (read `store.interactionMode()`), not here.
   *
   * Sketch only — declared for the mode-scoped-layout resolver to consume when
   * building a mode's default layout. See docs/reference/panel-mode-matrix.md.
   */
  availableModes?: InteractionMode[] | 'all';
  /**
   * Function class of the panel (e.g. 'trust', 'prediction', 'control',
   * 'capitalization', 'event', 'context'). From the interaction-framework
   * taxonomy; a tile's `kind` is set in its spec
   * (docs/plans/tile-<id>-<slug>.md). Sketch — not yet consumed by a resolver.
   */
  kind?: string;
  /**
   * Detail level the panel offers: 'overview' (at-a-glance), 'detail'
   * (drill-down), or 'overview-detail' (a badge that expands). Sketch.
   */
  granularity?: 'overview' | 'detail' | 'overview-detail';
}

export interface PanelInstance {
  id: string;
  type: string;
  title: string;
  zone: LayoutZone;
  order: number;
  collapsed: boolean;
  hidden: boolean;
  height?: number;
  width?: number;
  sizeMode: PanelSizeMode;
  config?: Record<string, unknown>;
}

export interface LayoutColumn {
  zone: LayoutZone;
  width: number | string;
  minWidth?: number;
  maxWidth?: number;
  resizable: boolean;
}

export interface LayoutState {
  version: number;
  columns: LayoutColumn[];
  panels: PanelInstance[];
  selectedPanelId?: string;
}

export const DEFAULT_PANEL_CAPABILITIES: PanelCapabilities = {
  collapsible: true,
  movable: true,
  resizable: false,
  closable: false,
  configurable: false,
};

export function createDefaultLayoutState(): LayoutState {
  return {
    version: 1,
    columns: [
      {
        zone: 'left',
        width: 320,
        minWidth: 240,
        maxWidth: 480,
        resizable: true,
      },
      {
        zone: 'center',
        width: '1fr',
        minWidth: 320,
        resizable: false,
      },
      {
        zone: 'right',
        width: 320,
        minWidth: 240,
        maxWidth: 480,
        resizable: true,
      },
    ],
    panels: [],
  };
}
