import { Injectable } from '@angular/core';
import { Observable, Subject, filter } from 'rxjs';
import { AppEvent, AppEventType } from './event-types';

@Injectable({ providedIn: 'root' })
export class EventBusService {
  private subject$ = new Subject<AppEvent>();
  events$: Observable<AppEvent> = this.subject$.asObservable();

  on<T extends AppEventType>(type: T): Observable<Extract<AppEvent, { type: T }>> {
    return this.events$.pipe(
      filter((e): e is Extract<AppEvent, { type: T }> => e.type === type),
    );
  }

  emit(event: AppEvent): void {
    this.subject$.next(event);
  }
}
