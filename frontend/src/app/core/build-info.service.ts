import { Injectable, computed, signal } from '@angular/core';

/**
 * Which build is on screen.
 *
 * A deploy either arrived or it did not, and "the page looks the same" is not
 * an answer — the Space can serve a stale image, a build can fail after the
 * mirror job reports success, and a browser can hold an old bundle. So the
 * build stamps itself and the footer shows it.
 *
 * The file is written by the deploy workflow (`.github/workflows/deploy-hf-space.yml`,
 * "Assemble the Space tree"), because the container image copies `frontend/`
 * and `backend/app` only — `.git` never reaches the Docker build, so nothing
 * inside it can ask git what it is.
 *
 * The committed default says `dev`, so a locally served build is never mistaken
 * for a deployed one.
 */
export interface BuildInfo {
  /** Short commit sha, or 'dev' for a local build. */
  commit: string;
  branch: string;
  /** ISO timestamp of the deploy build; null locally. */
  builtAt: string | null;
}

@Injectable({ providedIn: 'root' })
export class BuildInfoService {
  private readonly _info = signal<BuildInfo | null>(null);
  readonly info = this._info.asReadonly();

  constructor() {
    void this.load();
  }

  /** Absolute path on purpose: the app switches views by pathname (`/widgets`,
   *  `/designer`), so a relative fetch would resolve under the current one. */
  private async load(): Promise<void> {
    try {
      const res = await fetch('/build-info.json', { cache: 'no-store' });
      if (!res.ok) return;
      this._info.set((await res.json()) as BuildInfo);
    } catch {
      // No stamp is better than a wrong one — the footer simply shows nothing.
    }
  }

  /** Short label for the footer: the commit, and the build date when deployed. */
  readonly label = computed<string | null>(() => {
    const info = this._info();
    if (!info) return null;
    if (!info.builtAt) return `${info.commit} · local`;
    const built = new Date(info.builtAt);
    const date = built.toLocaleDateString('de-CH', { day: '2-digit', month: '2-digit' });
    const time = built.toLocaleTimeString('de-CH', { hour: '2-digit', minute: '2-digit' });
    return `${info.commit} · ${date} ${time}`;
  });

  /** Full detail for the tooltip. */
  readonly detail = computed<string>(() => {
    const info = this._info();
    if (!info) return '';
    return info.builtAt
      ? `Build ${info.commit} on ${info.branch}, deployed ${new Date(info.builtAt).toLocaleString('de-CH')}`
      : `Local build (${info.commit}) — not a deployed version`;
  });
}
