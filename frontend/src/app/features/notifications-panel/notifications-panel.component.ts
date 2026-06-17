import { Component, CUSTOM_ELEMENTS_SCHEMA, effect, inject, OnDestroy} from '@angular/core';
import { SessionStore } from '../../core/session.store';
import { ApiService } from '../../core/api.service';
import { EventBusService } from '../../core/events/event-bus.service';
import { AgentColorService } from '../../core/agent-color.service';
import { AppNotification } from '../../core/events/event-types';

@Component({
  selector: 'app-notifications-panel',
  standalone: true,
  templateUrl: './notifications-panel.component.html',
  styleUrl: './notifications-panel.component.scss',
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class NotificationsPanelComponent implements OnDestroy {
  store = inject(SessionStore);
  api = inject(ApiService);
  bus = inject(EventBusService);
  colors = inject(AgentColorService);

  private _notifPollHandle: any = null;
  private _notifLastSession: string | null = null;

  constructor() {
    // Notifications used to refetch on every state update with a 'cheap,
    // mock anyway' comment — but the backend now actually computes them
    // and pulling 2×/sec from a state-driven effect blocks /pause and
    // makes Play feel unresponsive (see scenario-panel for the same fix).
    //
    // New strategy: throttle to ~2s while a session is active. Also
    // refetch immediately when Play stops, so the user sees fresh
    // notifications right after pausing.
    let lastPlaying = false;
    effect(() => {
      const sess = this.store.session();
      const playing = this.store.playing();

      if (!sess) {
        this.store.notifications.set([]);
        this._stopNotifPolling();
        this._notifLastSession = null;
        lastPlaying = false;
        return;
      }

      const sessionChanged = sess.id !== this._notifLastSession;
      const stoppedPlaying = lastPlaying && !playing;

      // Immediate fetch on session change or pause-end.
      if (sessionChanged || stoppedPlaying) {
        this._fetchNotifications(sess.id);
      }

      // Slow background refresh (every 2s) while session is alive,
      // so live deadlock/conflict notifications appear within a couple
      // of seconds even during Play.
      if (sessionChanged) {
        this._stopNotifPolling();
        this._notifPollHandle = setInterval(() => {
          this._fetchNotifications(sess.id);
        }, 2000);
      }

      this._notifLastSession = sess.id;
      lastPlaying = playing;
    });
  }

  private _fetchNotifications(sessionId: string): void {
    this.api.getNotifications(sessionId).subscribe({
      next: (notifications) => this.store.notifications.set(notifications),
      error: () => {},
    });
  }

  private _stopNotifPolling(): void {
    if (this._notifPollHandle !== null) {
      clearInterval(this._notifPollHandle);
      this._notifPollHandle = null;
    }
  }

  notificationAgentHandles(n: AppNotification): number[] {
    const out = new Set<number>();

    // Structured relation from backend.
    if (n.relatedElement?.kind === 'train') {
      const h = Number(n.relatedElement.id);
      if (Number.isFinite(h)) out.add(h);
    }

    // Defensive fallback: parse "Train 2", "Train #2", "Agent 2",
    // "agent #2" from title/message.
    const text = `${n.title ?? ''} ${n.message ?? ''}`;
    const re = /\b(?:train|agent)\s*#?\s*(\d+)\b/gi;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      const h = Number(m[1]);
      if (Number.isFinite(h)) out.add(h);
    }

    return Array.from(out);
  }

  primaryNotificationAgentHandle(n: AppNotification): number | null {
    const handles = this.notificationAgentHandles(n);
    if (handles.length === 0) return null;

    // If one of the notification-related agents is already selected,
    // clicking the notification should behave exactly like clicking that
    // selected agent again: toggle it off.
    const selected = this.store.selectedHandle();
    if (selected != null && handles.includes(selected)) {
      return selected;
    }

    // Otherwise select the first related agent.
    return handles[0];
  }

  singleNotificationAgentHandle(n: AppNotification): number | null {
    const handles = this.notificationAgentHandles(n);
    return handles.length === 1 ? handles[0] : null;
  }

  notificationAgentColor(n: AppNotification): string | null {
    const h = this.singleNotificationAgentHandle(n);
    return h == null ? null : this.colors.getColorSolid(h);
  }

  isAgentRelated(n: AppNotification): boolean {
    return this.notificationAgentHandles(n).length > 0;
  }

  isSelectedAgentRelated(n: AppNotification): boolean {
    const selected = this.store.selectedHandle();
    if (selected == null) return false;
    return this.notificationAgentHandles(n).includes(selected);
  }

  isHoveredAgentRelated(n: AppNotification): boolean {
    const hovered = this.store.notificationHoverHandles();
    if (hovered.size === 0) return false;
    return this.notificationAgentHandles(n).some((h) => hovered.has(h));
  }


  onNotificationMouseEnter(n: AppNotification): void {
    const handles = this.notificationAgentHandles(n);

    if (handles.length > 0) {
      // Same cross-panel hover behaviour as hovering agent(s) directly.
      this.store.setAgentHoverAgents(handles);
    }
  }

  onNotificationMouseLeave(): void {
    // Same cross-panel hover clear behaviour as leaving an agent.
    this.store.clearAgentHoverAgents();
  }

  onNotificationClick(n: AppNotification): void {
    const handle = this.primaryNotificationAgentHandle(n);

    if (handle != null) {
      // Same behaviour as clicking the agent in the Flatland grid map:
      // select if not selected, deselect if already selected.
      this.store.toggleAgentSelection(handle);
      return;
    }

    // Non-agent notifications keep the previous infrastructure focus behaviour.
    if (n.relatedElement) {
      this.bus.emit({
        type: 'FOCUS_INFRASTRUCTURE_ELEMENT',
        kind: n.relatedElement.kind,
        id: n.relatedElement.id,
      });
    }
  }

  dismiss(n: AppNotification, event: Event) {
    event.stopPropagation();
    this.bus.emit({ type: 'NOTIFICATION_DISMISSED', notificationId: n.id });
    const cur = this.store.notifications();
    this.store.notifications.set(cur.filter((x) => x.id !== n.id));
  }

  iconFor(kind: string): string {
    switch (kind) {
      case 'error':
        return '⛔';
      case 'warning':
        return '⚠';
      default:
        return 'ⓘ';
    }
  }

  ngOnDestroy() {
    this._stopNotifPolling();
  }
}
