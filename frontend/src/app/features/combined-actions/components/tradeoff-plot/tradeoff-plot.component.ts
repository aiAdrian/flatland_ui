import { Component, Input, computed, signal } from '@angular/core';

/** One action version on the energy ↔ delay plane. */
export interface TradeoffPoint {
  id: string;
  packageId: string;
  /** Short mark drawn in the dot ('A', 'B', "A′"). */
  label: string;
  origin: 'ai' | 'human';
  recommended: boolean;
  /** This is the version its card is currently showing. */
  active: boolean;
  delayReductionMin: number;
  energyKwh: number;
}

interface PlottedPoint extends TradeoffPoint {
  x: number;
  y: number;
}

/** The move from an AI proposal to the dispatcher's variant of it. */
interface TradeArrow {
  packageId: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  deltaMin: number;
  deltaKwh: number;
  /** The variant is better on both axes — rare, and worth saying. */
  dominates: boolean;
  /** Where the inline label sits, clamped inside the plot box. */
  labelX: number;
  labelY: number;
  /** False for a short arrow: the label would sit on top of its own dots, and
   *  the readout line underneath already carries the figures. */
  showLabel: boolean;
}

/**
 * Energy against delay for every action version on the panel.
 *
 * A single "↓ 14 min" hides the price of those minutes. Holding a heavy train
 * back to let a lighter one through can buy delay and pay for it in traction
 * energy, and no per-card number shows that — you have to see the options on
 * the same two axes. This is the Evaluative-AI move from T2.3: expected outcome
 * per alternative, on the axes the operator actually trades off, rather than
 * one opaque score.
 *
 * Both axes read so that **up and to the right is better**: more delay saved,
 * less energy spent. The arrow from an AI dot to its variant is the part that
 * matters most — it names the trade the dispatcher just made, in the direction
 * they made it.
 */
@Component({
  selector: 'app-tradeoff-plot',
  standalone: true,
  templateUrl: './tradeoff-plot.component.html',
  styleUrl: './tradeoff-plot.component.scss',
})
export class TradeoffPlotComponent {
  /** Signal-backed: `plotted` is a `computed`, and a computed over a plain
   *  `@Input` field never invalidates — the plot would keep drawing whatever it
   *  saw on its first render and a new variant would never appear. */
  private readonly _points = signal<readonly TradeoffPoint[]>([]);

  @Input() set points(value: readonly TradeoffPoint[]) {
    this._points.set(value ?? []);
  }

  readonly hovered = signal<string | null>(null);

  readonly width = 280;
  readonly height = 150;
  private readonly pad = { top: 20, right: 18, bottom: 26, left: 44 };

  /** Fraction of each axis kept clear at both ends.
   *
   *  Without it the cheapest option lands exactly ON the energy axis and the
   *  weakest one exactly ON the delay axis, which reads as a rendering fault
   *  rather than as data — and the best option gets pinned into the corner
   *  where its "recommended" ring is clipped. */
  private static readonly INSET = 0.12;

  readonly bounds = computed(() => {
    const pts = this._points();
    const delays = pts.map((p) => p.delayReductionMin);
    const energies = pts.map((p) => p.energyKwh);
    return {
      dMin: Math.min(...delays),
      dMax: Math.max(...delays),
      eMin: Math.min(...energies),
      eMax: Math.max(...energies),
    };
  });

  readonly plotted = computed<PlottedPoint[]>(() => {
    const pts = this._points();
    if (!pts.length) return [];
    const { dMin, dMax, eMin, eMax } = this.bounds();

    const innerW = this.width - this.pad.left - this.pad.right;
    const innerH = this.height - this.pad.top - this.pad.bottom;

    // A single point (or a flat axis) lands in the middle rather than dividing
    // by zero — one option is still worth drawing.
    const inset = TradeoffPlotComponent.INSET;
    const fit = (t: number) => inset + t * (1 - 2 * inset);
    const sx = (v: number) => fit(dMax === dMin ? 0.5 : (v - dMin) / (dMax - dMin));
    const sy = (v: number) => fit(eMax === eMin ? 0.5 : (v - eMin) / (eMax - eMin));

    return pts.map((p) => ({
      ...p,
      x: this.pad.left + sx(p.delayReductionMin) * innerW,
      // SVG y grows downward, so mapping energy straight onto it puts the
      // cheapest option at the top — the "up is better" reading the axes promise.
      y: this.pad.top + sy(p.energyKwh) * innerH,
    }));
  });

