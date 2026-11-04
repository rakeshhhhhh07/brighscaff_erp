import { authToken, clearSession } from './auth';

export const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000/api';

/** Attach the bearer token, plus a JSON content type when there is a body. */
function headers(hasBody: boolean): HeadersInit {
  const h: Record<string, string> = {};
  if (hasBody) h['Content-Type'] = 'application/json';
  const token = authToken();
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

/**
 * Turn a non-2xx response into an Error carrying the server's message.
 *
 * A 401 means the token is missing or expired, so the session is dropped here;
 * App listens for that and shows the login screen again.
 */
async function failure(r: Response): Promise<Error> {
  const body = await r.json().catch(() => ({}) as { message?: string });
  if (r.status === 401) {
    clearSession();
    return new Error(body.message || 'Your session has expired. Please sign in again.');
  }
  return new Error(body.message || `API request failed (${r.status})`);
}

async function send<T>(path: string, init: RequestInit, hasBody: boolean): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, { ...init, headers: headers(hasBody) });
  if (!r.ok) throw await failure(r);
  return (await r.json().catch(() => ({}))) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return send<T>(path, { method: 'GET' }, false);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return send<T>(path, { method: 'POST', body: JSON.stringify(body) }, true);
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  return send<T>(path, { method: 'PUT', body: JSON.stringify(body) }, true);
}

export async function apiDelete<T>(path: string, body?: unknown): Promise<T> {
  return send<T>(
    path,
    { method: 'DELETE', body: body ? JSON.stringify(body) : undefined },
    Boolean(body),
  );
}

/** Authenticated file download, used by the statement Excel/PDF exports. */
export async function apiDownload(path: string): Promise<Blob> {
  const r = await fetch(`${API_BASE}${path}`, { headers: headers(false) });
  if (!r.ok) throw await failure(r);
  return r.blob();
}
