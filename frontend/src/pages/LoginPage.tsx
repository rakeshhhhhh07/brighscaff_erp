import { FormEvent, useState } from 'react';
import { Eye, EyeOff, Loader2, Lock, LogIn, User } from 'lucide-react';
import { apiPost } from '../api';
import { saveSession, type LoginResult } from '../services/auth';

type Props = {
  onSignedIn: () => void;
};

export default function LoginPage({ onSignedIn }: Props) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const result = await apiPost<LoginResult>('/auth/login', {
        username: username.trim(),
        password,
      });
      saveSession(result);
      onSignedIn();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in');
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-shell">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-name">
            BRIGHT <span>SCAFF.</span>
          </div>
          <div className="brand-sub">ERP</div>
        </div>

        <h1 className="login-title">Sign in</h1>
        <p className="login-subtitle">Use your workspace account to continue.</p>

        <form onSubmit={submit} className="login-form">
          <label className="login-field">
            <span>Username</span>
            <div className="login-input">
              <User size={17} />
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
                placeholder="admin"
              />
            </div>
          </label>

          <label className="login-field">
            <span>Password</span>
            <div className="login-input">
              <Lock size={17} />
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                placeholder="••••••••"
              />
              <button
                type="button"
                className="login-reveal"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </label>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <button className="btn btn-primary login-submit" type="submit" disabled={busy}>
            {busy ? <Loader2 size={17} className="spin" /> : <LogIn size={17} />}
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  );
}
