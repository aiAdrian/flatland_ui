import { Component, computed, effect, inject, untracked } from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { TourContextService } from '../../core/demo/tour-context.service';
import { ReflectionPromptComponent } from '../reflection-prompt/reflection-prompt.component';

/**
 * "Warum diese Entscheidung?" as a dialog, for a tour that asks for it
 * (`TourBriefing.reasonDialog`).
 *
 * In the reflection panel the question is easy to miss while the run goes on. The
 * dialog pauses the run as soon as a decision asks for a reason and resumes it
 * once the reason is given or the question is dismissed — only if it was running
 * before, and not once the shift is over. The capture itself is the unchanged
 * `app-reflection-prompt` — the reflection with guided questions; the experiments
 * keep `app-rationale-capture` in their reflection panel.
 */
@Component({
  selector: 'app-tour-reason-dialog',
  standalone: true,
  imports: [ReflectionPromptComponent],
  templateUrl: './tour-reason-dialog.component.html',
  styleUrl: './tour-reason-dialog.component.scss',
})
export class TourReasonDialogComponent {
  private readonly store = inject(SessionStore);
  private readonly tour = inject(TourContextService);

  readonly open = computed(
    () =>
      this.tour.reasonDialog() &&
      this.store.interactionMode() !== 'director' &&
      this.store.pendingRationale() !== null,
  );

  private wasOpen = false;
  private resumeOnClose = false;

  constructor() {
    effect(() => {
      const open = this.open();
      untracked(() => {
        if (open && !this.wasOpen) {
          this.resumeOnClose = this.store.playing();
          if (this.resumeOnClose) this.store.pause();
        } else if (!open && this.wasOpen) {
          if (this.resumeOnClose && !this.store.shiftReviewOpen()) {
            this.store.play(this.store.activePolicy() || this.store.defaultPolicy(), this.store.playSpeed());
          }
          this.resumeOnClose = false;
        }
        this.wasOpen = open;
      });
    });
  }
}
