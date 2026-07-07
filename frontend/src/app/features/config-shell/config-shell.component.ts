import { Component, Input } from '@angular/core';

export type ConfigArea = 'designer' | 'infrastructure-builder' | 'gallery';

/**
 * Shared chrome for the system **Configuration** area. A single topbar strip —
 * brand + sub-navigation between the config surfaces (Layout Designer, Tile
 * Gallery) — so every full-page config surface shares one consistent header
 * instead of each hand-rolling its own.
 *
 * Used as the first child of a config surface (it replaces that surface's own
 * topbar); the surface keeps managing its own body below. Area-specific actions
 * (including the surface's own Menu / exit action) are projected into the
 * topbar via `[configActions]`:
 *
 *   <app-config-shell active="designer">
 *     <sbb-menu configActions …>…</sbb-menu>
 *   </app-config-shell>
 *   <!-- surface body follows -->
 */
@Component({
  selector: 'app-config-shell',
  standalone: true,
  templateUrl: './config-shell.component.html',
  styleUrl: './config-shell.component.scss',
})
export class ConfigShellComponent {
  /** Which config surface is active — drives the sub-nav highlight. */
  @Input({ required: true }) active!: ConfigArea;

  readonly tabs: Array<{ id: ConfigArea; label: string; href: string }> = [
    { id: 'designer', label: 'Layout Designer', href: '/designer' },
    { id: 'infrastructure-builder', label: 'Infrastructure Builder', href: '/infrastructure-builder' },
    { id: 'gallery', label: 'Tile Gallery', href: '/gallery' },
  ];
}
