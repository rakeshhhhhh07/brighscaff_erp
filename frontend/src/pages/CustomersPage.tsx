import { ChangeEvent, useRef, useState } from 'react';
import {
  Download,
  FileSpreadsheet,
  History,
  Pencil,
  Plus,
  Search,
  Users,
  Trash2,
} from 'lucide-react';
import * as XLSX from 'xlsx';
import type { Customer, CustomerBalance } from '../types';
import { money } from '../services/formatters';
import { apiPost } from '../api';

type Props = {
  customers: Customer[];
  query: string;
  setQuery: (q: string) => void;
  onAdd: () => void;
  onEdit: (c: Customer) => void;
  onDelete: (c: Customer) => void;
  onImported: (c: Customer[]) => void;
  /** Live outstanding balance per customer id, loaded by App. */
  balances: Record<number, CustomerBalance>;
  onViewHistory: (c: Customer) => void;
};

type DetailRow = [string, string | undefined];

const normalize = (v: unknown) => String(v ?? '').trim();

export default function CustomersPage({
  customers,
  query,
  setQuery,
  onAdd,
  onEdit,
  onDelete,
  onImported,
  balances,
  onViewHistory,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);
  const [notice, setNotice] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<number[]>([]);
  const [viewCustomer, setViewCustomer] = useState<Customer | null>(null);

  const visibleCustomers = customers.filter(
    (c) =>
      !statusFilter || (statusFilter === 'ACTIVE' ? c.is_active !== false : c.is_active === false),
  );

  async function importFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setNotice('');
    setImporting(true);
    try {
      const data = await file.arrayBuffer();
      const wb = XLSX.read(data);
      const ws = wb.Sheets[wb.SheetNames[0]];
      const rows = XLSX.utils.sheet_to_json<Record<string, unknown>>(ws, { defval: '' });

      const keys = (r: Record<string, unknown>) =>
        Object.fromEntries(
          Object.entries(r).map(([k, v]) => [k.toLowerCase().replace(/[^a-z0-9]/g, ''), v]),
        );

      const prepared = rows
        .map((r) => {
          const x = keys(r);
          return {
            customer_code: normalize(x.customercode ?? x.customerid ?? x.code ?? x.accountcode),
            customer_name: normalize(x.customername ?? x.companyname ?? x.name ?? x.ledgername),
            contact_person: normalize(x.contactperson ?? x.contact ?? x.contactname),
            phone: normalize(x.phone ?? x.mobile ?? x.telephone),
            email: normalize(x.email),
            billing_address: normalize(x.billingaddress ?? x.address),
            site_address: normalize(x.siteaddress),
            tax_number: normalize(x.taxnumber ?? x.gst ?? x.gstin),
            opening_balance: Number(x.openingbalance ?? 0) || 0,
          };
        })
        .filter((r) => r.customer_code && r.customer_name);

      if (!prepared.length) {
        throw new Error(
          'No usable customer rows found. Use columns such as Customer Code, Customer Name, Contact Person, Phone, Email, Address and Opening Balance. Ledger statements are not customer-master files.',
        );
      }

      const result = await apiPost<{ created: Customer[]; skipped: number }>('/customers/import', {
        customers: prepared,
      });
      onImported(result.created || []);
      setNotice(
        `Import complete: ${result.created?.length || 0} added, ${result.skipped || 0} skipped (duplicate customer codes).`,
      );
    } catch (err) {
      setNotice(
        err instanceof Error ? err.message : 'Import failed. Check the Excel file and API.',
      );
    } finally {
      setImporting(false);
      e.target.value = '';
    }
  }

  function exportCsv() {
    const rows = [
      [
        'Customer Code',
        'Customer Name',
        'Contact Person',
        'Phone',
        'Email',
        'Opening Balance',
        'Status',
      ],
      ...customers.map((c) => [
        c.customer_code,
        c.customer_name,
        c.contact_person || '',
        c.phone || '',
        c.email || '',
        c.opening_balance || 0,
        c.is_active === false ? 'Inactive' : 'Active',
      ]),
    ];
    const csv = rows
      .map((r) => r.map((v) => '"' + String(v ?? '').replace(/"/g, '""') + '"').join(','))
      .join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    a.download = 'bright-scaff-customers.csv';
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // Loosely typed view of the customer so the detail panel compiles
  // even if some optional fields are not yet declared on the Customer type.
  const d = (viewCustomer || {}) as unknown as Record<string, string | undefined>;

  const personalRows: DetailRow[] = [
    ['Customer name', d.customer_name],
    ['Company', d.company],
    ['Site', d.site_address],
    ['Main mobile', d.main_mobile || d.phone],
    ['Mobile 2', d.mobile_2],
    ['Mobile 3', d.mobile_3],
    ['Email ID', d.email],
    ['Residential address', d.residential_address],
  ];

  const officeRows: DetailRow[] = [
    ['Office address', d.office_address || d.billing_address],
    ['Office email', d.office_email],
    ['GST number', d.gst_number || d.tax_number],
  ];

  const guarantorRows: DetailRow[] = [
    ['Relationship', d.guarantor_relationship],
    ['Name', d.guarantor_name],
    ['Contact number', d.guarantor_contact],
    ['Address', d.guarantor_address],
  ];

  const renderFields = (rows: DetailRow[]) =>
    rows.map(([k, v]) => (
      <div className="customer-detail-field" key={k}>
        <small>{k}</small>
        <span>{v || '—'}</span>
      </div>
    ));

  return (
    <>
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">CUSTOMER DIRECTORY</div>
          <h1>Customers</h1>
          <p className="page-subtitle">
            Manage customer profiles, contact information and rental relationships.
          </p>
        </div>
        <button className="btn btn-primary" onClick={onAdd}>
          <Plus size={19} />
          Add customer
        </button>
      </div>

      <div className="panel table-panel">
        <div className="table-toolbar">
          <label className="search-box">
            <Search size={19} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search by name, customer code or phone…"
            />
          </label>
          <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" hidden onChange={importFile} />
          <button
            className="btn btn-secondary"
            disabled={importing}
            onClick={() => fileRef.current?.click()}
          >
            <Download size={18} />
            {importing ? 'Importing…' : 'Import Excel / Tally'}
          </button>
          <select
            aria-label="Filter customer status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>
          <button className="btn btn-secondary" onClick={exportCsv}>
            <FileSpreadsheet size={18} />
            Export CSV
          </button>
        </div>

        {notice && (
          <div className="import-notice" role="status">
            {notice}
          </div>
        )}

        <div className="table-responsive">
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    aria-label="Select all visible customers"
                    type="checkbox"
                    checked={
                      visibleCustomers.length > 0 &&
                      visibleCustomers.every((x) => selected.includes(Number(x.id)))
                    }
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? visibleCustomers.map((x) => Number(x.id)).filter(Boolean)
                          : [],
                      )
                    }
                  />
                </th>
                <th>Customer</th>
                <th>Customer ID</th>
                <th>Contact person</th>
                <th>Phone</th>
                <th>Status</th>
                <th>Opening balance</th>
                <th>Balance due</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleCustomers.map((c, i) => (
                <tr key={c.id || c.customer_code}>
                  <td>
                    <input
                      aria-label={`Select ${c.customer_name}`}
                      type="checkbox"
                      checked={selected.includes(Number(c.id))}
                      onChange={(e) =>
                        setSelected((p) =>
                          e.target.checked
                            ? [...p, Number(c.id)]
                            : p.filter((id) => id !== Number(c.id)),
                        )
                      }
                    />
                  </td>
                  <td>
                    <div className="table-customer">
                      <div className={`customer-avatar avatar-${i % 4}`}>
                        {c.customer_name
                          .split(' ')
                          .map((w) => w[0])
                          .slice(0, 2)
                          .join('')
                          .toUpperCase()}
                      </div>
                      <div>
                        <strong>
                          <button
                            type="button"
                            className="customer-name-link"
                            onClick={() => setViewCustomer(c)}
                          >
                            {c.customer_name}
                          </button>
                        </strong>
                        <span>{c.email || 'Customer account'}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className="code-pill">{c.customer_code}</span>
                  </td>
                  <td>{c.contact_person || '—'}</td>
                  <td>{c.phone || '—'}</td>
                  <td>
                    <span className={`status-pill ${c.is_active === false ? 'inactive' : ''}`}>
                      <i />
                      {c.is_active === false ? 'Inactive' : 'Active'}
                    </span>
                  </td>
                  <td className="amount-cell">{money(Number(c.opening_balance || 0))}</td>
                  <td className="amount-cell">
                    {/* Balances load separately from the customer list, so show a
                        placeholder until the aggregate request comes back. */}
                    {balances[Number(c.id)] ? (
                      <span
                        className={
                          balances[Number(c.id)].balance > 0 ? 'balance-due' : 'balance-clear'
                        }
                      >
                        {money(balances[Number(c.id)].balance)}
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`View history for ${c.customer_name}`}
                      title="View rentals, payments and balance"
                      onClick={() => onViewHistory(c)}
                    >
                      <History size={16} />
                    </button>
                    <button
                      className="icon-button"
                      aria-label={`Edit ${c.customer_name}`}
                      onClick={() => onEdit(c)}
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      className="icon-button danger-icon"
                      aria-label={`Deactivate ${c.customer_name}`}
                      title="Deactivate customer (history is preserved)"
                      onClick={() => onDelete(c)}
                      disabled={c.is_active === false}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {visibleCustomers.length === 0 && (
            <div className="empty-state">
              <Users size={30} />
              <strong>No customer records yet</strong>
              <span>Add a customer or import a clean customer-master Excel/Tally export.</span>
            </div>
          )}
        </div>

        <div className="table-footer">
          <span>
            Showing <strong>{visibleCustomers.length}</strong> customers in this view
          </span>
          <span>Only records saved in your database are shown.</span>
        </div>
      </div>

      {viewCustomer && (
        <div
          className="customer-detail-overlay"
          role="presentation"
          onClick={() => setViewCustomer(null)}
        >
          <section
            className="panel customer-detail-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Customer details"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="page-heading-row">
              <div>
                <div className="eyebrow">CUSTOMER ACCOUNT</div>
                <h1>{viewCustomer.customer_name}</h1>
                <p className="page-subtitle">
                  {viewCustomer.is_active === false ? 'Inactive customer' : 'Individual customer'}
                </p>
              </div>
              <div className="export-actions">
                <button
                  className="btn btn-secondary"
                  onClick={() => {
                    onEdit(viewCustomer);
                    setViewCustomer(null);
                  }}
                >
                  Edit customer
                </button>
                <button className="btn btn-secondary" onClick={() => setViewCustomer(null)}>
                  Close
                </button>
              </div>
            </div>

            <div className="customer-detail-grid">
              <section>
                <h3>Personal details</h3>
                {renderFields(personalRows)}
              </section>
              <section>
                <h3>Office details</h3>
                {renderFields(officeRows)}
              </section>
              <section>
                <h3>Guarantor or introducer</h3>
                {renderFields(guarantorRows)}
              </section>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
