import { CUSTOM_ELEMENTS_SCHEMA, Component, computed, inject } from '@angular/core';
import { CommonModule } from '@angular/common';

import {
  LEARNING_MOMENT_EVENT_LABELS,
  LearningMomentPrediction,
  comparisonRows,
  predictionVerdict,
} from '../../core/learning-moment';
import { SessionStore } from '../../core/session.store';

/**
 * A Learning Moment: predict first, then see what the alternative would have done.
 *
 * Two stages in one surface. Before answering, the operator sees the situation,
 * the question and three options — and nothing about the outcome, because the
 * payload carrying the question does not contain it. After answering, the
 * measured comparison appears together with the reading of it.
 *
 * The template keeps those two apart under separate headings. That is not
 * decoration: the numbers are forward-simulated on forks of the live episode,
 * the prose is generated from those numbers, and an operator who cannot tell
 * which is which cannot judge either. `backend/app/core/learning_moments.py`
 * holds the same boundary on the other side.
 */
@Component({
  selector: 'app-learning-moment',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './learning-moment.component.html',
  styleUrl: './learning-moment.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class LearningMomentComponent {
  private readonly store = inject(SessionStore);

  readonly moment = computed(() => this.store.pendingLearningMoment());
  readonly eventLabel = computed(() => {
    const m = this.moment();
    return m ? LEARNING_MOMENT_EVENT_LABELS[m.eventType] : '';
  });
  readonly rows = computed(() => {
    const m = this.moment();
    return m ? comparisonRows(m) : [];
  });
  readonly verdict = computed(() => {
    const m = this.moment();
    return m ? predictionVerdict(m) : '';
  });

  /** What the operator predicted, as its label, for the reveal. */
  readonly predictionLabel = computed(() => {
    const m = this.moment();
    if (!m?.userPrediction) return '';
    return m.options.find((o) => o.id === m.userPrediction)?.label ?? '';
  });

  answer(prediction: LearningMomentPrediction): void {
    this.store.answerLearningMoment(prediction);
  }

  close(): void {
    this.store.dismissLearningMoment();
  }
}
