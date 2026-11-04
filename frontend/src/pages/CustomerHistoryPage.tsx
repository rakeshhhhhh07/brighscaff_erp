import { useCallback, useEffect, useState } from 'react';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { apiGet } from '../api';
import { money } from '../services/formatters';
import type { Customer } from '../types';

type Delivery = {
  rental_number: string;
  issue_date: string;
  status: string;
  site_name: string;
  line_count: number;
  total_issued: number;
};

type Payment = {
  id: number;
  payment_date: string;
  amount: number;
  payment_method?: string | null;
  payment_type?: string | null;
  reference_number?: string | null;
  rental_number: string;
};

type ReturnRow = {
  return_date: string;
  return_number: string;
  rental_number: string;
  item_name: string;
  quantity_returned: number;
  item_condition: string;
};

type RunningItem = { item_name: string; unit: string; outstanding: number };

type History = {
  customer: { customer_name: string; customer_code: string; phone?: string | null };
  period_start: string | null;
  period_end: string;
  opening_balance: number;
  closing_balance: number;
  total_charged: number;
  total_received: number;
  deliveries: Delivery[];
  payments: Payment[];
  returns: ReturnRow[];
  running_items: RunningItem[];
};

type Props = {
  customer: Customer;
  onBack: () => void;
};

type Tab = 'deliveries' | 'returns' | 'payments' | 'running';

export default function CustomerHistoryPage({ customer, onBack }: Props) {
  const [data, setData] = useState<History | null>(null);
  const [tab, setTab] = useState<Tab>('deliveries');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!customer.id) return;
    setBusy(true);
    setError('');
    try {
      setData(await apiGet<History>(`/ledgers/customer/${customer.id}/history`));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load history');
    } finally {
      setBusy(false);
    }
  }, [customer.id]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <button className="btn btn-secondary" onClick={onBack}>
            <ArrowLeft size={16} /> Back to customers
          </button>
          <h2 style={{ marginTop: 12 }}>{customer.customer_name}</h2>
          <p className="muted">
            {customer.customer_code}
            {customer.phone ? ` · ${customer.phone}` : ''}
          </p>
        </div>
      </div>

      {error && <div className="banner error">{error}</div>}
      {busy && (
        <div className="banner">
          <Loader2 size={15} className="spin" /> Loading history…
        </div>
      )}

      {data && (
        <>
          <div className="summary-grid">
            <div className="summary-card">
              <span>Opening balance</span>
              <strong>{money(data.opening_balance)}</strong>
            </div>
            <div className="summary-card">
              <span>Total charged</span>
              <strong>{money(data.total_charged)}</strong>
            </div>
            <div className="summary-card">
              <span>Payments received</span>
              <strong>{money(data.total_received)}</strong>
            </div>
            <div className="summary-card accent">
              <span>Balance to collect</span>
              <strong>{money(data.closing_balance)}</strong>
            </div>
          </div>

          <div className="tab-row">
            {(
              [
                ['deliveries', `Deliveries (${data.deliveries.length})`],
                ['returns', `Returns (${data.returns.length})`],
                ['payments', `Payments (${data.payments.length})`],
                ['running', `Items with customer (${data.running_items.length})`],
              ] as [Tab, string][]
            ).map(([key, label]) => (
              <button
                key={key}
                className={`tab ${tab === key ? 'active' : ''}`}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="card">
            <div className="table-wrap">
              {tab === 'deliveries' && (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Bill no</th>
                      <th>Date</th>
                      <th>Site</th>
                      <th>Status</th>
                      <th className="num">Items</th>
                      <th className="num">Qty issued</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.deliveries.map((d) => (
                      <tr key={d.rental_number}>
                        <td>
                          <strong>{d.rental_number}</strong>
                        </td>
                        <td>{d.issue_date}</td>
                        <td>{d.site_name || '—'}</td>
                        <td>
                          <span className="pill subtle">{d.status.replace(/_/g, ' ')}</span>
                        </td>
                        <td className="num">{d.line_count}</td>
                        <td className="num">{d.total_issued}</td>
                      </tr>
                    ))}
                    {!data.deliveries.length && (
                      <tr>
                        <td colSpan={6} className="empty">
                          No deliveries recorded.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}

              {tab === 'returns' && (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Return no</th>
                      <th>Date</th>
                      <th>Against bill</th>
                      <th>Item</th>
                      <th className="num">Qty</th>
                      <th>Condition</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.returns.map((r, i) => (
                      <tr key={`${r.return_number}-${i}`}>
                        <td>
                          <strong>{r.return_number}</strong>
                        </td>
                        <td>{r.return_date}</td>
                        <td>{r.rental_number}</td>
                        <td>{r.item_name}</td>
                        <td className="num">{r.quantity_returned}</td>
                        <td>{r.item_condition}</td>
                      </tr>
                    ))}
                    {!data.returns.length && (
                      <tr>
                        <td colSpan={6} className="empty">
                          No returns recorded.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}

              {tab === 'payments' && (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Against bill</th>
                      <th>Type</th>
                      <th>Method</th>
                      <th>Reference</th>
                      <th className="num">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.payments.map((p) => (
                      <tr key={p.id}>
                        <td>{p.payment_date}</td>
                        <td>{p.rental_number}</td>
                        <td>{p.payment_type || '—'}</td>
                        <td>{p.payment_method || '—'}</td>
                        <td>{p.reference_number || '—'}</td>
                        <td className="num amount-cell">{money(p.amount)}</td>
                      </tr>
                    ))}
                    {!data.payments.length && (
                      <tr>
                        <td colSpan={6} className="empty">
                          No payments recorded.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}

              {tab === 'running' && (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Item</th>
                      <th>Unit</th>
                      <th className="num">Quantity still out</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.running_items.map((r) => (
                      <tr key={r.item_name}>
                        <td>{r.item_name}</td>
                        <td>{r.unit}</td>
                        <td className="num">{r.outstanding}</td>
                      </tr>
                    ))}
                    {!data.running_items.length && (
                      <tr>
                        <td colSpan={3} className="empty">
                          Everything has been returned.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </div>
          </div>
        </>
      )}
    </section>
  );
}
