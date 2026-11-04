import { useEffect, useState } from 'react';
import { Download, FileSpreadsheet, FileText, RefreshCw } from 'lucide-react';
import { apiDownload, apiGet } from '../api';
import type { Customer } from '../types';
import { money, displayDate } from '../services/formatters';
import Combobox from '../components/ui/Combobox';
type Entry = {
  transaction_date: string;
  reference_number?: string;
  transaction_type: string;
  particulars: string;
  debit: number;
  credit: number;
  running_balance: number;
};
type BillSummary = {
  rental_order_id: number;
  rental_number: string;
  site_name?: string;
  issue_date: string;
  rental_base: number;
  discount_amount: number;
  gst_amount: number;
  vehicle_rent_amount: number;
  total_bill_amount: number;
  amount_paid: number;
  balance_due: number;
};
type Ledger = {
  bill_summaries?: BillSummary[];
  customer: { id: number; customer_code: string; customer_name: string; phone?: string };
  opening_balance: number;
  entries: Entry[];
  closing_balance: number;
  note: string;
};
export default function LedgersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerId, setCustomerId] = useState('');
  // Both dates start empty so the statement covers all history until the user
  // deliberately narrows the period.
  const [start, setStart] = useState('');
  const [end, setEnd] = useState('');
  const [ledger, setLedger] = useState<Ledger | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    (async () => {
      try {
        const first = await apiGet<{ items: Customer[]; pages?: number }>(
          '/customers/?per_page=100&page=1',
        );
        let all = first.items || [];
        for (let page = 2; page <= (first.pages || 1); page++) {
          const next = await apiGet<{ items: Customer[] }>('/customers/?per_page=100&page=' + page);
          all = all.concat(next.items || []);
        }
        setCustomers(all);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load customers');
      }
    })();
  }, []);
  async function load() {
    if (!customerId) {
      setError('Select a customer first.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const qs = new URLSearchParams();
      if (start) qs.set('start', start);
      if (end) qs.set('end', end);
      const d = await apiGet<Ledger>(`/ledgers/customer/${customerId}?${qs.toString()}`);
      setLedger(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load statement');
    } finally {
      setBusy(false);
    }
  }
  async function download(kind: 'pdf' | 'excel') {
    if (!customerId) {
      setError('Select a customer first.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const qs = new URLSearchParams();
      if (start) qs.set('start', start);
      if (end) qs.set('end', end);
      // apiDownload sends the bearer token; a plain fetch would be rejected.
      const blob = await apiDownload(
        `/ledgers/customer/${customerId}/${kind}?${qs.toString()}`,
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const cust = customers.find((c) => String(c.id) === String(customerId));
      const safe =
        (cust?.customer_name || 'CUSTOMER')
          .toUpperCase()
          .replace(/[^A-Z0-9]+/g, '')
          .slice(0, 40) || 'CUSTOMER';
      const compact = (v: string) =>
        v ? v.slice(8, 10) + v.slice(5, 7) + v.slice(0, 4).slice(2) : 'ALL';
      a.download = `${safe}_${compact(start)}_${compact(end)}.${kind === 'excel' ? 'xlsx' : 'pdf'}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not export statement');
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">CUSTOMER STATEMENTS & RENTAL CHARGES</div>
          <h1>Billing & ledgers</h1>
          <p className="page-subtitle">
            Review item-level rental charges and export customer statements.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={load} disabled={busy}>
          <RefreshCw size={17} />
          Refresh statement
        </button>
      </div>
      {error && (
        <div className="inline-message error-message">
          {error}
          <button onClick={() => setError('')}>Dismiss</button>
        </div>
      )}
      <section className="panel ledger-filters">
        <div className="panel-heading">
          <div>
            <h2>Statement filters</h2>
            <p>Choose a customer and optional transaction period.</p>
          </div>
        </div>
        <div className="ledger-filter-grid">
          <label>
            Customer
            <Combobox
              value={customerId}
              onChange={(v) => {
                setCustomerId(v);
                setLedger(null);
              }}
              placeholder="Search or select customer"
              emptyMessage="No matching customer"
              options={customers.map((c) => ({
                value: String(c.id),
                label: `${c.customer_code} — ${c.customer_name}`,
                hint: c.phone || undefined,
                keywords: `${c.customer_name} ${c.customer_code} ${c.phone || ''}`,
              }))}
            />
          </label>
          <label>
            From date
            <input type="date" value={start} onChange={(e) => setStart(e.target.value)} />
          </label>
          <label>
            To date
            <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
          </label>
          <button className="btn btn-primary" disabled={busy || !customerId} onClick={load}>
            {busy ? 'Loading…' : 'Generate statement'}
          </button>
        </div>
      </section>
      {ledger && (
        <>
          <div className="ledger-summary-grid">
            <div className="mini-stat">
              <span>Customer</span>
              <strong>{ledger.customer.customer_name}</strong>
              <small>
                {ledger.customer.customer_code}
                {ledger.customer.phone ? ` · ${ledger.customer.phone}` : ''}
              </small>
            </div>
            <div className="mini-stat">
              <span>Opening balance</span>
              <strong>{money(ledger.opening_balance)}</strong>
            </div>
            <div className="mini-stat">
              <span>Closing balance</span>
              <strong>{money(ledger.closing_balance)}</strong>
            </div>
          </div>
          {(ledger.bill_summaries || []).length > 0 && (
            <section className="panel table-panel">
              <div className="panel-heading">
                <div>
                  <h2>Bill-wise payment summary</h2>
                  <p>
                    Discount is deducted from rental charges before GST. Vehicle rent (including
                    vehicle rent added at return) is shown separately.
                  </p>
                </div>
              </div>
              <div className="table-responsive">
                <table>
                  <thead>
                    <tr>
                      <th>Bill no.</th>
                      <th>Site</th>
                      <th>Date</th>
                      <th>Rental</th>
                      <th>Discount</th>
                      <th>GST</th>
                      <th>Vehicle rent</th>
                      <th>Bill total</th>
                      <th>Paid</th>
                      <th>Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(ledger.bill_summaries || []).map((b) => (
                      <tr key={b.rental_order_id}>
                        <td>{b.rental_number}</td>
                        <td>{b.site_name || '—'}</td>
                        <td>{displayDate(b.issue_date)}</td>
                        <td>{money(b.rental_base)}</td>
                        <td>{b.discount_amount ? `− ${money(b.discount_amount)}` : money(0)}</td>
                        <td>{money(b.gst_amount)}</td>
                        <td>{money(b.vehicle_rent_amount)}</td>
                        <td>
                          <strong>{money(b.total_bill_amount)}</strong>
                        </td>
                        <td>{money(b.amount_paid)}</td>
                        <td>
                          <strong>{money(b.balance_due)}</strong>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          <section className="panel table-panel">
            <div className="panel-heading">
              <div>
                <h2>Customer statement</h2>
                <p>{ledger.entries.length} ledger entries in the selected period.</p>
              </div>
              <div className="export-actions">
                <button
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => download('pdf')}
                >
                  <FileText size={17} />
                  PDF
                </button>
                <button
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => download('excel')}
                >
                  <FileSpreadsheet size={17} />
                  Excel
                </button>
              </div>
            </div>
            <div className="table-responsive">
              <table>
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Reference</th>
                    <th>Type</th>
                    <th>Particulars</th>
                    <th>Debit</th>
                    <th>Credit</th>
                    <th>Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {ledger.entries.map((e, i) => (
                    <tr key={`${e.reference_number || 'entry'}-${i}`}>
                      <td>{displayDate(e.transaction_date)}</td>
                      <td>{e.reference_number || '—'}</td>
                      <td>{e.transaction_type}</td>
                      <td>{e.particulars}</td>
                      <td>{money(e.debit)}</td>
                      <td>{money(e.credit)}</td>
                      <td>
                        <strong>{money(e.running_balance)}</strong>
                      </td>
                    </tr>
                  ))}
                  {!ledger.entries.length && (
                    <tr>
                      <td colSpan={7}>No transactions found for this customer and period.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="info-note ledger-note">
              <strong>Calculation note:</strong> {ledger.note} This statement is intended for
              validation and should not be treated as a final tax invoice until your company's
              billing rules are confirmed.
            </div>
          </section>
        </>
      )}
      {!ledger && (
        <div className="empty-state ledger-empty">
          <FileText size={32} />
          <strong>Generate a customer statement</strong>
          <span>Select a customer above to view the ledger and download PDF or Excel.</span>
          <Download size={18} />
        </div>
      )}
    </>
  );
}
