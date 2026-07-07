import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, computed, inject, signal } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { DecisionLogEntry, DecisionOwner } from '../../core/decision-log';
import { AgentColorService } from '../../core/agent-color.service';

/**
 * Tile A2 — Decision Log & Accountability Strip (spec:
 * docs/plans/tile-a2-decision-log.md). `kind` = Capitalization.
 *
 * A read model over decisions already captured at the existing choke-points
 * (setOverride / clearOverride / systemHold) in all three modes — no parallel
 * logging mechanism. Every entry has an `accountableOwner` (human / ai /
 * system) so "human in control" is an inspectable claim, not a slogan.
 *
 * Mode behaviour (single mode-aware component):
 *  - recommendation → each entry shows the AI suggestion alongside what the
 *    human chose (accept vs. override is the point).
 *  - co-learning    → entries show the human's chosen option neutrally; feeds
 *    the reflection prompt.
 *  - director       → mostly AI auto-decisions; the operator's entries are the
 *    rarer exception interventions — the strip makes this asymmetry visible.
 *
 * Owner colour-coding uses bare SBB tokens for now (human=blue, ai=amber,
 * system=granite) matching the planned visual-encoding registry's authorship
 * defaults. When the registry is wired to tiles, swap these to read
 * `store.visualEncoding()` instead — the registry will then own this colour
 * family (see docs/reference/colour-usage-audit.md §2/§3).
 */
@Component({
  selector: 'app-decision-log-panel',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './decision-log-panel.component.html',
  styleUrl: './decision-log-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class DecisionLogPanelComponent {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  readonly store = inject(SessionStore);
  private readonly colors = inject(AgentColorService);

  /** Newest-first view of the rolling log (cap 200 for the strip). */
  readonly entries = computed<DecisionLogEntry[]>(() =>
    [...this.store.decisionLog()].slice(-200).reverse(),
  );

  /** Director: highlight that human interventions are the rare exception. */
  readonly humanCount = computed(() =>
    this.store.decisionLog().filter((e) => e.accountableOwner === 'human').length,
  );
  readonly aiCount = computed(() =>
    this.store.decisionLog().filter((e) => e.accountableOwner === 'ai').length,
  );
  readonly systemCount = computed(() =>
    this.store.decisionLog().filter((e) => e.accountableOwner === 'system').length,
  );

  /** Override rate = human-owned decisions ÷ human+ai decisions (system excluded:
   *  a safe-default hold is neither an accept nor an override). */
  readonly overrideRate = computed<number | null>(() => {
    const human = this.humanCount();
    const ai = this.aiCount();
    const denom = human + ai;
    if (denom === 0) return null;
    // "Override" = a human decision whose action differs from the AI suggestion.
    const overrides = this.store
      .decisionLog()
      .filter((e) => e.accountableOwner === 'human' && e.aiSuggestion != null)
      .length;
    return Math.round((overrides / denom) * 100);
  });

  /** Mean human decision dwell (ms), null if none yet. */
  readonly meanDecisionMs = computed<number | null>(() => {
    const times = this.store
      .decisionLog()
      .map((e) => e.decisionTimeMs)
      .filter((t): t is number => t != null);
    if (!times.length) return null;
    return Math.round(times.reduce((a, b) => a + b, 0) / times.length);
  });

  readonly collapsed = signal<boolean>(false);
  toggleCollapsed(): void {
    this.collapsed.update((v) => !v);
  }

  ownerClass(owner: DecisionOwner): string {
    return `dl-owner-${owner}`;
  }

  ownerLabel(owner: DecisionOwner): string {
    return owner === 'human' ? 'You' : owner === 'ai' ? 'AI' : 'System';
  }

  /** Accept vs. override (derived): a human entry whose action differs from the
   *  AI suggestion = override; same = accept. */
  decisionVerb(e: DecisionLogEntry): 'accept' | 'override' | '—' {
    if (e.accountableOwner === 'system') return '—';
    if (e.aiSuggestion == null) return '—';
    // Coarse heuristic: if the human's action text matches the AI suggestion
    // title fragment, call it accept; otherwise override.
    const ai = e.aiSuggestion.toLowerCase();
    const act = e.action;
    const accepts = (act === 'hold' && ai.includes('hold'))
      || (act === 'reroute' && ai.includes('reroute'))
      || (act === 'proceed' && ai.includes('proceed'));
    return accepts ? 'accept' : 'override';
  }

  agentColor(handle: number): string {
    return this.colors.getColorSolid(handle);
  }

  /** JSON export (reuses the download pattern from layout-designer). */
  exportJson(): void {
    const payload = {
      version: 1 as const,
      exportedAt: new Date().toISOString(),
      session: this.store.session()?.id ?? null,
      mode: this.store.interactionMode(),
      entries: this.store.decisionLog(),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `flatland-decision-log-${payload.session ?? 'local'}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  clear(): void {
    this.store.clearDecisionLog();
  }

  formatMs(ms: number | null): string {
    if (ms == null) return '—';
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  }

  formatTime(t: number): string {
    return new Date(t).toLocaleTimeString();
  }
}
