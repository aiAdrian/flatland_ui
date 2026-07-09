import { Component, CUSTOM_ELEMENTS_SCHEMA, Input } from '@angular/core';

export type ConfigArea = 'dispatcher' | 'designer' | 'infrastructure-builder' | 'widgets';

interface AreaLink {
  id: ConfigArea;
  label: string;
  href: string;
  icon: string;
}

const AREA_LINKS: AreaLink[] = [
  { id: 'dispatcher', label: 'Dispatcher', href: '/', icon: 'train-small' },
  { id: 'designer', label: 'Layout Designer', href: '/designer', icon: 'grid-small' },
  { id: 'infrastructure-builder', label: 'Infrastructure Builder', href: '/infrastructure-builder', icon: 'map-small' },
  { id: 'widgets', label: 'Widgets Gallery', href: '/widgets', icon: 'apps-small' },
];

/**
 * Shared app chrome — a single topbar strip (brand + Menu) used by every
 * full-page surface (Dispatcher, Layout Designer, Infrastructure Builder,
 * Widget Gallery) so all four share one consistent header instead of each
 * hand-rolling its own.
 *
 * Area-to-area navigation lives inside the Menu's "Areas" section (generated
 * here, once, for every surface) rather than as always-visible top-bar tabs —
 * those crowded the bar and fought for attention with the live Dispatcher view.
 * A surface's own actions are projected via `[configActions]`, rendered above
 * the Areas section; add a trailing `<sbb-divider configActions>` as your last
 * action if you have any (Widgets Gallery has none, so it skips straight to
 * Areas). A surface that needs extra controls inline in the bar itself (e.g.
 * the Dispatcher's interaction-mode tabs) projects them via `[configCenter]`:
 *
 *   <app-config-shell active="designer" [skipAreas]="['dispatcher']">
 *     <sbb-menu-button configActions (click)="applyAndOpenDispatcher()">Apply &amp; open dispatcher</sbb-menu-button>
 *   </app-config-shell>
 *   <!-- surface body follows -->
 *
 * `skipAreas` omits an area from the generated list when the surface already
 * offers its own, more specific way to reach it (e.g. Designer's save-first
 * "Apply & open dispatcher" instead of a plain "Dispatcher" link) — so there's
 * exactly one way there, not two.
 */
@Component({
  selector: 'app-config-shell',
  standalone: true,
  templateUrl: './config-shell.component.html',
  styleUrl: './config-shell.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ConfigShellComponent {
  /** Which surface is active — drives the brand subtitle and is excluded from Areas. */
  @Input({ required: true }) active!: ConfigArea;

  /** Areas to omit from the generated Areas menu section (see class doc). */
  @Input() skipAreas: ConfigArea[] = [];

  private readonly subtitles: Record<ConfigArea, string> = {
    dispatcher: 'A Human-AI Teaming Playground',
    designer: 'Layout Designer',
    'infrastructure-builder': 'Infrastructure Builder',
    widgets: 'Widget Gallery',
  };

  get subtitle(): string {
    return this.subtitles[this.active];
  }

  get areaLinks(): AreaLink[] {
    return AREA_LINKS.filter((a) => a.id !== this.active && !this.skipAreas.includes(a.id));
  }
}
