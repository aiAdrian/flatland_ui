import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, computed, signal } from '@angular/core';
import { NgComponentOutlet } from '@angular/common';
import { PanelInstance } from '../../core/layout/models/layout.models';
import { CENTER_VIEWS, CenterViewDef, centerViewByType } from './center-views';

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
  @Input() embedded = false;

  /** Panel context — carries `config.tabs` (selected view types) and is
   *  forwarded to views that need it (e.g. goal-achievement). */
  @Input() set panel(p: PanelInstance | null) {
    this._panel.set(p);
  }
  private readonly _panel = signal<PanelInstance | null>(null);

  /** The tabs to show: the configured subset (from the layout designer, stored
   *  in `settings.tabs`, or `config.tabs`), else all registered center views. */
  readonly tabs = computed<CenterViewDef[]>(() => {
    const p = this._panel() as (PanelInstance & { settings?: { tabs?: string[] } }) | null;
    const configured = p?.settings?.tabs ?? (p?.config?.['tabs'] as string[] | undefined);
    const types = configured && configured.length ? configured : CENTER_VIEWS.map((v) => v.type);
    return types.map((t) => centerViewByType(t)).filter((v): v is CenterViewDef => !!v);
  });

  private readonly _activeType = signal<string | null>(null);

  /** Active view: the selected tab if still present, else the first tab. */
  readonly active = computed<CenterViewDef | null>(() => {
    const tabs = this.tabs();
    if (!tabs.length) return null;
    return tabs.find((t) => t.type === this._activeType()) ?? tabs[0];
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
