import { CommonModule } from '@angular/common';
import { Component, CUSTOM_ELEMENTS_SCHEMA, HostBinding, Input, OnDestroy, computed, effect, inject, signal, untracked } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { TrainIdentityService } from '../../core/train-identity.service';
import { TrainActionService } from '../../core/dispatch/train-action.service';
import { ApiService } from '../../core/api.service';
import { AgentColorService } from '../../core/agent-color.service';
import { ProposalOption, ProposalsResult, ProposalVariant } from '../../core/events/event-types';

/** One option the operator can put next to the plan and the AI. */
interface OptionChoice {
  option: ProposalOption;
  label: string;
  hint: string;
}

/**
 * Widget B1, second cut — **Plan / KI / Mensch**.
 *
 * Three courses for the selected train, each simulated to the same horizon by
 * `GET /session/{id}/proposals` (docs/plans/proposal-agents-roadmap.md, 2b):
 *
 *  - **Plan** (neutral grey): the timetable plan running on — nobody's proposal.
 *  - **KI** (yellow): a Prioritized Planning replan of every train. The order the
 *    trains take the single-track section is the decision, so the further orders
 *    come along as ranked alternatives.
 *  - **Mensch** (blue): the operator's option — hold, hold until clear, proceed,
 *    reroute — on top of the plan.
 *
 * Colours follow the A3S/TraceRL convention (human blue, AI yellow); the plan is
 * the third course and stays neutral.
 *
 * Separate from `whatif-compare` on purpose: that widget is what the User Study 2
 * conditions show, and this one is the interview layout's surface. They share the
 * backend's branch simulation, not their framing.
 *
 * Reading only — nothing is committed until "Übernehmen".
 */
