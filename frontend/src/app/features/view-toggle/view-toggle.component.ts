import { Component, CUSTOM_ELEMENTS_SCHEMA, inject } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';
import { SessionStore } from '../../core/session.store';

@Component({
  selector: 'app-view-toggle',
  standalone: true,
  imports: [TranslocoPipe],
  templateUrl: './view-toggle.component.html',
  styleUrl: './view-toggle.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class ViewToggleComponent {
  store = inject(SessionStore);

  toggleMap() {
    this.store.toggleMap();
  }
  toggleMarey() {
    this.store.toggleMarey();
  }
}
