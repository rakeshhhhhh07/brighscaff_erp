import {
  Activity,
  Boxes,
  ClipboardList,
  FileText,
  LayoutDashboard,
  LifeBuoy,
  LogOut,
  Settings2,
  Users,
  X,
} from 'lucide-react';
import type { NavKey } from '../../types';
import type { AuthUser } from '../../services/auth';
type Props = {
  active: NavKey;
  open: boolean;
  onNavigate: (key: NavKey) => void;
  onClose: () => void;
  user: AuthUser | null;
  onSignOut: () => void;
};

/** "Admin User" -> "AU"; falls back to the first two characters of the username. */
function initials(user: AuthUser | null) {
  if (!user) return '?';
  const fromName = user.full_name
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w[0])
    .slice(0, 2)
    .join('');
  return (fromName || user.username.slice(0, 2)).toUpperCase();
}
const nav: { label: NavKey; icon: any; section?: string }[] = [
  { label: 'Dashboard', icon: LayoutDashboard, section: 'WORKSPACE' },
  { label: 'Customers', icon: Users },
  { label: 'Inventory', icon: Boxes },
  { label: 'Rentals', icon: ClipboardList },
  { label: 'Billing & Ledgers', icon: FileText },
  { label: 'Reports', icon: Activity, section: 'INSIGHTS' },
  { label: 'Settings', icon: Settings2, section: 'SYSTEM' },
];
export default function Sidebar({ active, open, onNavigate, onClose, user, onSignOut }: Props) {
  return (
    <>
      <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div>
            <div>
              BRIGHT <span>SCAFF.</span>
            </div>
            <div className="brand-sub">ERP</div>
          </div>

        </div>
        <nav className="nav-list">
          {nav.map((n) => (
            <div key={n.label}>
              {n.section && <div className="nav-section">{n.section}</div>}
              <button
                className={`nav-item ${active === n.label ? 'active' : ''}`}
                onClick={() => {
                  onNavigate(n.label);
                  onClose();
                }}
              >
                <n.icon size={20} />
                <span>{n.label}</span>
              </button>
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <a
            className="help-card"
            href="https://www.scaffoldingkochi.com/"
            target="_blank"
            // noreferrer also implies noopener, which stops the opened page
            // reaching back into this one via window.opener.
            rel="noreferrer"
          >
            <div className="help-icon">
              <LifeBuoy size={19} />
            </div>
            <div>
              <strong>Need a hand?</strong>
              <p>Help and support</p>
            </div>
          </a>
          <div className="profile-row">
            <div className="avatar">{initials(user)}</div>
            <div className="profile-text">
              <strong>{user?.full_name || 'Signed out'}</strong>
              <span>{user ? user.role.toLowerCase() : ''}</span>
            </div>
            <button className="icon-button" onClick={onSignOut} aria-label="Sign out" title="Sign out">
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      {open && <button className="mobile-overlay" aria-label="Close menu" onClick={onClose} />}
    </>
  );
}