@Component({
  selector: 'app-proposal-compare',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './proposal-compare.component.html',
  styleUrl: './proposal-compare.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ProposalCompareComponent implements OnDestroy {
  @Input() embedded = false;

  @HostBinding('class.embedded')
  get embeddedClass(): boolean {
    return this.embedded;
  }

  store = inject(SessionStore);
  private api = inject(ApiService);
  private trainActions = inject(TrainActionService);
  private colors = inject(AgentColorService);
  private identity = inject(TrainIdentityService);

  /** Flatland action ints behind the committable options. */
  private static readonly STOP = 4;

  readonly optionChoices: OptionChoice[] = [
    { option: 'hold', label: 'Halten', hint: 'Der Zug bleibt stehen, bis Sie ihn wieder freigeben.' },
    { option: 'hold_until_clear', label: 'Halten bis frei', hint: 'Der Zug wartet, bis die Stelle wieder frei ist, und fährt dann weiter.' },
    { option: 'proceed', label: 'Weiterfahren', hint: 'Der Zug fährt ohne Eingriff weiter.' },
    { option: 'reroute', label: 'Umleiten', hint: 'Der Zug nimmt an der nächsten Weiche den anderen Ast.' },
  ];

  readonly chosenOption = signal<ProposalOption | null>(null);
  readonly result = signal<ProposalsResult | null>(null);
  readonly loading = signal(false);
  readonly failed = signal<string | null>(null);
  readonly committed = signal(false);
  /** Alternatives are the detail: shown on request, not by default. */
  readonly showAlternatives = signal(false);

  readonly targetHandle = computed(() => this.store.selectedHandle());

  constructor() {
    // A different train is a different question: drop the old answer and ask
    // again for the plan and the AI course, without an option.
    effect(() => {
      const handle = this.targetHandle();
      untracked(() => {
        this.chosenOption.set(null);
        this.committed.set(false);
        this.showAlternatives.set(false);
        this.result.set(null);
        this.store.whatIfPreview.set(null);
        if (handle != null) this.load(null);
      });
    });
  }

  /** The variants with the given id prefix, in the response's order. */
  private variant(id: string): ProposalVariant | null {
    return this.result()?.variants.find((v) => v.id === id) ?? null;
  }

  readonly plan = computed(() => this.variant('plan'));
  readonly ai = computed(() => this.variant('ai'));
  readonly human = computed(() => this.variant('human'));
  readonly alternatives = computed(() => this.result()?.ai_alternatives ?? []);

  /** Ask the backend for the three courses. `option` null = plan and AI only. */
  load(option: ProposalOption | null): void {
    const sess = this.store.session();
    const handle = this.targetHandle();
    if (!sess || handle == null) return;

    this.loading.set(true);
    this.failed.set(null);
    this.committed.set(false);

    this.api.getProposals(sess.id, handle, option ?? undefined).subscribe({
      next: (r) => {
        this.result.set(r);
        this.loading.set(false);
        this.drawPreview(r, handle);
      },
      error: (err) => {
        // The backend refuses an option it cannot offer (no reroute here) with
        // its own sentence — that is the useful answer, so show it.
        this.failed.set(err?.error?.detail ?? 'Die Varianten konnten nicht gerechnet werden.');
        this.loading.set(false);
        this.store.whatIfPreview.set(null);
      },
    });
  }

  /** Pick an option → simulate it next to the plan and the AI. */
  choose(option: ProposalOption): void {
    this.chosenOption.set(option);
    this.load(option);
  }

  /**
   * Two paths on the map, which is what the overlay holds: the operator's course
   * in blue against the AI's in yellow once an option is picked, and the AI's
   * against the plan before that.
   */
  private drawPreview(r: ProposalsResult, handle: number): void {
    const human = r.variants.find((v) => v.id === 'human')?.trajectories;
    const ai = r.variants.find((v) => v.id === 'ai')?.trajectories;
    const plan = r.variants.find((v) => v.id === 'plan')?.trajectories;
    const yellow = ai ?? plan;
    const blue = human ?? ai;
    if (!yellow || !blue || yellow === blue) {
      this.store.whatIfPreview.set(null);
      return;
    }
    this.store.whatIfPreview.set({ baseline: yellow, branch: blue, handles: [handle] });
  }

  /** Take the chosen option for real. Logged through the dispatch seam. */
  commit(): void {
    const handle = this.targetHandle();
    const option = this.chosenOption();
    if (handle == null || option == null) return;

    if (option === 'proceed') {
      this.trainActions.clear(handle, 'proposals');
    } else if (option === 'reroute') {
      const action = this.store.impact().find((i) => i.handle === handle)?.reroute_action;
      if (action == null) {
        this.failed.set('Für diesen Zug gibt es hier keine Umleitung.');
        return;
      }
      this.trainActions.set(handle, action, 'proposals');
    } else {
      // Both hold options stop the train. The timed release exists in the
      // simulated variant only, so in the live run the operator releases it.
      this.trainActions.set(handle, ProposalCompareComponent.STOP, 'proposals');
    }
    this.committed.set(true);
    this.store.whatIfPreview.set(null);
  }

  ngOnDestroy(): void {
    this.store.whatIfPreview.set(null);
  }

  // ── Presentation helpers ──────────────────────────────────────────────

  targetColor(): string {
    const handle = this.targetHandle();
    return handle == null ? 'transparent' : this.colors.getColor(handle, 'default');
  }

  targetLabel(): string {
    const handle = this.targetHandle();
    return handle == null ? '' : this.identity.nameFor(handle);
  }

  isChosen(option: ProposalOption): boolean {
    return this.chosenOption() === option;
  }

  /**
   * Offer only what this train actually has. While the impact analysis lists the
   * train it also says whether a reroute exists; without a branch ahead the
   * backend refuses that option, and the assessment panel already says so —
   * an enabled button that always fails would contradict it.
   */
  readonly rerouteAvailable = computed(() => {
    const handle = this.targetHandle();
    const item = this.store.impact().find((i) => i.handle === handle);
    return item ? item.can_reroute : true;
  });

  isDisabled(option: ProposalOption): boolean {
    return option === 'reroute' && !this.rerouteAvailable();
  }

  /** "Hält bis frei" as the human column's heading, not the raw option id. */
  humanLabel(): string {
    const option = this.chosenOption();
    return this.optionChoices.find((c) => c.option === option)?.label ?? 'Ihre Wahl';
  }

  /** Arrival as a sentence: the step and how far off the plan it is. */
  arrivalText(v: ProposalVariant): string {
    const arrival = v.train.arrival_step;
    if (arrival == null) return 'kommt nicht an';
    const delay = v.train.delay_vs_plan;
    if (delay == null) return `Schritt ${arrival}`;
    if (delay === 0) return `Schritt ${arrival} · nach Plan`;
    return `Schritt ${arrival} · ${this.signed(delay)} gegenüber Plan`;
  }

  /** The order the AI would send the trains through, in train names. */
  priorityText(v: ProposalVariant): string {
    return (v.priority ?? []).map((h) => this.identity.nameFor(h)).join(' → ');
  }

  signed(value: number): string {
    return value > 0 ? `+${value}` : `${value}`;
  }

  /** Worse than the plan for this train — the template colours it, nothing more. */
  worseThanPlan(v: ProposalVariant): boolean {
    const plan = this.plan();
    if (!plan) return false;
    if (v.train.arrival_step == null) return plan.train.arrival_step != null;
    if (plan.train.arrival_step == null) return false;
    return v.train.arrival_step > plan.train.arrival_step;
  }

  betterThanPlan(v: ProposalVariant): boolean {
    const plan = this.plan();
    if (!plan || v.train.arrival_step == null || plan.train.arrival_step == null) return false;
    return v.train.arrival_step < plan.train.arrival_step;
  }
}
