import { Bell, Menu } from 'lucide-react';
import type { NavKey } from '../../types';
export default function Topbar({
  active,
  connected,
  onMenu,
}: {
  active: NavKey;
  connected: boolean;
  onMenu: () => void;
}) {
  return (
    <header className="topbar">
      <div className="topbar-left">
        <button className="icon-button mobile-menu" onClick={onMenu} aria-label="Open navigation">
          <Menu size={22} />
        </button>
        <div className="breadcrumb">
          Workspace <span>/</span> <strong>{active}</strong>
        </div>
      </div>
      <div className="topbar-actions">
        <div className={`api-status ${connected ? 'connected' : ''}`}>
          <span />
          {connected ? 'API connected' : 'Demo preview'}
        </div>
        <button className="icon-button notification-button" aria-label="Notifications">
          <Bell size={20} />
        </button>
        <div className="top-avatar">AD</div>
      </div>
    </header>
  );
}
