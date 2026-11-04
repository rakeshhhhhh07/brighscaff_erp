import { FormEvent, useEffect, useState } from 'react';
import { KeyRound, Plus, ShieldCheck, UserCog, Users as UsersIcon } from 'lucide-react';
import Modal from '../components/ui/Modal';
import { apiGet, apiPost, apiPut } from '../api';
import type { AuthUser } from '../services/auth';

type LoginAudit = {
  id: number;
  username: string;
  event_type: string;
  success: boolean;
  ip_address?: string | null;
  detail?: string | null;
  created_at: string;
};

type Props = {
  currentUser: AuthUser | null;
};

const ROLES: AuthUser['role'][] = ['ADMIN', 'MANAGER', 'STAFF'];
const MIN_PASSWORD = 8;

export default function SettingsPage({ currentUser }: Props) {
  const [tab, setTab] = useState<'users' | 'activity' | 'account'>('users');
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [audit, setAudit] = useState<LoginAudit[]>([]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [resetFor, setResetFor] = useState<AuthUser | null>(null);
  const [busy, setBusy] = useState(false);

  const isAdmin = currentUser?.role === 'ADMIN';

  async function loadUsers() {
    try {
      const r = await apiGet<{ items: AuthUser[] }>('/auth/users');
      setUsers(r.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load users');
    }
  }

  async function loadAudit() {
    try {
      const r = await apiGet<{ items: LoginAudit[] }>('/auth/login-audit');
      setAudit(r.items || []);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load activity');
    }
  }

  useEffect(() => {
    if (!isAdmin) return;
    if (tab === 'users') loadUsers();
    if (tab === 'activity') loadAudit();
  }, [tab, isAdmin]);

  function flash(message: string) {
    setNotice(message);
    setError('');
    window.setTimeout(() => setNotice(''), 4000);
  }

  async function createUser(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    try {
      await apiPost('/auth/users', {
        username: String(f.get('username') || '').trim(),
        full_name: String(f.get('full_name') || '').trim(),
        email: String(f.get('email') || '').trim() || null,
        password: String(f.get('password') || ''),
        role: String(f.get('role') || 'STAFF'),
        must_change_password: f.get('must_change_password') === 'on',
      });
      setShowCreate(false);
      flash('User created.');
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create user');
    } finally {
      setBusy(false);
    }
  }

  async function updateUser(user: AuthUser, patch: Partial<AuthUser>) {
    try {
      await apiPut(`/auth/users/${user.id}`, patch);
      flash('User updated.');
      loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update user');
    }
  }

  async function resetPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!resetFor) return;
    const f = new FormData(e.currentTarget);
    setBusy(true);
    try {
      await apiPost(`/auth/users/${resetFor.id}/reset-password`, {
        password: String(f.get('password') || ''),
        must_change_password: f.get('must_change_password') === 'on',
      });
      setResetFor(null);
      flash('Password reset.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reset password');
    } finally {
      setBusy(false);
    }
  }

  async function changeOwnPassword(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    setBusy(true);
    try {
      await apiPost('/auth/change-password', {
        current_password: String(f.get('current_password') || ''),
        new_password: String(f.get('new_password') || ''),
      });
      form.reset();
      flash('Your password has been changed.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to change password');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">CONFIGURATION</div>
          <h2>Workspace settings</h2>
          <p className="muted">Manage user access, review login activity, and secure your account.</p>
        </div>
      </div>

      <div className="tab-row">
        {(['users', 'activity', 'account'] as const).map((t) => (
          <button
            key={t}
            className={`tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
            disabled={t !== 'account' && !isAdmin}
            title={t !== 'account' && !isAdmin ? 'Administrators only' : undefined}
          >
            {t === 'users' && <UsersIcon size={16} />}
            {t === 'activity' && <ShieldCheck size={16} />}
            {t === 'account' && <UserCog size={16} />}
            {t === 'users' ? 'Users' : t === 'activity' ? 'Login activity' : 'My account'}
          </button>
        ))}
      </div>

      {notice && <div className="banner success">{notice}</div>}
      {error && <div className="banner error">{error}</div>}

      {tab === 'users' && isAdmin && (
        <div className="card">
          <div className="card-head">
            <h3>User accounts</h3>
            <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
              <Plus size={16} /> Add user
            </button>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Username</th>
                  <th>Full name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Last login</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td>
                      <strong>{u.username}</strong>
                      {u.id === currentUser?.id && <span className="pill subtle">you</span>}
                    </td>
                    <td>{u.full_name}</td>
                    <td>{u.email || '—'}</td>
                    <td>
                      <select
                        value={u.role}
                        disabled={u.id === currentUser?.id}
                        onChange={(e) =>
                          updateUser(u, { role: e.target.value as AuthUser['role'] })
                        }
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>
                            {r}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <span className={`pill ${u.is_active ? 'ok' : 'muted'}`}>
                        {u.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td>{u.last_login_at ? u.last_login_at.slice(0, 16) : 'Never'}</td>
                    <td className="row-actions">
                      <button className="btn btn-secondary" onClick={() => setResetFor(u)}>
                        <KeyRound size={15} /> Reset
                      </button>
                      <button
                        className="btn btn-secondary"
                        disabled={u.id === currentUser?.id}
                        onClick={() => updateUser(u, { is_active: !u.is_active })}
                      >
                        {u.is_active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                ))}
                {!users.length && (
                  <tr>
                    <td colSpan={7} className="empty">
                      No users yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'activity' && isAdmin && (
        <div className="card">
          <div className="card-head">
            <h3>Recent login activity</h3>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Username</th>
                  <th>Event</th>
                  <th>Result</th>
                  <th>IP address</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id}>
                    <td>{a.created_at.slice(0, 19)}</td>
                    <td>{a.username}</td>
                    <td>{a.event_type.replace(/_/g, ' ').toLowerCase()}</td>
                    <td>
                      <span className={`pill ${a.success ? 'ok' : 'danger'}`}>
                        {a.success ? 'Success' : 'Failed'}
                      </span>
                    </td>
                    <td>{a.ip_address || '—'}</td>
                    <td>{a.detail || '—'}</td>
                  </tr>
                ))}
                {!audit.length && (
                  <tr>
                    <td colSpan={6} className="empty">
                      No activity recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'account' && (
        <div className="card narrow">
          <div className="card-head">
            <h3>Change my password</h3>
          </div>
          <form className="form-grid" onSubmit={changeOwnPassword}>
            <label>
              <span>Current password</span>
              <input name="current_password" type="password" required autoComplete="current-password" />
            </label>
            <label>
              <span>New password</span>
              <input
                name="new_password"
                type="password"
                required
                minLength={MIN_PASSWORD}
                autoComplete="new-password"
              />
              <small className="muted">At least {MIN_PASSWORD} characters.</small>
            </label>
            <div className="form-actions">
              <button className="btn btn-primary" type="submit" disabled={busy}>
                Update password
              </button>
            </div>
          </form>
        </div>
      )}

      {!isAdmin && tab !== 'account' && (
        <div className="card">
          <p className="muted">Only administrators can manage users and view login activity.</p>
        </div>
      )}

      {showCreate && (
        <Modal
          title="Add user"
          subtitle="Create a login for a colleague and choose their access level."
          onClose={() => setShowCreate(false)}
        >
          <form className="form-grid" onSubmit={createUser}>
            <label>
              <span>Username</span>
              <input name="username" required minLength={3} autoFocus />
            </label>
            <label>
              <span>Full name</span>
              <input name="full_name" required />
            </label>
            <label>
              <span>Email</span>
              <input name="email" type="email" />
            </label>
            <label>
              <span>Role</span>
              <select name="role" defaultValue="STAFF">
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>Temporary password</span>
              <input name="password" type="text" required minLength={MIN_PASSWORD} />
              <small className="muted">At least {MIN_PASSWORD} characters.</small>
            </label>
            <label className="checkbox-row">
              <input name="must_change_password" type="checkbox" defaultChecked />
              <span>Require a password change at first sign in</span>
            </label>
            <div className="form-actions">
              <button className="btn btn-secondary" type="button" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
              <button className="btn btn-primary" type="submit" disabled={busy}>
                Create user
              </button>
            </div>
          </form>
        </Modal>
      )}

      {resetFor && (
        <Modal
          title={`Reset password — ${resetFor.username}`}
          subtitle="Set a new password and share it with the user securely."
          onClose={() => setResetFor(null)}
        >
          <form className="form-grid" onSubmit={resetPassword}>
            <label>
              <span>New password</span>
              <input name="password" type="text" required minLength={MIN_PASSWORD} autoFocus />
            </label>
            <label className="checkbox-row">
              <input name="must_change_password" type="checkbox" defaultChecked />
              <span>Require a password change at next sign in</span>
            </label>
            <div className="form-actions">
              <button className="btn btn-secondary" type="button" onClick={() => setResetFor(null)}>
                Cancel
              </button>
              <button className="btn btn-primary" type="submit" disabled={busy}>
                Reset password
              </button>
            </div>
          </form>
        </Modal>
      )}
    </section>
  );
}
