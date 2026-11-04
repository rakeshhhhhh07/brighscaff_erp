import {
  ArrowRight,
  Boxes,
  ClipboardList,
  FileText,
  Plus,
  Truck,
  Users,
  Wallet,
} from 'lucide-react';
import type { NavKey, Summary } from '../types';
import { money } from '../services/formatters';
type Props = { summary: Summary; onNavigate: (key: NavKey) => void };
export default function DashboardPage({ summary, onNavigate }: Props) {
  const cards = [
    {
      label: 'Total customers',
      value: summary.customers.toLocaleString('en-IN'),
      change: 'Saved customer records',
      icon: Users,
      tint: 'violet',
    },
    {
      label: 'Active rentals',
      value: summary.active_rentals.toLocaleString('en-IN'),
      change: 'Open delivery bills',
      icon: ClipboardList,
      tint: 'blue',
    },
    {
      label: 'Items on rent',
      value: summary.items_on_rent.toLocaleString('en-IN'),
      change: 'Units currently issued',
      icon: Truck,
      tint: 'amber',
    },
    {
      label: 'Rent accrued',
      value: money(summary.rent_accrued),
      change: 'Billed across all deliveries',
      icon: Wallet,
      tint: 'green',
    },
  ];
  return (
    <>
      <div className="welcome-row">
        <div>
          <div className="eyebrow">
            RENTAL OPERATIONS <span className="eyebrow-line" />
          </div>
          <h1>BRIGHT SCAFF. dashboard</h1>
          <p className="page-subtitle">
            Live overview based only on records saved in your database.
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => onNavigate('Customers')}>
          <Plus size={19} />
          Add customer
        </button>
      </div>
      <section className="stat-grid">
        {cards.map((c) => (
          <div className="stat-card" key={c.label}>
            <div className="stat-top">
              <span className="stat-label">{c.label}</span>
              <span className={`stat-icon ${c.tint}`}>
                <c.icon size={21} />
              </span>
            </div>
            <div className="stat-value">{c.value}</div>
            <div className="stat-bottom">
              <span className="stat-change">{c.change}</span>
            </div>
          </div>
        ))}
      </section>
      <section className="dashboard-grid">
        <div className="panel revenue-panel">
          <div className="panel-heading">
            <div>
              <h2>Rental activity</h2>
              <p>Summary of delivery bills recorded in the rental module.</p>
            </div>
          </div>
          <div className="empty-state">
            <ClipboardList size={30} />
            <strong>No rental activity yet</strong>
            <span>
              Create a delivery bill to start tracking issues, returns and rental periods.
            </span>
            <button className="btn btn-secondary" onClick={() => onNavigate('Rentals')}>
              Rental module <ArrowRight size={16} />
            </button>
          </div>
        </div>
        <div className="panel inventory-panel">
          <div className="panel-heading">
            <div>
              <h2>Inventory snapshot</h2>
              <p>Current catalogue totals</p>
            </div>
            <button className="text-button" onClick={() => onNavigate('Inventory')}>
              View inventory <ArrowRight size={16} />
            </button>
          </div>
          <div className="inventory-total">
            <strong>{summary.total_stock.toLocaleString('en-IN')}</strong>
            <span>Total listed units</span>
          </div>
          <p className="page-subtitle">
            Physical availability is calculated from issues, returns and adjustments.
          </p>
          <button className="outline-full" onClick={() => onNavigate('Inventory')}>
            Manage inventory <ArrowRight size={17} />
          </button>
        </div>
      </section>
      <section className="dashboard-grid lower-grid">
        <div className="panel activity-panel">
          <div className="panel-heading">
            <div>
              <h2>Recent activity</h2>
              <p>Actual transactions only</p>
            </div>
          </div>
          <div className="empty-state">
            <FileText size={28} />
            <strong>No activity recorded</strong>
            <span>Customer and inventory changes will be reflected as modules are connected.</span>
          </div>
        </div>
        <div className="panel quick-panel">
          <div className="panel-heading">
            <div>
              <h2>Quick actions</h2>
              <p>Jump to a module</p>
            </div>
          </div>
          <QuickAction
            icon={Users}
            tint="violet"
            title="Manage customers"
            subtitle="Add, edit, search or import records"
            onClick={() => onNavigate('Customers')}
          />
          <QuickAction
            icon={Boxes}
            tint="blue"
            title="Manage inventory"
            subtitle="Edit stock and rental rates"
            onClick={() => onNavigate('Inventory')}
          />
          <QuickAction
            icon={Truck}
            tint="amber"
            title="Rental transactions"
            subtitle="Create delivery bills and record returns"
            onClick={() => onNavigate('Rentals')}
          />
          <QuickAction
            icon={FileText}
            tint="green"
            title="Customer ledgers"
            subtitle="View statements and export PDF or Excel"
            onClick={() => onNavigate('Billing & Ledgers')}
          />
        </div>
      </section>
    </>
  );
}
function QuickAction({
  icon: Icon,
  tint,
  title,
  subtitle,
  onClick,
}: {
  icon: any;
  tint: string;
  title: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button className="quick-action" onClick={onClick}>
      <div className={`quick-icon ${tint}`}>
        <Icon size={20} />
      </div>
      <div>
        <strong>{title}</strong>
        <span>{subtitle}</span>
      </div>
      <ArrowRight size={17} className="quick-arrow" />
    </button>
  );
}
