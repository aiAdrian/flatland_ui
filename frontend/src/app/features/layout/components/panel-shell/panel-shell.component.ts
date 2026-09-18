import '@sbb-esta/lyne-elements/expansion-panel.js';

import {
  Component,
  CUSTOM_ELEMENTS_SCHEMA,
  ElementRef,
  HostBinding,
  Input,
  OnChanges,
  SimpleChanges,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { PanelInstance } from '../../../../core/layout';
import { LanguageService } from '../../../../core/i18n/language.service';
import { TourContextService } from '../../../../core/demo/tour-context.service';
import { TourGuideService } from '../../../../core/demo/tour-guide.service';
import { PanelPluginHostComponent } from '../panel-plugin-host/panel-plugin-host.component';

@Component({
  selector: 'app-panel-shell',
  standalone: true,
  imports: [PanelPluginHostComponent, TranslocoPipe],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
  templateUrl: './panel-shell.component.html',
  styleUrl: './panel-shell.component.scss',
})
export class PanelShellComponent implements OnChanges {
  @Input({ required: true }) panel!: PanelInstance;

  private readonly tour = inject(TourContextService);
  readonly i18n = inject(LanguageService);

  colearningModule(): string | null {
    return this.tour.moduleFor(this.panel?.type);
  }

  /** Tooltip on a Co-Learning panel's title, naming the module the violet edge
   *  stands for. Replaces the chip the header used to carry. */
  moduleHint(): string | null {
    const module = this.colearningModule();
    return module ? this.i18n.t('panels.moduleHint', { module }) : null;
  }

  private readonly guide = inject(TourGuideService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private wasGuideFocus = false;

  /** The tour guide's current step points at this panel. */
  isGuideFocus(): boolean {
    return !!this.panel && this.guide.highlightPanelType() === this.panel.type;
  }

  constructor() {
    // When the guide moves to this panel, open it and bring it into view: a
    // module that becomes relevant below the fold is a module nobody notices.
    effect(() => {
      const focusType = this.guide.highlightPanelType();
      untracked(() => {
        const on = !!focusType && focusType === this.panel?.type;
        if (on && !this.wasGuideFocus) {
          if (!this.isCanvasPanel) {
            this.expanded.set(true);
            this.panel.collapsed = false;
          }
          queueMicrotask(() => this.revealVertically());
        }
        this.wasGuideFocus = on;
      });
    });
  }

  /**
   * Scroll the nearest vertical scroller so this panel is in view. Not
   * `scrollIntoView`: that also scrolls ancestors sideways, and `app-root` clips
   * a header wider than narrow windows, so the whole app slid left.
   */
  private revealVertically(): void {
    const el = this.host.nativeElement;
    let scroller = el.parentElement;
    while (scroller) {
      const overflowY = getComputedStyle(scroller).overflowY;
      if ((overflowY === 'auto' || overflowY === 'scroll') && scroller.scrollHeight > scroller.clientHeight) break;
      scroller = scroller.parentElement;
    }
    const rect = el.getBoundingClientRect();
    const viewTop = scroller ? scroller.getBoundingClientRect().top : 0;
    const viewBottom = scroller ? scroller.getBoundingClientRect().bottom : window.innerHeight;
    let offset = 0;
    if (rect.top < viewTop) offset = rect.top - viewTop;
    else if (rect.bottom > viewBottom) offset = Math.min(rect.bottom - viewBottom, rect.top - viewTop);
    if (offset === 0) return;
    if (scroller) scroller.scrollBy({ top: offset, behavior: 'smooth' });
    else window.scrollBy({ top: offset, behavior: 'smooth' });
  }

  private currentPanelId: string | null = null;
  readonly expanded = signal(true);

  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['panel'] || !this.panel) {
      return;
    }

    if (this.currentPanelId !== this.panel.id) {
      this.currentPanelId = this.panel.id;
      this.expanded.set(this.isCanvasPanel || !this.panel.collapsed);
    }
  }

  @HostBinding('attr.data-panel-type')
  get hostPanelType(): string | null {
    return this.panel?.type ?? null;
  }

  @HostBinding('attr.data-panel-zone')
  get hostPanelZone(): string | null {
    return this.panel?.zone ?? null;
  }

  @HostBinding('class.layout-panel-shell-host--canvas')
  get isCanvasPanel(): boolean {
    return this.panel?.type === 'flatland-map' || this.panel?.type === 'graphic-timetable';
  }

  @HostBinding('class.layout-panel-shell-host--accordion')
  get isAccordionPanel(): boolean {
    return !this.isCanvasPanel;
  }

  get expandedAttribute(): '' | null {
    return this.expanded() ? '' : null;
  }

  isExpanded(): boolean {
    return this.expanded();
  }

  toggleExpanded(): void {
    if (this.isCanvasPanel) {
      this.expanded.set(true);
      this.panel.collapsed = false;
      return;
    }

    const next = !this.expanded();
    this.expanded.set(next);
    this.panel.collapsed = !next;
  }
}
