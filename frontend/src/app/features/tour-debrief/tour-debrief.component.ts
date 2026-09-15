import { Component, CUSTOM_ELEMENTS_SCHEMA, EventEmitter, Output, computed, inject, signal } from '@angular/core';
import { AgentDTO } from '../../core/models';
import { DecisionAction } from '../../core/decision-log';
import { OperatorModelService } from '../../core/operator-model.service';
import { REFLECTION_CASE_LABELS, ReflectionCaseType } from '../../core/reflection-moments';
import { SessionStore } from '../../core/session.store';
import { ShiftKpis, buildShiftReview, interventionsFrom } from '../../core/shift-review';
import { TourGuideService } from '../../core/demo/tour-guide.service';
import { SandboxCase, SandboxVariant } from '../../core/demo/sandbox-outcomes';
import { SANDBOX_OUTCOMES } from '../../core/demo/sandbox-outcomes.generated';
import { TrainIdentityService } from '../../core/train-identity.service';
import { LearningRecordsComponent } from '../learning-records/learning-records.component';

type DebriefSection = 'shift-summary' | 'event-simulation' | 'ai-learns';

const SECTIONS: ReadonlyArray<{ id: DebriefSection; n: number; title: string }> = [
  { id: 'shift-summary', n: 7, title: 'Schichtbilanz' },
  { id: 'event-simulation', n: 8, title: 'Event-Simulation' },
  { id: 'ai-learns', n: 9, title: 'KI lernt' },
];

const ACTION_LABEL: Record<DecisionAction, string> = {
  hold: 'Halten',
  proceed: 'Weiterfahren',
  reroute: 'Umleiten',
  accept: 'Übernommen',
  override: 'Übersteuert',
  dismiss: 'Verworfen',
  strategy: 'Ziel gesetzt',
};

/**
 * Tour debrief — the learning loop after the shift (thesis flow steps 7-9):
 * shift summary, event simulation in the sandbox, what the AI learned.
 *
 * Shown in place of the Director review when the running tour asks for it
 * (`TourBriefing.debrief`). Built on the same pure builder as the Director
 * review (`buildShiftReview`), with the human's per-train interventions in place
 * of Director's goal choices.
 */
@Component({
  selector: 'app-tour-debrief',
  standalone: true,
  imports: [LearningRecordsComponent],
  templateUrl: './tour-debrief.component.html',
  styleUrl: './tour-debrief.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class TourDebriefComponent {
  @Output() finish = new EventEmitter<void>();

  readonly store = inject(SessionStore);
  readonly guide = inject(TourGuideService);
  private readonly identity = inject(TrainIdentityService);
  private readonly model = inject(OperatorModelService);

  readonly sections = SECTIONS;
  readonly active = signal<DebriefSection>('shift-summary');
  readonly activeIndex = computed(() => SECTIONS.findIndex((s) => s.id === this.active()));
  readonly nextSection = computed(() => SECTIONS[this.activeIndex() + 1] ?? null);

  constructor() {
    this.model.loadProfile().subscribe({ error: () => void 0 });
  }

  private isMalfunctioning(a: AgentDTO): boolean {
    return !!a.is_malfunctioning || (a.malfunction_remaining ?? 0) > 0;
  }

  readonly kpis = computed<ShiftKpis>(() => {
    const agents = this.store.agents();
    return {
      total: agents.length,
      arrived: agents.filter((a) => String(a.state).toUpperCase() === 'DONE').length,
      delayed: agents.filter((a) => (a.delay ?? 0) > 0).length,
      malfunctions: agents.filter((a) => this.isMalfunctioning(a)).length,
      totalDelay: agents.reduce((sum, a) => sum + Math.max(0, a.delay ?? 0), 0),
    };
  });

  readonly review = computed(() =>
    buildShiftReview({
      kpis: this.kpis(),
      ai: null,
      decisionLog: this.store.decisionLog(),
      learningRecords: this.store.learningRecords(),
    }),
  );

  readonly interventions = computed(() => interventionsFrom(this.store.decisionLog()));
  readonly systemHolds = computed(
    () => this.store.decisionLog().filter((e) => e.accountableOwner === 'system').length,
  );

  readonly valueProfile = computed(() => this.model.profile()?.valueProfile ?? null);

  readonly sandbox = SANDBOX_OUTCOMES;

  /** The interviewee's last own decision on a train, to mark it among the variants. */
  private lastActionOn(handle: number): DecisionAction | null {
    const own = this.interventions().filter((i) => i.handle === handle);
    return own.length > 0 ? own[own.length - 1].action : null;
  }

  isUserChoice(sandboxCase: SandboxCase, variant: SandboxVariant): boolean {
    return (
      sandboxCase.kind === 'experienced' &&
      variant.matchesAction !== null &&
      variant.matchesAction === this.lastActionOn(sandboxCase.decisionHandle)
    );
  }

  readonly saveState = signal<'idle' | 'saving' | 'saved' | 'error'>('idle');

  savePreferences(): void {
    if (this.saveState() === 'saving' || this.saveState() === 'saved') return;
    this.saveState.set('saving');
    this.model.endSession().subscribe({
      next: () => this.saveState.set('saved'),
      error: () => this.saveState.set('error'),
    });
  }

  /** Only while the episode could still go on; a debrief must not be a trap. */
  readonly canReopen = computed(() => !this.store.episodeDone() && this.store.shiftEnded());

  reopenShift(): void {
    this.store.reopenShift();
  }

  select(id: DebriefSection): void {
    this.active.set(id);
  }

  next(): void {
    this.guide.markDone(this.active());
    const next = this.nextSection();
    if (next) {
      this.active.set(next.id);
    } else {
      this.finish.emit();
    }
  }

  back(): void {
    const previous = SECTIONS[this.activeIndex() - 1];
    if (previous) this.active.set(previous.id);
  }

  trainName(handle: number): string {
    return this.identity.nameFor(handle);
  }

  /** Replace the sandbox texts' `{T<handle>}` placeholders with shared train names. */
  fill(text: string): string {
    return text.replace(/\{T(\d+)\}/g, (_, handle: string) => this.trainName(Number(handle)));
  }

  actionLabel(action: DecisionAction): string {
    return ACTION_LABEL[action];
  }

  responseLabel(response: 'yes' | 'once' | 'no' | null): string | null {
    if (response === 'yes') return 'als Regel bestätigt';
    if (response === 'once') return 'nur diesmal';
    if (response === 'no') return 'nicht als Präferenz';
    return null;
  }

  caseLabel(caseType: ReflectionCaseType): string {
    return REFLECTION_CASE_LABELS[caseType];
  }
}
