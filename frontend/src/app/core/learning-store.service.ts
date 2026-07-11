import { Injectable, computed, signal } from '@angular/core';
import { InteractionMode } from './events/event-types';

/**
 * Workstream B Tier 1 — the Co-Learning learning loop's storage substrate
 * (deck slides 5 & 8). A mode-agnostic, frontend-only service: the mode-specific
 * capture surfaces (Recommendation "why?" override flow, Co-Learning reflection)
 * hand confirmed records here. **No LLM, no backend, no ranking feedback** —
 * those are Tier 2 (docs/plans/workstream-b-rationale-capture.md).
 *
 * Persistence rule (the overfitting guard, deck slide 7):
 *  - `'yes'`  → confirmed preference → persisted to `localStorage` (a rule).
 *  - `'once'` → a one-off decision → in-memory only, NEVER persisted (a single
 *               decision must not become a rule). Vanishes on reload by design.
 *  - `'no'    → hypothesis rejected → no record at all.
 *
 * Co-Learning is a cross-cutting layer, not a fourth mode
 * (docs/plans/colearning-across-modes.md §0): this store carries `mode` for
 * context, but the service itself is mode-agnostic.
 */

/** Snapshot of the situation at override time — the "condition" half of the
 *  preference ("learn the condition, not the option"). The three booleans are
 *  the Phase-2 flagship's connection/delay/ripple proxies; refine with real
 *  KPIs in Tier 2. */
export interface RationaleContext {
  /** Connection at risk (connection metric level 'low' = 'Reduced'). */
  connectionCritical: boolean;
  /** Added delay small/zero (delay metric level 'good'). */
  lowDelay: boolean;
  /** Ripple risk low (deadlocks delta ≤ 0). */
  lowRipple: boolean;
  /** Human-readable metric values at decision time, for the record card. */
  delayValue?: string;
  connectionValue?: string;
  rippleValue?: string;
  /** Top AI recommendation title at the moment of override, if any. */
  aiSuggestion: string | null;
  /** Simulation step of the override. */
  simStep: number;
  /** Whether a backing scenario was available to derive the booleans. When
   *  false, the hypothesis falls back to a generic template (honest about the
   *  missing context rather than inventing trade-off values). */
  hasScenario: boolean;
  /** Id/title of the scenario the metrics were derived from, for the record. */
  scenarioTitle?: string | null;
}

/** A confirmed (or one-off) learning record — deck slide 5's "Learning Record":
 *  the condition under which a trade-off is preferred, the chosen strategy, the
 *  why, and the operator's confirmation. */
export interface LearningRecord {
  id: string;
  createdAt: number;
  mode: InteractionMode;
  handle: number;
  /** Flatland action id the operator chose. */
  action: number;
  /** German label for the chosen strategy ("Halten" / "Umleiten"). */
  strategyLabel: string;
  /** Chosen "why" (chips joined) + optional free-text note. */
  rationale: string;
  /** Generated "when {context}, prefer {choice}" hypothesis. */
  hypothesis: string;
  /** Operator's confirmation. */
  response: 'yes' | 'once';
  /** True = one-off ('once'), not persisted. false = confirmed ('yes'). */
  once: boolean;
  /** The situation snapshot the hypothesis was templated over. */
  context: RationaleContext;
}

/** German strategy label for a Flatland action id (mirrors `actionLabelFor`
 *  semantics: STOP_MOVING=4 → hold; 1/2/3 → reroute). */
export function strategyLabelForAction(action: number): string {
  return action === 4 ? 'Halten' : 'Umleiten';
}

/**
 * Build the preference hypothesis as a **template over the context fields**
 * (no LLM). Honest about missing context: when no scenario backed the decision,
 * it says so instead of inventing trade-off values. Marked as a hypothesis, not
 * a fact, because the template is mechanical and the context is proxy-based.
 */
export function buildPreferenceHypothesis(
  ctx: RationaleContext,
  strategyLabel: string,
): string {
  if (!ctx.hasScenario) {
    return `Bei dieser Situation bevorzugst du ${strategyLabel} (Hypothese — Kontext unbekannt).`;
  }
  const conn = ctx.connectionCritical ? 'kritischem Anschluss' : 'stabilem Anschluss';
  const delay = ctx.lowDelay ? 'geringer Zusatzverspätung' : 'höherer Zusatzverspätung';
  const ripple = ctx.lowRipple ? 'niedrigem Ripple-Risiko' : 'erhöhtem Ripple-Risiko';
  return `Bei ${conn}, ${delay} und ${ripple} bevorzugst du ${strategyLabel}.`;
}

@Injectable({ providedIn: 'root' })
export class LearningStore {
  private static readonly STORAGE_KEY = 'flatland_learning_records';

  /** All records currently held (confirmed + one-off). 'no' responses produce
   *  no record. One-off records live here for the session but are not persisted. */
  readonly records = signal<LearningRecord[]>([]);

  /** Count of confirmed ('yes') preferences — the number the recommendations
   *  panel's Co-Learning-effect hint reflects. One-offs don't count. */
  readonly confirmedCount = computed(
    () => this.records().filter((r) => !r.once && r.response === 'yes').length,
  );

  /** Records shown as Learning-Record cards: confirmed + this-session one-offs. */
  readonly visibleRecords = computed(() =>
    this.records().filter((r) => r.response === 'yes' || r.response === 'once'),
  );

  constructor() {
    // Reload persisted (confirmed) preferences within the browser.
    this.records.set(this._loadPersisted());
  }

  addRecord(record: LearningRecord): void {
    this.records.update((list) => [record, ...list]);
    if (!record.once && record.response === 'yes') {
      this._persist();
    }
  }

  clear(): void {
    this.records.set([]);
    try {
      localStorage.removeItem(LearningStore.STORAGE_KEY);
    } catch {
      // localStorage unavailable (private mode / tests).
    }
  }

  /** Reload only the persisted (confirmed 'yes') records, discarding any
   *  in-memory one-off ('once') records. Non-destructive: unlike `clear()`,
   *  it does NOT touch localStorage, so a caller that added throwaway
   *  in-memory records (e.g. the Widget Gallery fixture) can remove just
   *  those without wiping the operator's real confirmed preferences. */
  resetToPersisted(): void {
    this.records.set(this._loadPersisted());
  }

  private _loadPersisted(): LearningRecord[] {
    try {
      const raw = localStorage.getItem(LearningStore.STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? (parsed as LearningRecord[]) : [];
    } catch {
      return [];
    }
  }

  private _persist(): void {
    try {
      // Only confirmed ('yes') records are persisted; one-offs never are.
      const persisted = this.records().filter((r) => !r.once && r.response === 'yes');
      localStorage.setItem(LearningStore.STORAGE_KEY, JSON.stringify(persisted));
    } catch {
      // localStorage may be unavailable.
    }
  }
}
