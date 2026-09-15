import { Component, computed, inject } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { TourGuideService } from '../../core/demo/tour-guide.service';
import { GuideLoop, TourGuideStep } from '../../core/demo/tour-briefings';

const LOOP_LABEL: Record<GuideLoop, string> = {
  operational: 'Betrieb',
  learning: 'Lernen',
};

interface GuideGroup {
  loop: GuideLoop;
  label: string;
  steps: { step: TourGuideStep; n: number }[];
}

/**
 * Guide strip for a tour with `TourBriefing.guide`: the interaction flow as
 * numbered steps grouped by loop, ticking itself as the run shows each step,
 * with a one-line hint for the step that comes next.
 */
@Component({
  selector: 'app-tour-guide',
  standalone: true,
  templateUrl: './tour-guide.component.html',
  styleUrl: './tour-guide.component.scss',
})
export class TourGuideComponent {
  readonly guide = inject(TourGuideService);
  readonly store = inject(SessionStore);

  readonly afterLiveHint =
    'Alle Schritte während der Fahrt sind erlebt. Beenden Sie die Schicht: danach folgen Schichtbilanz, Event-Simulation und was die KI gelernt hat.';

  readonly groups = computed<GuideGroup[]>(() => {
    const groups: GuideGroup[] = [];
    this.guide.steps().forEach((step, i) => {
      let group = groups[groups.length - 1];
      if (!group || group.loop !== step.loop) {
        group = { loop: step.loop, label: LOOP_LABEL[step.loop], steps: [] };
        groups.push(group);
      }
      group.steps.push({ step, n: i + 1 });
    });
    return groups;
  });

  readonly currentNumber = computed(() => {
    const current = this.guide.current();
    return current ? this.guide.steps().indexOf(current) + 1 : null;
  });
}
