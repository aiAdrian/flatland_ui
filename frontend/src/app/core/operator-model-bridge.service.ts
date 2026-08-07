import { Injectable, computed, effect, inject, untracked } from '@angular/core';
import { DecisionLogEntry } from './decision-log';
import { OperatorModelService, OptionKpis, OperatorContext } from './operator-model.service';
import { SessionStore } from './session.store';
import { followedAi, isDeliberate, valueAxisFor } from './operator-value-axis';

/**
 * Bridges the HMI's existing capture choke-points to the backend operator model
 * (Co-Learning **Level B**, `docs/plans/co-learning-direction.md`).
 *
 * Deliberately **non-invasive**: it observes `SessionStore.decisionLog()` — the
 * session's owned decision record — instead of adding calls inside the store.
 * No new capture mechanism, per `interaction-logging-plan.md`.
 *
 * Settling rule: a human entry may gain its `rationale` a moment later (the
 * "why?" prompt). We therefore only report an entry once it is **settled** —
 * either it already carries a reason, or no rationale prompt is pending for it
 * any more (the operator dismissed it → a passive accept).
 */
@Injectable({ providedIn: 'root' })
export class OperatorModelBridge {
  private store = inject(SessionStore);
  private model = inject(OperatorModelService);

  /** Decision-log sequence numbers already reported (no double counting). */
  private readonly reported = new Set<number>();
  /** Manual override: `null` = follow the session/mode condition below. */
  private forced: boolean | null = null;
  private profileLoadedFor: string | null = null;

  /**
   * Self-arming: report while a session is running in a mode where Co-Learning
   * applies. Co-Learning is a cross-cutting layer, not a fourth mode
   * (`docs/plans/colearning-across-modes.md` §0) — but Recommendation mode's
   * accept/override flow is the one that produces the signals, and Director mode
   * is where the inferred weights land, so both count.
   */
  private readonly active = computed(() => {
    if (this.forced !== null) return this.forced;
    if (!this.store.session()) return false;
    const mode = this.store.interactionMode();
    return mode === 'co-learning' || mode === 'director' || mode === 'recommendation';
  });

  constructor() {
    effect(() => {
      const log = this.store.decisionLog();
      const pending = this.store.pendingRationale();
      const pendingStrategy = this.store.pendingStrategyReflection();
      if (!this.active()) return;
      untracked(() => {
        this.ensureProfileLoaded();
        this.drain(log, [pending?.decisionSeq, pendingStrategy?.decisionSeq]);
      });
    });
  }

  /** Force reporting on (and optionally switch operator). */
  enable(operatorId?: string): void {
    if (operatorId) this.model.operatorId.set(operatorId);
    this.forced = true;
  }

  /** Force reporting off, regardless of session/mode. */
  disable(): void {
    this.forced = false;
  }

  /** Fetch the carried-over profile once per operator, so the UI starts warm. */
  private ensureProfileLoaded(): void {
    const id = this.model.operatorId();
    if (this.profileLoadedFor === id) return;
    this.profileLoadedFor = id;
    this.model.loadProfile().subscribe({ error: () => void 0 });
  }

  /** Forget which entries were reported (e.g. on session reset). */
  resetReported(): void {
    this.reported.clear();
  }

  private drain(log: DecisionLogEntry[], pendingSeqs: Array<number | undefined>): void {
    const waiting = new Set(pendingSeqs.filter((n): n is number => n != null));
    for (const entry of log) {
      if (this.reported.has(entry.seq)) continue;
      // 'system' holds are deliberately attributed to neither party.
      if (entry.accountableOwner === 'system') {
        this.reported.add(entry.seq);
        continue;
      }
      // Still waiting for its "why?" / "as a rule?" — report once that resolves.
      if (waiting.has(entry.seq)) continue;

      this.reported.add(entry.seq);
      this.report(entry);
    }
  }

