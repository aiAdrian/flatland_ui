import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, map, tap } from 'rxjs';
import { backendHttpBase } from './backend-origin';
import { DirectorWeights } from './api.service';

const API_BASE = backendHttpBase();

/**
 * Co-Learning **Level B** client — the AI's model of the operator
 * (`docs/plans/co-learning-direction.md`). The backend
 * (`app/core/operator_model.py`) infers *reward weights* from what the operator
 * actually did and proposes (a) Director dials and (b) an autonomy / framing
 * level. This service is the thin transport + a signal mirror for the UI.
 *
 * Evidence rule (mirrors `LearningStore`'s overfitting guard, lifted to the
 * accept/override signal itself): a **passive** accept — the operator taking the
 * recommendation without engaging — is recorded but never shapes preferences.
 * Only `deliberate` decisions (reasoned accept, or an override) count.
 */

/** The value axes the model reasons over (backend `VALUE_AXES`). */
export type ValueAxis = 'punctuality' | 'throughput' | 'stability' | 'connection';

/** Situation snapshot; the same proxy booleans `RationaleContext` already uses. */
export interface OperatorContext {
  connection_critical?: boolean;
  low_delay?: boolean;
  low_ripple?: boolean;
  /** True when the chosen option keeps a critical connection. */
  protects_connection?: boolean;
}

/** `ScenarioKpis`-shaped deltas, used to infer the axis when it isn't given. */
export interface OptionKpis {
  totalDelay?: number;
  deadlocks?: number;
  done?: number;
  meanDelay?: number;
}

export interface OperatorSignal {
  step?: number;
  handle?: number;
  optionId?: string | null;
  value?: ValueAxis | null;
  followedAi?: boolean;
  deliberate?: boolean;
  context?: OperatorContext;
  chosenKpis?: OptionKpis | null;
  optionKpis?: OptionKpis[];
}

export interface OperatorLearning {
  statement: string;
  targetValue: ValueAxis;
  conditions?: Record<string, unknown>;
}

export interface OperatorValueProfile {
  dominant: ValueAxis | null;
  label: string;
  dominantPct: number;
  distribution: { value: ValueAxis; weight: number; count: number }[];
  total: number;
}

export interface OperatorProfile {
  operatorId: string;
  isWarm: boolean;
  priorSessions: number;
  evidenceCount: number;
  passiveCount: number;
  trustRatio: number;
  valueWeights: Partial<Record<ValueAxis, number>>;
  valueProfile: OperatorValueProfile;
  confirmedLearnings: OperatorLearning[];
  optionPresentation: 'recommend' | 'neutral';
  suggestedDirectorWeights: DirectorWeights;
}

export interface OperatorPrediction {
  value: ValueAxis | null;
  confidence: number;
  basis: 'similar_context' | 'overall_preference' | 'profile' | 'cold_start';
  sampleSize: number;
}

export interface OperatorAdjustment {
  targetValue: ValueAxis;
  reason: string;
  appliedLearning: string | null;
  confidence: number;
}

@Injectable({ providedIn: 'root' })
export class OperatorModelService {
  private http = inject(HttpClient);

  /** Which operator the profile belongs to; preferences persist under this id. */
  readonly operatorId = signal<string>('operator1');

  /** Last profile fetched from the backend (null until the first call). */
  readonly profile = signal<OperatorProfile | null>(null);

  /** Last prediction, so the UI can show "I think you'll choose …". */
  readonly prediction = signal<OperatorPrediction | null>(null);

  /** True once the model carries something from earlier sessions. */
  readonly isWarm = computed(() => this.profile()?.isWarm ?? false);

  /** The dial proposal, ready to hand to `ApiService.setDirectorWeights`. */
  readonly suggestedWeights = computed<DirectorWeights | null>(
    () => this.profile()?.suggestedDirectorWeights ?? null,
  );

  private base(): string {
    return `${API_BASE}/operator/${encodeURIComponent(this.operatorId())}`;
  }

  loadProfile(): Observable<OperatorProfile> {
    return this.http
      .get<OperatorProfile>(this.base())
      .pipe(tap((p) => this.profile.set(p)));
  }

  /** Record one decision. Returns (and mirrors) the updated profile. */
  recordSignal(entry: OperatorSignal): Observable<OperatorProfile> {
    return this.http
      .post<OperatorProfile>(`${this.base()}/signal`, {
        step: entry.step ?? 0,
        handle: entry.handle ?? 0,
        optionId: entry.optionId ?? null,
        value: entry.value ?? null,
        followedAi: entry.followedAi ?? false,
        deliberate: entry.deliberate ?? false,
        context: entry.context ?? {},
        chosenKpis: entry.chosenKpis ?? null,
        optionKpis: entry.optionKpis ?? [],
      })
      .pipe(tap((p) => this.profile.set(p)));
  }

  /** Register a preference the operator confirmed ('yes'). */
  recordLearning(learning: OperatorLearning): Observable<OperatorProfile> {
    return this.http
      .post<OperatorProfile>(`${this.base()}/learning`, {
        statement: learning.statement,
        targetValue: learning.targetValue,
        conditions: learning.conditions ?? {},
      })
      .pipe(tap((p) => this.profile.set(p)));
  }

  /** "Which trade-off will this operator pick here?" */
  predict(context: OperatorContext = {}): Observable<OperatorPrediction> {
    return this.http
      .post<OperatorPrediction>(`${this.base()}/predict`, context)
      .pipe(tap((p) => this.prediction.set(p)));
  }

  /** Re-ranking hint for the recommender, or `null` to leave the baseline alone. */
  adjustment(
    context: OperatorContext = {},
    availableValues?: ValueAxis[],
  ): Observable<OperatorAdjustment | null> {
    return this.http
      .post<{ adjustment: OperatorAdjustment | null }>(`${this.base()}/adjustment`, {
        context,
        availableValues: availableValues ?? null,
      })
      .pipe(map((r) => r.adjustment));
  }

  /** Fold this session's deliberate evidence into the carried-over profile. */
  endSession(): Observable<OperatorProfile> {
    return this.http
      .post<OperatorProfile>(`${this.base()}/end-session`, {})
      .pipe(tap((p) => this.profile.set(p)));
  }

  /** Forget this operator (demo / test reset). */
  reset(): Observable<OperatorProfile> {
    return this.http
      .delete<OperatorProfile>(this.base())
      .pipe(tap((p) => this.profile.set(p)));
  }
}
