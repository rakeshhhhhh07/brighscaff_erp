import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Boxes, IndianRupee, Loader2, TrendingUp } from 'lucide-react';
import { apiGet } from '../api';
import { money } from '../services/formatters';

type StockRow = {
  item_code: string;
  item_name: string;
  unit: string;
  total_stock: number;
  on_rent: number;
  available: number;
  oversubscribed: boolean;
};

type OverdueRow = {
  rental_number: string;
  customer_id: number;
  customer_name: string;
  phone?: string | null;
  site_name: string;
  issue_date: string;
  days_out: number;
  outstanding_qty: number;
};

type OutstandingRow = {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  balance: number;
  payments: number;
  open_orders: number;
  last_activity?: string | null;
};

type RevenueRow = { period: string; received: number; payment_count: number };

type Tab = 'stock' | 'overdue' | 'outstanding' | 'revenue';

const TABS: { key: Tab; label: string; icon: typeof Boxes }[] = [
  { key: 'stock', label: 'Stock availability', icon: Boxes },
  { key: 'overdue', label: 'Overdue rentals', icon: AlertTriangle },
  { key: 'outstanding', label: 'Outstanding balances', icon: IndianRupee },
  { key: 'revenue', label: 'Revenue', icon: TrendingUp },
];

export default function ReportsPage() {
  const [tab, setTab] = useState<Tab>('stock');
  const [overdueDays, setOverdueDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const [stock, setStock] = useState<StockRow[]>([]);
  const [overdue, setOverdue] = useState<OverdueRow[]>([]);
  const [outstanding, setOutstanding] = useState<OutstandingRow[]>([]);
  const [revenue, setRevenue] = useState<RevenueRow[]>([]);
  const [totals, setTotals] = useState<Record<string, number>>({});

  const load = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      if (tab === 'stock') {
        const r = await apiGet<{ items: StockRow[]; total_stock: number; total_on_rent: number }>(
          '/reports/stock-availability',
        );
        setStock(r.items || []);
        setTotals({ total_stock: r.total_stock, total_on_rent: r.total_on_rent });
      } else if (tab === 'overdue') {
        const r = await apiGet<{ items: OverdueRow[] }>(`/reports/overdue?days=${overdueDays}`);
        setOverdue(r.items || []);
      } else if (tab === 'outstanding') {
        const r = await apiGet<{
          items: OutstandingRow[];
          total_outstanding: number;
          customers_owing: number;
        }>('/reports/outstanding');
        setOutstanding(r.items || []);
        setTotals({
          total_outstanding: r.total_outstanding,
          customers_owing: r.customers_owing,
        });
      } else {
        const r = await apiGet<{ items: RevenueRow[]; total_received: number }>(
          '/reports/revenue?months=12',
        );
        setRevenue(r.items || []);
        setTotals({ total_received: r.total_received });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load report');
    } finally {
      setBusy(false);
    }
  }, [tab, overdueDays]);

  useEffect(() => {
    load();
  }, [load]);

  const peakRevenue = Math.max(1, ...revenue.map((r) => r.received));

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <div className="eyebrow">BUSINESS INTELLIGENCE</div>
          <h2>Reports &amp; insights</h2>
          <p className="muted">Stock utilisation, rental ageing, and customer activity.</p>
        </div>
      </div>

      <div className="tab-row">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            <t.icon size={16} />
            {t.label}
          </button>
        ))}
      </div>

      {error && <div className="banner error">{error}</div>}
      {busy && (
        <div className="banner">
          <Loader2 size={15} className="spin" /> Loading report…
        </div>
      )}

      {tab === 'stock' && (
        <div className="card">
          <div className="card-head">
            <h3>Stock availability</h3>
            <span className="muted">
              {totals.total_on_rent ?? 0} of {totals.total_stock ?? 0} units on rent
            </span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Unit</th>
                  <th className="num">Total stock</th>
                  <th className="num">On rent</th>
                  <th className="num">Available</th>
                </tr>
              </thead>
              <tbody>
                {stock.map((s) => (
                  <tr key={s.item_code}>
                    <td>
                      <strong>{s.item_name}</strong>
                      <div className="muted small">{s.item_code}</div>
                    </td>
                    <td>{s.unit}</td>
                    <td className="num">{s.total_stock}</td>
                    <td className="num">{s.on_rent}</td>
                    <td className="num">
                      <span className={s.oversubscribed ? 'pill danger' : ''}>{s.available}</span>
                    </td>
                  </tr>
                ))}
                {!stock.length && !busy && (
                  <tr>
                    <td colSpan={5} className="empty">
                      No items in the catalogue.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'overdue' && (
        <div className="card">
          <div className="card-head">
            <h3>Overdue rentals</h3>
            <label className="inline-field">
              <span>Open longer than</span>
              <input
                type="number"
                min={0}
                value={overdueDays}
                onChange={(e) => setOverdueDays(Math.max(0, Number(e.target.value)))}
              />
              <span>days</span>
            </label>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Bill no</th>
                  <th>Customer</th>
                  <th>Site</th>
                  <th>Issued</th>
                  <th className="num">Days out</th>
                  <th className="num">Qty pending</th>
                </tr>
              </thead>
              <tbody>
                {overdue.map((o) => (
                  <tr key={o.rental_number}>
                    <td>
                      <strong>{o.rental_number}</strong>
                    </td>
                    <td>
                      {o.customer_name}
                      <div className="muted small">{o.phone || ''}</div>
                    </td>
                    <td>{o.site_name || '—'}</td>
                    <td>{o.issue_date}</td>
                    <td className="num">
                      <span className={o.days_out > 90 ? 'pill danger' : 'pill warn'}>
                        {o.days_out}
                      </span>
                    </td>
                    <td className="num">{o.outstanding_qty}</td>
                  </tr>
                ))}
                {!overdue.length && !busy && (
                  <tr>
                    <td colSpan={6} className="empty">
                      Nothing overdue past {overdueDays} days.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'outstanding' && (
        <div className="card">
          <div className="card-head">
            <h3>Outstanding balances</h3>
            <span className="muted">
              {totals.customers_owing ?? 0} customers · {money(totals.total_outstanding ?? 0)} owing
            </span>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Code</th>
                  <th className="num">Received</th>
                  <th className="num">Balance due</th>
                  <th className="num">Open bills</th>
                  <th>Last activity</th>
                </tr>
              </thead>
              <tbody>
                {outstanding.map((o) => (
                  <tr key={o.customer_id}>
                    <td>
                      <strong>{o.customer_name}</strong>
                    </td>
                    <td>{o.customer_code}</td>
                    <td className="num">{money(o.payments)}</td>
                    <td className="num amount-cell">{money(o.balance)}</td>
                    <td className="num">{o.open_orders}</td>
                    <td>{o.last_activity || '—'}</td>
                  </tr>
                ))}
                {!outstanding.length && !busy && (
                  <tr>
                    <td colSpan={6} className="empty">
                      No customer owes anything.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'revenue' && (
        <div className="card">
          <div className="card-head">
            <h3>Revenue received</h3>
            <span className="muted">Last 12 months · {money(totals.total_received ?? 0)}</span>
          </div>
          <div className="report-bars">
            {revenue.map((r) => (
              <div className="report-bar-row" key={r.period}>
                <span className="report-bar-label">{r.period}</span>
                <div className="report-bar-track">
                  <div
                    className="report-bar-fill"
                    style={{ width: `${(r.received / peakRevenue) * 100}%` }}
                  />
                </div>
                <span className="report-bar-value">{money(r.received)}</span>
              </div>
            ))}
            {!revenue.length && !busy && <p className="empty">No payments recorded yet.</p>}
          </div>
        </div>
      )}
    </section>
  );
}
