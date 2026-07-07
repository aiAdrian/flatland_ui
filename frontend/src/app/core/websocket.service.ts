import { Injectable, signal } from '@angular/core';
import { SessionState } from './models';
import { backendWsBase } from './backend-origin';

export interface WSMessage {
  type: 'state' | 'episode_done' | 'error' | 'pong';
  session_id?: string;
  state?: SessionState;
  message?: string;
}

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private socket: WebSocket | null = null;
  private currentSessionId: string | null = null;
  private reconnectTimer: any = null;
  private shouldReconnect = false;

  readonly connected = signal(false);
  readonly lastMessage = signal<WSMessage | null>(null);
  readonly lastError = signal<string | null>(null);

  connect(sessionId: string) {
    if (this.currentSessionId === sessionId && this.socket?.readyState === WebSocket.OPEN) {
      return;
    }

    this.disconnect();
    this.currentSessionId = sessionId;
    this.shouldReconnect = true;
    this._open();
  }

  private _open() {
    if (!this.currentSessionId) return;

    // Same-origin (wss inherited) in production, localhost:8000 during local
    // dev — see backend-origin. No hardcoded host/port.
    const url = `${backendWsBase()}/ws/session/${this.currentSessionId}`;

    try {
      this.socket = new WebSocket(url);
    } catch (e: any) {
      this.lastError.set(`WS open failed: ${e.message}`);
      this._scheduleReconnect();
      return;
    }

    this.socket.onopen = () => {
      this.connected.set(true);
      this.lastError.set(null);
    };

    this.socket.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as WSMessage;
        this.lastMessage.set(data);
      } catch (e: any) {
        this.lastError.set(`Parse error: ${e.message}`);
      }
    };

    this.socket.onerror = () => {
      this.lastError.set('WebSocket error');
    };

    this.socket.onclose = () => {
      this.connected.set(false);
      this.socket = null;
      if (this.shouldReconnect) {
        this._scheduleReconnect();
      }
    };
  }

  private _scheduleReconnect() {
    if (this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.shouldReconnect) {
        this._open();
      }
    }, 1500);
  }

  disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      try {
        this.socket.close();
      } catch {}
      this.socket = null;
    }
    this.connected.set(false);
    this.currentSessionId = null;
  }

  send(msg: string) {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(msg);
    }
  }
}
