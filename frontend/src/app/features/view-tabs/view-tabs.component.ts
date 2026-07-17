import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, computed, effect, inject, signal } from '@angular/core';
import { NgComponentOutlet } from '@angular/common';
import { PanelInstance } from '../../core/layout/models/layout.models';
import { SessionStore } from '../../core/session.store';
import { InteractionMode } from '../../core/events/event-types';
import { CENTER_VIEWS, CenterViewDef, centerViewByType } from './center-views';

/**
 * Default center view per interaction mode. Recommendation & Co-Learning work on
 * concrete trains/conflicts → the Map (Co-Learning's "my plan vs AI" compare is
 * drawn on the map, blue=you/yellow=AI). Director supervises goals at scale →
 * the Goal-Achievement dashboard. Applied only until the operator picks a tab.
 */
const MODE_DEFAULT_VIEW: Record<InteractionMode, string> = {
  recommendation: 'flatland-map',
  'co-learning': 'flatland-map',
  director: 'goal-achievement',
};

/**
 * View Tabs — a single center container that switches between the run's
 * situation views via a tab bar, instead of stacking them vertically.
 *
 * The tab set is data-driven, not hardwired: it comes from the panel's
 * `config.tabs` (a list of view types) when set, else every registered center
 * view (see center-views.ts). Rendering is generic via NgComponentOutlet, so the
 * container has no per-view code. Episodic / cross-cutting surfaces (reflection,
 * survey, chat) stay as overlays, not tabs. See docs/plans/center-view-tabs.md.
 * Source: from-scratch, deliberately.
 */
@Component({
  selector: 'app-view-tabs',
  standalone: true,
  imports: [NgComponentOutlet],
  templateUrl: './view-tabs.component.html',
  styleUrl: './view-tabs.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ViewTabsComponent {
  private readonly store = inject(SessionStore);

  @Input() embedded = false;

  /** Panel context — carries `config.tabs` (selected view types) and is
   *  forwarded to views that need it (e.g. goal-achievement). */
  @Input() set panel(p: PanelInstance | null) {
    this._panel.set(p);
  }
  private readonly _panel = signal<PanelInstance | null>(null);

  constructor() {
    // On a mode switch, drop the manual tab pick so the mode's default view
    // (MODE_DEFAULT_VIEW) takes over. Within a mode, an explicit pick sticks.
    effect(() => {
      this.store.interactionMode();
      this._activeType.set(null);
    });
  }

  /** The tabs to show: the configured subset (from the layout designer, stored
   *  in `settings.tabs`, or `config.tabs`), else all registered center views. */
  readonly tabs = computed<CenterViewDef[]>(() => {
    const p = this._panel() as (PanelInstance & { settings?: { tabs?: string[] } }) | null;
    const configured = p?.settings?.tabs ?? (p?.config?.['tabs'] as string[] | undefined);
    const types = configured && configured.length ? configured : CENTER_VIEWS.map((v) => v.type);
    return types.map((t) => centerViewByType(t)).filter((v): v is CenterViewDef => !!v);
  });

  private readonly _activeType = signal<string | null>(null);

  /** Active view: the operator's explicit pick if still present; else the
   *  current mode's default view (MODE_DEFAULT_VIEW); else the first tab. */
  readonly active = computed<CenterViewDef | null>(() => {
    const tabs = this.tabs();
    if (!tabs.length) return null;
    const picked = this._activeType();
    if (picked) {
      const hit = tabs.find((t) => t.type === picked);
      if (hit) return hit;
    }
    const modeDefault = MODE_DEFAULT_VIEW[this.store.interactionMode()];
    return tabs.find((t) => t.type === modeDefault) ?? tabs[0];
  });

  readonly activeComponent = computed(() => this.active()?.component ?? null);
  readonly activeInputs = computed<Record<string, unknown>>(() =>
    this.active()?.inputs?.({ panel: this._panel() }) ?? {},
  );

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  select(type: string): void {
    this._activeType.set(type);
  }
}
