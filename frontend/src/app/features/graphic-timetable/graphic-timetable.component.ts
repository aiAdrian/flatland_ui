import { Component, CUSTOM_ELEMENTS_SCHEMA } from '@angular/core';
import { MareyChartComponent } from '../marey-chart/marey-chart.component';

/**
 * Graphic-Timetable: Time-Distance-Diagramm der Zugbewegungen.
 * Aktuell duenner Wrapper um MareyChart.
 */
@Component({
  selector: 'app-graphic-timetable',
  standalone: true,
  imports: [MareyChartComponent],
  template: `
    <div class="timetable-host">
      <app-marey-chart></app-marey-chart>
    </div>
  `,
  styles: [`
    :host {
      display: block;
      position: relative;
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      box-sizing: border-box;
    }

    .timetable-host {
      display: block;
      position: relative;
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      box-sizing: border-box;
    }

    app-marey-chart {
      display: block;
      position: relative;
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      box-sizing: border-box;
    }
  `],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class GraphicTimetableComponent {}
