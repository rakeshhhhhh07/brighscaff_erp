import { useCallback, useEffect, useMemo, useState } from 'react';
import Sidebar from './components/layout/Sidebar';
import Topbar from './components/layout/Topbar';
import Modal from './components/ui/Modal';
import DashboardPage from './pages/DashboardPage';
import CustomersPage from './pages/CustomersPage';
import CustomerHistoryPage from './pages/CustomerHistoryPage';
import InventoryPage from './pages/InventoryPage';
import RentalsPage from './pages/RentalsPage';
import LedgersPage from './pages/LedgersPage';
import LoginPage from './pages/LoginPage';
import ReportsPage from './pages/ReportsPage';
import SettingsPage from './pages/SettingsPage';
import { apiGet, apiPost, apiPut, apiDelete } from './api';
import {
  clearSession,
  isSignedIn,
  SESSION_EVENT,
  storedUser,
  type AuthUser,
} from './services/auth';
import type { Customer, CustomerBalance, Item, NavKey, Summary } from './types';

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(() => (isSignedIn() ? storedUser() : null));
  // Customer whose history is open; null shows the normal customer list.
  const [historyCustomer, setHistoryCustomer] = useState<Customer | null>(null);
  const [balances, setBalances] = useState<Record<number, CustomerBalance>>({});
  const [active, setActive] = useState<NavKey>(() => {
    const k = decodeURIComponent(window.location.hash.replace(/^#\//, '')) as NavKey;
    return (
      [
        'Dashboard',
        'Customers',
        'Inventory',
        'Rentals',
        'Billing & Ledgers',
        'Reports',
        'Settings',
      ] as string[]
    ).includes(k)
      ? k
      : 'Dashboard';
  });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [summary, setSummary] = useState<Summary>({
    customers: 0,
    active_customers: 0,
    catalogue_items: 0,
    total_stock: 0,
    active_rentals: 0,
    items_on_rent: 0,
    rent_accrued: 0,
    outstanding_amount: 0,
  });
  const [showCustomerModal, setShowCustomerModal] = useState(false);
  const [showItemModal, setShowItemModal] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [editingItem, setEditingItem] = useState<Item | null>(null);
  const [apiConnected, setApiConnected] = useState(false);
  const [dashboardError, setDashboardError] = useState('');
  useEffect(() => {
    const onHash = () => {
      const k = decodeURIComponent(window.location.hash.replace(/^#\//, '')) as NavKey;
      if (
        (
          [
            'Dashboard',
            'Customers',
            'Inventory',
            'Rentals',
            'Billing & Ledgers',
            'Reports',
            'Settings',
          ] as string[]
        ).includes(k)
      )
        setActive(k);
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  // api.ts clears the session on any 401, so mirror that into React state and
  // drop straight back to the login screen rather than showing empty tables.
  useEffect(() => {
    const onSessionChange = () => setUser(isSignedIn() ? storedUser() : null);
    window.addEventListener(SESSION_EVENT, onSessionChange);
    return () => window.removeEventListener(SESSION_EVENT, onSessionChange);
  }, []);

  const loadWorkspace = useCallback(() => {
    apiGet<Summary>('/dashboard/summary')
      .then((s) => {
        setSummary(s);
        setApiConnected(true);
        setDashboardError('');
      })
      .catch((e) => {
        setDashboardError(e instanceof Error ? e.message : 'Dashboard API unavailable');
      });
    (async () => {
      try {
        const first = await apiGet<{ items: Customer[]; pages: number }>(
          '/customers/?per_page=100&page=1',
        );
        let all = first.items || [];
        for (let page = 2; page <= (first.pages || 1); page++) {
          const next = await apiGet<{ items: Customer[] }>('/customers/?per_page=100&page=' + page);
          all = all.concat(next.items || []);
        }
        setCustomers(all);
        setApiConnected(true);
      } catch {}
    })();
    // Outstanding balances come from one aggregate call rather than per-customer
    // statement builds, which would be far too slow for a list screen.
    apiGet<{ items: CustomerBalance[] }>('/ledgers/balances')
      .then((r) => {
        const byId: Record<number, CustomerBalance> = {};
        for (const b of r.items || []) byId[b.customer_id] = b;
        setBalances(byId);
      })
      .catch(() => {});
    apiGet<{ items: Item[] }>('/items/')
      .then((r) => {
        if (r.items) setItems(r.items);
        setApiConnected(true);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (user) loadWorkspace();
  }, [user, loadWorkspace]);
  const filteredCustomers = useMemo(
    () =>
      customers.filter((c) =>
        `${c.customer_name} ${c.customer_code} ${c.phone || ''}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [customers, query],
  );
  const filteredItems = useMemo(
    () =>
      items.filter((i) =>
        `${i.item_name} ${i.item_code} ${i.category || ''}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [items, query],
  );
  async function saveCustomer(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const payload = {
      customer_code: String(f.get('customer_code')).trim(),
      customer_name: String(f.get('customer_name')).trim(),
      contact_person: String(f.get('contact_person') || '').trim() || null,
      phone: String(f.get('phone') || '').trim() || null,
      email: String(f.get('email') || '').trim() || null,
      opening_balance: Number(f.get('opening_balance') || 0),
      company: String(f.get('company') || '').trim() || null,
      main_mobile: String(f.get('main_mobile') || '').trim() || null,
      mobile_2: String(f.get('mobile_2') || '').trim() || null,
      mobile_3: String(f.get('mobile_3') || '').trim() || null,
      residential_address: String(f.get('residential_address') || '').trim() || null,
      office_address: String(f.get('office_address') || '').trim() || null,
      office_email: String(f.get('office_email') || '').trim() || null,
      gst_number: String(f.get('gst_number') || '').trim() || null,
      guarantor_relationship: String(f.get('guarantor_relationship') || '').trim() || null,
      guarantor_name: String(f.get('guarantor_name') || '').trim() || null,
      guarantor_contact: String(f.get('guarantor_contact') || '').trim() || null,
      guarantor_address: String(f.get('guarantor_address') || '').trim() || null,
    };
    try {
      const saved = editingCustomer?.id
        ? await apiPut<Customer>(`/customers/${editingCustomer.id}`, payload)
        : await apiPost<Customer>('/customers/', payload);
      setCustomers((p) =>
        editingCustomer ? p.map((c) => (c.id === saved.id ? saved : c)) : [...p, saved],
      );
      setShowCustomerModal(false);
      setEditingCustomer(null);
      apiGet<Summary>('/dashboard/summary')
        .then(setSummary)
        .catch(() => {});
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Could not save customer. Check API/database.');
    }
  }
  async function saveItem(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const payload = {
      item_code: String(f.get('item_code')).trim(),
      item_name: String(f.get('item_name')).trim(),
      category: String(f.get('category') || '').trim(),
      unit: String(f.get('unit') || 'Nos'),
      total_stock: Number(f.get('total_stock') || 0),
      // One daily rate only; the legacy "after 30 days" rate is kept identical.
      initial_daily_rate: Number(f.get('initial_daily_rate') || 0),
      post_30_day_daily_rate: Number(f.get('initial_daily_rate') || 0),
      has_monthly_minimum: String(f.get('category') || '').trim().toUpperCase() !== 'COLUMN BOX',
    };
    try {
      const saved = editingItem?.id
        ? await apiPut<Item>(`/items/${editingItem.id}`, payload)
        : await apiPost<Item>('/items/', payload);
      setItems((p) =>
        editingItem ? p.map((i) => (i.id === saved.id ? saved : i)) : [...p, saved],
      );
      setShowItemModal(false);
      setEditingItem(null);
      apiGet<Summary>('/dashboard/summary')
        .then(setSummary)
        .catch(() => {});
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Could not save item. Check API/database.');
    }
  }
  async function deleteCustomer(c: Customer) {
    if (
      !c.id ||
      !window.confirm(
        `Deactivate ${c.customer_name}? Historical bills and statements will be preserved.`,
      )
    )
      return;
    try {
      await apiDelete(`/customers/${c.id}`);
      setCustomers((p) => p.map((x) => (x.id === c.id ? { ...x, is_active: false } : x)));
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Could not deactivate customer');
    }
  }
  async function deleteItem(i: Item) {
    if (
      !i.id ||
      !window.confirm(
        `Deactivate ${i.item_name}? Historical stock and rental records will be preserved.`,
      )
    )
      return;
    try {
      await apiDelete(`/items/${i.id}`);
      setItems((p) => p.map((x) => (x.id === i.id ? { ...x, is_active: false } : x)));
    } catch (e) {
      alert(e instanceof Error ? e.message : 'Could not deactivate item');
    }
  }
  function navigate(key: NavKey) {
    setActive(key);
    window.location.hash = '/' + encodeURIComponent(key);
    setQuery('');
    // Leaving the Customers tab closes any open history view.
    setHistoryCustomer(null);
  }

  async function signOut() {
    // Best effort: the audit entry is useful but must not block signing out.
    try {
      await apiPost('/auth/logout', {});
    } catch {}
    clearSession();
    setCustomers([]);
    setItems([]);
    setBalances({});
    setHistoryCustomer(null);
  }

  // Everything below the login gate requires a session.
  if (!user) {
    return <LoginPage onSignedIn={() => setUser(storedUser())} />;
  }

  return (
    <div className="app-shell">
      <Sidebar
        active={active}
        open={sidebarOpen}
        onNavigate={navigate}
        onClose={() => setSidebarOpen(false)}
        user={user}
        onSignOut={signOut}
      />
      <main className="main-area">
        <Topbar active={active} connected={apiConnected} onMenu={() => setSidebarOpen(true)} />
        <div className="page-content">
          {active === 'Dashboard' && (
            <>
              {dashboardError && (
                <div className="inline-message error-message">
                  Live dashboard totals could not be loaded ({dashboardError}). Check that the Phase
                  2 database tables exist; run database/schema.sql in MySQL Workbench, then restart
                  Flask.
                  <button
                    onClick={() => {
                      setDashboardError('');
                      apiGet<Summary>('/dashboard/summary')
                        .then(setSummary)
                        .catch((e) =>
                          setDashboardError(
                            e instanceof Error ? e.message : 'Dashboard API unavailable',
                          ),
                        );
                    }}
                  >
                    Retry
                  </button>
                </div>
              )}
              <DashboardPage summary={summary} onNavigate={navigate} />
            </>
          )}
          {active === 'Customers' &&
            (historyCustomer ? (
              <CustomerHistoryPage
                customer={historyCustomer}
                onBack={() => setHistoryCustomer(null)}
              />
            ) : (
              <CustomersPage
                customers={filteredCustomers}
                query={query}
                setQuery={setQuery}
                onAdd={() => {
                  setEditingCustomer(null);
                  setShowCustomerModal(true);
                }}
                onEdit={(c) => {
                  setEditingCustomer(c);
                  setShowCustomerModal(true);
                }}
                onDelete={deleteCustomer}
                onImported={(list) => setCustomers((p) => [...p, ...list])}
                balances={balances}
                onViewHistory={setHistoryCustomer}
              />
            ))}
          {active === 'Inventory' && (
            <InventoryPage
              items={filteredItems}
              query={query}
              setQuery={setQuery}
              onAdd={() => {
                setEditingItem(null);
                setShowItemModal(true);
              }}
              onEdit={(i) => {
                setEditingItem(i);
                setShowItemModal(true);
              }}
              onDelete={deleteItem}
            />
          )}
          {active === 'Rentals' && <RentalsPage />}
          {active === 'Billing & Ledgers' && <LedgersPage />}
          {active === 'Reports' && <ReportsPage />}
          {active === 'Settings' && <SettingsPage currentUser={user} />}
        </div>
        <footer className="footer">
          <span>© 2026 BRIGHT SCAFF ERP</span>
          <span>Secure workspace foundation</span>
        </footer>
      </main>
      {showCustomerModal && (
        <Modal
          title={editingCustomer ? 'Edit customer' : 'Add customer'}
          subtitle="Create a customer profile for rental transactions."
          onClose={() => {
            setShowCustomerModal(false);
            setEditingCustomer(null);
          }}
        >
          <form className="form-grid" onSubmit={saveCustomer}>
            <label>
              Customer code
              <input
                name="customer_code"
                defaultValue={editingCustomer?.customer_code || ''}
                placeholder="e.g. CUST-1005"
                required
              />
            </label>
            <label>
              Customer / company name
              <input
                name="customer_name"
                defaultValue={editingCustomer?.customer_name || ''}
                placeholder="Enter customer name"
                required
              />
            </label>
            <label>
              Contact person
              <input
                name="contact_person"
                defaultValue={editingCustomer?.contact_person || ''}
                placeholder="Contact name"
              />
            </label>
            <label>
              Phone number
              <input
                name="phone"
                type="tel"
                defaultValue={editingCustomer?.phone || ''}
                placeholder="Phone number"
              />
            </label>
            <label>
              Email address
              <input
                name="email"
                type="email"
                defaultValue={editingCustomer?.email || ''}
                placeholder="name@company.com"
              />
            </label>
            <label>
              Company
              <input name="company" defaultValue={editingCustomer?.company || ''} />
            </label>
            <label>
              Main mobile
              <input name="main_mobile" defaultValue={editingCustomer?.main_mobile || ''} />
            </label>
            <label>
              Mobile 2<input name="mobile_2" defaultValue={editingCustomer?.mobile_2 || ''} />
            </label>
            <label>
              Mobile 3<input name="mobile_3" defaultValue={editingCustomer?.mobile_3 || ''} />
            </label>
            <label>
              Residential address
              <input
                name="residential_address"
                defaultValue={editingCustomer?.residential_address || ''}
              />
            </label>
            <label>
              Office address
              <input name="office_address" defaultValue={editingCustomer?.office_address || ''} />
            </label>
            <label>
              Office email
              <input
                name="office_email"
                type="email"
                defaultValue={editingCustomer?.office_email || ''}
              />
            </label>
            <label>
              GST number
              <input name="gst_number" defaultValue={editingCustomer?.gst_number || ''} />
            </label>
            <label>
              Guarantor relationship
              <input
                name="guarantor_relationship"
                defaultValue={editingCustomer?.guarantor_relationship || ''}
              />
            </label>
            <label>
              Guarantor name
              <input name="guarantor_name" defaultValue={editingCustomer?.guarantor_name || ''} />
            </label>
            <label>
              Guarantor contact
              <input
                name="guarantor_contact"
                defaultValue={editingCustomer?.guarantor_contact || ''}
              />
            </label>
            <label>
              Guarantor address
              <input
                name="guarantor_address"
                defaultValue={editingCustomer?.guarantor_address || ''}
              />
            </label>
            <label>
              Opening balance (₹)
              <input
                name="opening_balance"
                type="number"
                min="0"
                step="0.01"
                defaultValue={String(editingCustomer?.opening_balance || 0)}
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowCustomerModal(false)}
              >
                Cancel
              </button>
              <button className="btn btn-primary" type="submit">
                Save customer
              </button>
            </div>
          </form>
        </Modal>
      )}
      {showItemModal && (
        <Modal
          title={editingItem ? 'Edit inventory item' : 'Add inventory item'}
          subtitle="Add a product and configure its rental rates."
          onClose={() => {
            setShowItemModal(false);
            setEditingItem(null);
          }}
        >
          <form className="form-grid" onSubmit={saveItem}>
            <label>
              Item code
              <input
                name="item_code"
                defaultValue={editingItem?.item_code || ''}
                placeholder="e.g. PIPE-005"
                required
              />
            </label>
            <label>
              Item name
              <input
                name="item_name"
                defaultValue={editingItem?.item_name || ''}
                placeholder="Scaffolding pipe"
                required
              />
            </label>
            <label>
              Category
              <input
                name="category"
                list="inventory-category-options"
                defaultValue={editingItem?.category || ''}
                placeholder="Select or enter a category"
                autoComplete="off"
                required
              />
              <datalist id="inventory-category-options">
                {Array.from(
                  new Set([
                    'PIPE ITEMS',
                    'H FRAME ITEMS',
                    'SHUTTERING ITEMS',
                    'LEDGER ITEMS',
                    'VERTICAL ITEMS',
                    'COLUMN BOX',
                    'Scaffolding',
                    'Formwork',
                    'Accessories',
                    'Safety',
                    'Other',
                    ...items.map((item) => String(item.category || '').trim()),
                    editingItem?.category || '',
                  ].filter(Boolean)),
                )
                  .sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
                  .map((category) => (
                    <option key={category} value={category} />
                  ))}
              </datalist>
            </label>
            <label>
              Unit
              <input name="unit" defaultValue={editingItem?.unit || 'Nos'} required />
            </label>
            <label>
              Total stock
              <input
                name="total_stock"
                type="number"
                min="0"
                defaultValue={String(editingItem?.total_stock || 0)}
                required
              />
            </label>
            <label>
              Daily rent (₹/unit/day) — monthly rent = daily × 30
              <input
                name="initial_daily_rate"
                type="number"
                min="0"
                step="0.01"
                defaultValue={String(editingItem?.initial_daily_rate || 0)}
                required
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setShowItemModal(false)}
              >
                Cancel
              </button>
              <button className="btn btn-primary" type="submit">
                Save item
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
