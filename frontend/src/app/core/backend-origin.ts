/**
 * Where the FastAPI backend lives, relative to how the page is served.
 *
 * - Local dev: the Angular dev server runs on :4200 while FastAPI runs on :8000,
 *   so we target the same hostname on :8000 (works for localhost and for
 *   phones/other machines hitting the dev host by IP).
 * - Production / anywhere else: the app is served same-origin (FastAPI serving
 *   the built frontend, or a reverse proxy / tunnel), so we use relative /
 *   same-origin URLs and inherit the host and http(s)/ws(s) automatically.
 *
 * This is the single place the backend origin is decided — no hardcoded host.
 */
const DEV_FRONTEND_PORT = '4200';
const DEV_BACKEND_PORT = '8000';

function isDevServer(): boolean {
  return typeof window !== 'undefined' && window.location.port === DEV_FRONTEND_PORT;
}

/** Base for REST calls. `''` means same origin (relative URLs). */
export function backendHttpBase(): string {
  if (isDevServer()) {
    return `${window.location.protocol}//${window.location.hostname}:${DEV_BACKEND_PORT}`;
  }
  return '';
}

/** Base for WebSocket connections, e.g. `wss://host` (no trailing slash). */
export function backendWsBase(): string {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = isDevServer()
    ? `${window.location.hostname}:${DEV_BACKEND_PORT}`
    : window.location.host;
  return `${proto}//${host}`;
}
