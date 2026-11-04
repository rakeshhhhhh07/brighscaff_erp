/**
 * Session storage and auth API calls.
 *
 * The JWT lives in localStorage so a refresh keeps you signed in. `api.ts` reads it
 * through `authToken()` on every request, and calls `clearSession()` whenever the
 * server answers 401 so an expired token cannot leave the UI in a half-signed-in state.
 */

export type AuthUser = {
  id: number;
  username: string;
  full_name: string;
  email?: string | null;
  role: 'ADMIN' | 'MANAGER' | 'STAFF';
  is_active: boolean;
  must_change_password: boolean;
  last_login_at?: string | null;
};

export type LoginResult = {
  access_token: string;
  expires_at: number;
  user: AuthUser;
};

const TOKEN_KEY = 'brightscaff.token';
const USER_KEY = 'brightscaff.user';

// Notifies the app when the session is dropped from outside React (e.g. by a 401
// handler deep inside api.ts), so App can route back to the login screen.
export const SESSION_EVENT = 'brightscaff:session-changed';

function emitSessionChange() {
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function authToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function storedUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    // A corrupted entry should not wedge the app on a blank screen.
    return null;
  }
}

export function saveSession(result: LoginResult) {
  localStorage.setItem(TOKEN_KEY, result.access_token);
  localStorage.setItem(USER_KEY, JSON.stringify(result.user));
  emitSessionChange();
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  emitSessionChange();
}

export function isSignedIn(): boolean {
  return Boolean(authToken());
}