  private report(entry: DecisionLogEntry): void {
    const { chosenKpis, optionKpis } = this.kpiSnapshot(entry);
    this.model
      .recordSignal({
        step: entry.simStep,
        handle: entry.handle,
        value: valueAxisFor(entry),
        followedAi: followedAi(entry),
        deliberate: isDeliberate(entry),
        context: this.contextFor(entry),
        chosenKpis,
        optionKpis,
      })
      .subscribe({ error: () => void 0 });

    // A confirmed hypothesis ('yes') is a rule the AI should apply from now on;
    // 'once' is the overfitting guard and must NOT become one.
    if (entry.hypothesisResponse === 'yes' && entry.preferenceHypothesis) {
      const axis = valueAxisFor(entry);
      if (axis) {
        this.model
          .recordLearning({
            statement: entry.preferenceHypothesis,
            targetValue: axis,
            conditions: this.contextFor(entry) as Record<string, unknown>,
          })
          .subscribe({ error: () => void 0 });
      }
    }
  }

  /**
   * The situation proxies, in the backend model's snake_case vocabulary — the
   * "condition" half of a learned preference ("learn the condition, not the
   * option").
   */
  private contextFor(entry?: DecisionLogEntry): OperatorContext {
    // A Director strategy choice is not made against a policy scenario — under
    // the goal-directed planner those scenarios are not even what drives — so
    // reading their KPI deltas would attach a condition that describes nothing.
    // The live fleet state does describe the situation the operator chose in.
    if (entry?.action === 'strategy') return this.liveContext();

    const scenario =
      this.store.scenarios().find((s) => s.isBaseline) ?? this.store.scenarios()[0] ?? null;
    if (!scenario) return {};
    const meanDelay = scenario.kpiDeltas?.meanDelay;
    const done = scenario.kpiDeltas?.done;
    const deadlocks = scenario.kpiDeltas?.deadlocks;
    return {
      connection_critical: done != null && done < 0,
      low_delay: meanDelay != null && meanDelay <= 0,
      low_ripple: deadlocks != null && deadlocks <= 0,
    };
  }

  /** Situation from the fleet itself: how many trains are late, how many broken. */
  private liveContext(): OperatorContext {
    const agents = this.store.agents();
    const delayed = agents.filter((a) => (a.delay ?? 0) > 0).length;
    const malfunctioning = agents.filter(
      (a) => !!a.is_malfunctioning || (a.malfunction_remaining ?? 0) > 0,
    ).length;
    return {
      // Late trains are what puts transfers at risk.
      connection_critical: delayed > 0,
      low_delay: delayed === 0,
      low_ripple: malfunctioning === 0,
    };
  }

  /**
   * KPI deltas of the options that were on the table, so the backend can infer
   * the value axis when the operator stated no reason (inverse-RL-lite). The
   * chosen option is only known when the AI's suggestion was accepted; on an
   * override we honestly send `null` rather than guessing.
   */
  private kpiSnapshot(entry: DecisionLogEntry): {
    chosenKpis: OptionKpis | null;
    optionKpis: OptionKpis[];
  } {
    const scenarios = this.store.scenarios();
    const optionKpis = scenarios
      .map((s) => s.kpiDeltas)
      .filter((k): k is NonNullable<typeof k> => k != null)
      .map((k) => this.toOptionKpis(k));

    if (entry.action === 'override' || entry.aiSuggestion == null) {
      return { chosenKpis: null, optionKpis };
    }
    const accepted = scenarios.find((s) => s.title === entry.aiSuggestion);
    return {
      chosenKpis: accepted?.kpiDeltas ? this.toOptionKpis(accepted.kpiDeltas) : null,
      optionKpis,
    };
  }

  private toOptionKpis(k: {
    totalDelay?: number;
    deadlocks?: number;
    done?: number;
    meanDelay?: number;
  }): OptionKpis {
    return {
      totalDelay: k.totalDelay,
      deadlocks: k.deadlocks,
      done: k.done,
      meanDelay: k.meanDelay,
    };
  }
}