  /**
   * One arrow per package that has a variant, drawn from the AI dot to it.
   *
   * This is the sentence the plot exists to say: "you traded 4 minutes for 31
   * kWh, in this direction." Two loose dots leave the reader to work that out.
   */
  readonly arrows = computed<TradeArrow[]>(() => {
    const byPackage = new Map<string, PlottedPoint[]>();
    for (const p of this.plotted()) {
      const list = byPackage.get(p.packageId) ?? [];
      list.push(p);
      byPackage.set(p.packageId, list);
    }

    const out: TradeArrow[] = [];
    for (const [packageId, list] of byPackage) {
      const ai = list.find((p) => p.origin === 'ai');
      const human = list.find((p) => p.origin === 'human');
      if (!ai || !human) continue;
      const length = Math.hypot(human.x - ai.x, human.y - ai.y);
      out.push({
        packageId,
        x1: ai.x,
        y1: ai.y,
        x2: human.x,
        y2: human.y,
        deltaMin: human.delayReductionMin - ai.delayReductionMin,
        deltaKwh: human.energyKwh - ai.energyKwh,
        dominates:
          human.delayReductionMin >= ai.delayReductionMin && human.energyKwh <= ai.energyKwh,
        labelX: Math.min(
          Math.max((ai.x + human.x) / 2, this.pad.left + 26),
          this.width - this.pad.right - 26,
        ),
        labelY: Math.max((ai.y + human.y) / 2 - 9, this.pad.top - 6),
        showLabel: length > 34,
      });
    }
    return out;
  });

  /** The drawing box, so the template can place axes and grid without repeating
   *  the padding arithmetic. */
  readonly box = computed(() => ({
    left: this.pad.left,
    right: this.width - this.pad.right,
    top: this.pad.top,
    bottom: this.height - this.pad.bottom,
  }));

  /** Two faint gridlines per axis. Enough to judge "further right / higher up"
   *  at a glance; more would be chart-junk at this size. */
  readonly grid = computed(() => {
    const b = this.box();
    const xs = [1, 2].map((i) => b.left + ((b.right - b.left) * i) / 3);
    const ys = [1, 2].map((i) => b.top + ((b.bottom - b.top) * i) / 3);
    return { xs, ys };
  });

  /** Axis end labels, so the dots carry units rather than only relative position. */
  readonly axisLabels = computed(() => {
    const { dMin, dMax, eMin, eMax } = this.bounds();
    return {
      // The energy axis runs cheapest-at-the-top, so its low number belongs at
      // the top. Spelled with the unit at both ends, because a bare "244" above
      // a bare "302" looks like an axis drawn upside down.
      delayLow: `−${dMin} min`,
      delayHigh: `−${dMax} min`,
      energyLow: `${eMin} kWh`,
      energyHigh: `${eMax} kWh`,
      flatDelay: dMin === dMax,
      flatEnergy: eMin === eMax,
    };
  });

  radius(p: PlottedPoint): number {
    return p.active ? 9 : 6;
  }

  /** Figures beside the dot the card is actually showing, so the common case
   *  needs no hovering at all. */
  showValue(p: PlottedPoint): boolean {
    return p.active;
  }

  valueLabel(p: PlottedPoint): string {
    return `−${p.delayReductionMin}′ · ${p.energyKwh}`;
  }

  /** Keep the label inside the box: a dot near the right edge labels leftwards. */
  valueAnchor(p: PlottedPoint): 'start' | 'end' {
    return p.x > (this.box().left + this.box().right) / 2 ? 'end' : 'start';
  }

  valueX(p: PlottedPoint): number {
    return this.valueAnchor(p) === 'end' ? p.x - this.radius(p) - 4 : p.x + this.radius(p) + 4;
  }

  onEnter(id: string): void {
    this.hovered.set(id);
  }

  onLeave(): void {
    this.hovered.set(null);
  }

  readonly hoveredPoint = computed<PlottedPoint | null>(
    () => this.plotted().find((p) => p.id === this.hovered()) ?? null,
  );

  /** Falls back to the arrow's trade when nothing is hovered — the readout line
   *  should say something useful the moment a variant exists. */
  readonly readout = computed<string>(() => {
    const point = this.hoveredPoint();
    if (point) {
      return `${point.label} · ${point.origin === 'ai' ? 'AI proposal' : 'your variant'} · −${point.delayReductionMin} min · ${point.energyKwh} kWh`;
    }
    const arrow = this.arrows()[0];
    if (arrow) {
      // Spelled out rather than signed. "−1 min saved" reads as a saving to
      // half the people who see it; "1 min less delay saved" cannot.
      const delay =
        arrow.deltaMin === 0
          ? 'the same delay saved'
          : `${Math.abs(arrow.deltaMin)} min ${arrow.deltaMin > 0 ? 'more' : 'less'} delay saved`;
      const energy =
        arrow.deltaKwh === 0
          ? 'the same energy'
          : `${Math.abs(arrow.deltaKwh)} kWh ${arrow.deltaKwh > 0 ? 'more' : 'less'} energy`;
      return `Your variant of ${arrow.packageId}: ${delay}, ${energy}.`;
    }
    return 'Point at a dot for its figures.';
  });
}
