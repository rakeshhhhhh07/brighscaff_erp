import { useEffect, useMemo, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  RefreshCw,
  Search,
  Pencil,
  Trash2,
  Truck,
} from 'lucide-react';
import { apiGet, apiPost, apiPut, apiDelete } from '../api';
import Modal from '../components/ui/Modal';
import Combobox from '../components/ui/Combobox';
import type { Customer, Item } from '../types';
import { money } from '../services/formatters';
type RentalLine = {
  rental_order_item_id: number;
  item_id: number;
  item_code: string;
  item_name: string;
  unit: string;
  quantity_issued: number;
  quantity_returned_good: number;
  quantity_damaged: number;
  quantity_missing: number;
  quantity_outstanding: number;
  initial_daily_rate: number;
  post_30_day_daily_rate: number;
  is_daily_rental?: boolean;
};
type Rental = {
  id: number;
  rental_number: string;
  customer_name: string;
  customer_code: string;
  issue_date: string;
  status: string;
  notes?: string | null;
  site_name?: string | null;
  line_count: number;
  total_issued: number;
  items?: RentalLine[];
};
type Stock = {
  id: number;
  item_code: string;
  item_name: string;
  unit: string;
  total_stock: number;
  on_rent: number;
  available_stock: number;
};
type ReturnHistory = {
  return_id: number;
  return_number: string;
  return_date: string;
  submitted_at?: string | null;
  return_notes?: string | null;
  return_item_id: number | null;
  rental_order_item_id: number | null;
  quantity_returned: number | null;
  item_condition: string | null;
  notes?: string | null;
  item_name?: string | null;
  item_code?: string | null;
  adj_vehicle_rent_amount?: number | null;
  adj_vehicle_type?: string | null;
  adj_vehicle_number?: string | null;
  adj_discount_type?: DiscountType | null;
  adj_discount_value?: number | null;
  unit?: string | null;
};
type DiscountType = 'PERCENT' | 'FIXED';
/** Short label such as "10%" or "₹500.00 fixed" for a saved discount. */
const discountLabel = (type: DiscountType | null | undefined, value: number) =>
  type === 'PERCENT' ? `${value}%` : `${money(value)} fixed`;
const validDiscount = (type: DiscountType, value: string) =>
  Number(value) > 0 && (type !== 'PERCENT' || Number(value) <= 100);
type IssueLine = { category: string; item_id: string; quantity: string; daily: boolean };
const emptyLine = (): IssueLine => ({ category: '', item_id: '', quantity: '1', daily: false });
/** Column box items are normally hired by the day, so their daily-rental box starts ticked. */
const isColumnBox = (category: string) => category.trim().toUpperCase() === 'COLUMN BOX';
const today = () => new Date().toISOString().slice(0, 10);
/** Items may have no category set; group those under a single stable bucket. */
const categoryOf = (item: Item) => item.category || 'Other';
/** Radio (percentage / fixed amount) plus the value input, shared by both discount modals. */
function DiscountFields(props: {
  type: DiscountType;
  value: string;
  onType: (t: DiscountType) => void;
  onValue: (v: string) => void;
}) {
  const percent = props.type === 'PERCENT';
  return (
    <>
      <div className="radio-row" role="radiogroup" aria-label="Discount type">
        <label>
          <input
            type="radio"
            name="discount-type"
            checked={percent}
            onChange={() => props.onType('PERCENT')}
          />
          <span>Percentage (%)</span>
        </label>
        <label>
          <input
            type="radio"
            name="discount-type"
            checked={!percent}
            onChange={() => props.onType('FIXED')}
          />
          <span>Fixed amount (Rs.)</span>
        </label>
      </div>
      <label>
        {percent ? 'Discount percentage' : 'Discount amount (Rs.)'}
        <input
          type="number"
          min="0"
          max={percent ? 100 : undefined}
          step="0.01"
          value={props.value}
          onChange={(e) => props.onValue(e.target.value)}
          placeholder={percent ? 'e.g. 10' : 'e.g. 500.00'}
        />
      </label>
    </>
  );
}
export default function RentalsPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [rentals, setRentals] = useState<Rental[]>([]);
  const [stock, setStock] = useState<Stock[]>([]);
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [mode, setMode] = useState<'delivery' | 'return'>('delivery');
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] = useState<Rental | null>(null);
  const [message, setMessage] = useState('');
  const [customerId, setCustomerId] = useState('');
  const [issueDate, setIssueDate] = useState(today());
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<IssueLine[]>([emptyLine()]);
  const [returnDate, setReturnDate] = useState(today());
  const [applyGst, setApplyGst] = useState(false);
  const [advanceAtDelivery, setAdvanceAtDelivery] = useState(false);
  const [advancePaid, setAdvancePaid] = useState('');
  const [advanceMethod, setAdvanceMethod] = useState('CASH');
  const [vehicleAtDelivery, setVehicleAtDelivery] = useState(false);
  const [vehicleAmount, setVehicleAmount] = useState('');
  const [vehicleType, setVehicleType] = useState('');
  const [vehicleNumber, setVehicleNumber] = useState('');
  const [vehicleMethod, setVehicleMethod] = useState('CASH');
  const [vehiclePaidStatus, setVehiclePaidStatus] = useState('UNPAID');
  const [returnPayment, setReturnPayment] = useState('');
  const [returnPaymentMethod, setReturnPaymentMethod] = useState('CASH');
  const [vehicleAtReturn, setVehicleAtReturn] = useState(false);
  const [returnVehicleAmount, setReturnVehicleAmount] = useState('');
  const [returnVehicleType, setReturnVehicleType] = useState('');
  const [returnVehicleNumber, setReturnVehicleNumber] = useState('');
  const [vehicleModal, setVehicleModal] = useState<null | 'delivery' | 'return'>(null);
  const [siteName, setSiteName] = useState('');
  const [discountAllowed, setDiscountAllowed] = useState(false);
  const [discountModal, setDiscountModal] = useState(false);
  const [discountType, setDiscountType] = useState<DiscountType>('PERCENT');
  const [discountValue, setDiscountValue] = useState('');
  // Vehicle rent + discount added to one return bill from the return history.
  const [adjustRow, setAdjustRow] = useState<ReturnHistory | null>(null);
  const [adjVehicleType, setAdjVehicleType] = useState('');
  const [adjVehicleNumber, setAdjVehicleNumber] = useState('');
  const [adjVehicleAmount, setAdjVehicleAmount] = useState('');
  const [adjDiscountType, setAdjDiscountType] = useState<DiscountType>('PERCENT');
  const [adjDiscountValue, setAdjDiscountValue] = useState('');
  const [returnHistory, setReturnHistory] = useState<ReturnHistory[]>([]);
  const [returnLines, setReturnLines] = useState<
    Record<number, { quantity: string; condition: string }>
  >({});
  async function load() {
    setBusy(true);
    setMessage('');
    // Load master data independently. A missing Phase 2 table must not prevent
    // existing customers and inventory from appearing in the delivery form.
    const [cResult, iResult, rResult, sResult] = await Promise.allSettled([
      (async () => {
        const first = await apiGet<{ items: Customer[]; pages?: number }>(
          '/customers/?per_page=100&page=1',
        );
        let all = first.items || [];
        for (let page = 2; page <= (first.pages || 1); page++) {
          const next = await apiGet<{ items: Customer[] }>('/customers/?per_page=100&page=' + page);
          all = all.concat(next.items || []);
        }
        return { items: all };
      })(),
      apiGet<{ items: Item[] }>('/items/'),
      apiGet<{ items: Rental[] }>('/rentals/'),
      apiGet<{ items: Stock[] }>('/rentals/stock'),
    ]);
    const errors: string[] = [];
    if (cResult.status === 'fulfilled') setCustomers(cResult.value.items || []);
    else
      errors.push(
        `Customers: ${cResult.reason instanceof Error ? cResult.reason.message : 'request failed'}`,
      );
    if (iResult.status === 'fulfilled') setItems(iResult.value.items || []);
    else
      errors.push(
        `Inventory: ${iResult.reason instanceof Error ? iResult.reason.message : 'request failed'}`,
      );
    if (rResult.status === 'fulfilled') setRentals(rResult.value.items || []);
    else
      errors.push(
        `Delivery bills: ${rResult.reason instanceof Error ? rResult.reason.message : 'request failed'}`,
      );
    if (sResult.status === 'fulfilled') setStock(sResult.value.items || []);
    else
      errors.push(
        `Stock: ${sResult.reason instanceof Error ? sResult.reason.message : 'request failed'}`,
      );
    if (errors.length)
      setMessage(
        `Some rental data could not load. ${errors.join(' | ')}. Confirm the Phase 2 database tables are installed by running database/schema.sql in MySQL Workbench, then restart Flask and refresh.`,
      );
    setBusy(false);
  }
  useEffect(() => {
    load();
  }, []);
  async function openReturn(r: Rental) {
    try {
      const d = await apiGet<Rental>(`/rentals/${r.id}`);
      const h = await apiGet<{ items: ReturnHistory[] }>(`/rentals/${r.id}/returns`);
      setReturnHistory(h.items || []);
      setDetail(d);
      setSelected(r.id);
      setMode('return');
      const initial: Record<number, { quantity: string; condition: string }> = {};
      (d.items || []).forEach((it) => {
        initial[it.rental_order_item_id] = {
          quantity: String(it.quantity_outstanding),
          condition: 'GOOD',
        };
      });
      setReturnLines(initial);
      setMessage('');
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not load delivery details');
    }
  }
  async function submitDelivery(e: React.FormEvent) {
    e.preventDefault();
    setMessage('');
    const clean = lines
      .filter((x) => x.item_id && Number(x.quantity) > 0)
      .map((x) => ({
        item_id: Number(x.item_id),
        quantity: Number(x.quantity),
        is_daily_rental: x.daily,
      }));
    if (!clean.length) {
      setMessage('Add at least one item with a quantity.');
      return;
    }
    if (discountAllowed && !validDiscount(discountType, discountValue)) {
      setMessage('Enter a valid discount value, or untick "Is Discount Allowed?".');
      return;
    }
    setBusy(true);
    try {
      await apiPost('/rentals/', {
        customer_id: Number(customerId),
        issue_date: issueDate,
        site_name: siteName.trim() || null,
        discount_allowed: discountAllowed,
        discount_type: discountAllowed ? discountType : null,
        discount_value: discountAllowed ? Number(discountValue) : 0,
        notes,
        items: clean,
        apply_gst: applyGst,
        gst_rate: 18,
        advance_paid: advanceAtDelivery ? Number(advancePaid || 0) : 0,
        advance_payment_method: advanceAtDelivery ? advanceMethod : null,
        vehicle_rent_amount: vehicleAtDelivery ? Number(vehicleAmount || 0) : 0,
        vehicle_rent_stage: vehicleAtDelivery ? 'DELIVERY' : null,
        vehicle_type: vehicleAtDelivery ? vehicleType : null,
        vehicle_number: vehicleAtDelivery ? vehicleNumber : null,
        vehicle_paid_status: vehicleAtDelivery ? vehiclePaidStatus : 'UNPAID',
        vehicle_payment_method: vehicleMethod,
      });
      setMessage('Delivery bill saved successfully.');
      setCustomerId('');
      setNotes('');
      setLines([emptyLine()]);
      setApplyGst(false);
      setSiteName('');
      setDiscountAllowed(false);
      setDiscountType('PERCENT');
      setDiscountValue('');
      setAdvanceAtDelivery(false);
      setAdvancePaid('');
      setAdvanceMethod('CASH');
      setVehicleAtDelivery(false);
      setVehicleAmount('');
      setVehicleType('');
      setVehicleNumber('');
      setVehicleMethod('CASH');
      setVehiclePaidStatus('UNPAID');
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not save delivery');
    } finally {
      setBusy(false);
    }
  }
  async function editDelivery(r: Rental) {
    const newDate = window.prompt('Delivery / issue date (YYYY-MM-DD)', r.issue_date);
    if (newDate === null) return;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(newDate)) {
      setMessage('Date must be in YYYY-MM-DD format.');
      return;
    }
    const newNotes = window.prompt('Delivery notes', r.notes || '');
    if (newNotes === null) return;
    const newSite = window.prompt('Site name (optional)', r.site_name || '');
    if (newSite === null) return;
    setBusy(true);
    try {
      await apiPut(`/rentals/${r.id}`, {
        issue_date: newDate,
        notes: newNotes,
        site_name: newSite.trim(),
      });
      setMessage('Delivery bill updated.');
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not edit delivery bill');
    } finally {
      setBusy(false);
    }
  }
  async function cancelDelivery(r: Rental) {
    if (
      !window.confirm(
        `Cancel delivery bill ${r.rental_number}? This retains the record for audit. Bills with return history cannot be cancelled.`,
      )
    )
      return;
    setBusy(true);
    try {
      await apiDelete(`/rentals/${r.id}`);
      setMessage('Delivery bill cancelled; audit record retained.');
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not cancel delivery bill');
    } finally {
      setBusy(false);
    }
  }
  async function correctReturnLine(row: ReturnHistory) {
    if (!row.return_item_id || !detail) return;
    const qty = window.prompt('Correct quantity returned', String(row.quantity_returned));
    if (qty === null) return;
    const condition = window.prompt(
      'Condition: GOOD, DAMAGED, or MISSING',
      row.item_condition || 'GOOD',
    );
    if (condition === null) return;
    const dt = window.prompt('Return date (YYYY-MM-DD)', row.return_date);
    if (dt === null) return;
    const notesValue = window.prompt('Return line notes', row.notes || '');
    if (notesValue === null) return;
    const reason = window.prompt('Reason for correction (required for audit history)');
    if (!reason?.trim()) {
      setMessage('Correction cancelled: an audit reason is required.');
      return;
    }
    setBusy(true);
    try {
      await apiPut(`/rentals/return-items/${row.return_item_id}`, {
        quantity_returned: Number(qty),
        item_condition: condition.toUpperCase(),
        return_date: dt,
        notes: notesValue,
        reason,
      });
      const h = await apiGet<{ items: ReturnHistory[] }>(`/rentals/${detail.id}/returns`);
      setReturnHistory(h.items || []);
      const d = await apiGet<Rental>(`/rentals/${detail.id}`);
      setDetail(d);
      setMessage('Return line corrected. Previous values are retained in the audit history.');
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not correct return line');
    } finally {
      setBusy(false);
    }
  }
  async function viewReturnAudit(row: ReturnHistory) {
    try {
      const result = await apiGet<{
        items: Array<{
          action_type: string;
          old_return_number: string;
          old_return_date: string;
          old_quantity_returned: number;
          old_item_condition: string;
          old_notes?: string;
          reason: string;
          changed_at: string;
        }>;
      }>(`/rentals/returns/${row.return_id}/audit`);
      const entries = result.items || [];
      window.alert(
        entries.length
          ? entries
              .map(
                (a) =>
                  `${a.changed_at} — ${a.action_type}\nPrevious bill: ${a.old_return_number}; date: ${a.old_return_date}; qty: ${a.old_quantity_returned}; condition: ${a.old_item_condition}\nReason: ${a.reason}`,
              )
              .join('\n\n')
          : 'No corrections recorded for this return line.',
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not load audit history');
    }
  }
  async function deleteReturnLine(row: ReturnHistory) {
    if (!row.return_item_id || !detail) return;
    const reason = window.prompt(
      `Reason for deleting ${row.item_name || 'this return line'} (required for audit history)`,
    );
    if (!reason?.trim()) return;
    if (
      !window.confirm(
        'Delete this return line? The original values will remain in audit history and stock/status will be recalculated.',
      )
    )
      return;
    setBusy(true);
    try {
      await apiDelete(`/rentals/return-items/${row.return_item_id}`, { reason });
      const h = await apiGet<{ items: ReturnHistory[] }>(`/rentals/${detail.id}/returns`);
      setReturnHistory(h.items || []);
      const d = await apiGet<Rental>(`/rentals/${detail.id}`);
      setDetail(d);
      setMessage('Return line deleted and preserved in audit history.');
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not delete return line');
    } finally {
      setBusy(false);
    }
  }
  function openAdjustments(row: ReturnHistory) {
    setAdjustRow(row);
    setAdjVehicleType(row.adj_vehicle_type || '');
    setAdjVehicleNumber(row.adj_vehicle_number || '');
    setAdjVehicleAmount(row.adj_vehicle_rent_amount ? String(row.adj_vehicle_rent_amount) : '');
    setAdjDiscountType(row.adj_discount_type || 'PERCENT');
    setAdjDiscountValue(row.adj_discount_value ? String(row.adj_discount_value) : '');
  }
  async function saveAdjustments() {
    if (!adjustRow || !detail) return;
    if (Number(adjVehicleAmount || 0) < 0) {
      setMessage('Vehicle rent cannot be negative.');
      return;
    }
    if (adjDiscountValue && !validDiscount(adjDiscountType, adjDiscountValue)) {
      setMessage('Enter a valid discount (percentage must be between 0 and 100).');
      return;
    }
    setBusy(true);
    try {
      await apiPut(`/rentals/returns/${adjustRow.return_id}/adjustments`, {
        vehicle_rent_amount: Number(adjVehicleAmount || 0),
        vehicle_type: adjVehicleType,
        vehicle_number: adjVehicleNumber,
        discount_type: adjDiscountValue ? adjDiscountType : null,
        discount_value: Number(adjDiscountValue || 0),
      });
      const h = await apiGet<{ items: ReturnHistory[] }>(`/rentals/${detail.id}/returns`);
      setReturnHistory(h.items || []);
      setAdjustRow(null);
      setMessage(
        `Vehicle rent / discount saved for ${adjustRow.return_number}. The statement now includes it.`,
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not save vehicle rent / discount');
    } finally {
      setBusy(false);
    }
  }
  async function recordPayment(r: Rental) {
    const amount = window.prompt(`Payment received against ${r.rental_number} (Rs.)`);
    if (amount === null) return;
    if (!Number.isFinite(Number(amount)) || Number(amount) <= 0) {
      setMessage('Enter a payment amount greater than zero.');
      return;
    }
    const paymentDate = window.prompt('Payment date (YYYY-MM-DD)', today());
    if (paymentDate === null) return;
    const method = window.prompt('Payment method (CASH / UPI / BANK TRANSFER / CHEQUE)', 'CASH');
    if (method === null) return;
    setBusy(true);
    try {
      await apiPost(`/rentals/${r.id}/payments`, {
        amount: Number(amount),
        payment_date: paymentDate,
        payment_method: method,
        reference_number: r.rental_number,
        notes: 'Additional bill-wise customer receipt',
      });
      setMessage(
        `Payment of Rs. ${Number(amount).toFixed(2)} recorded against ${r.rental_number}.`,
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not record payment');
    } finally {
      setBusy(false);
    }
  }
  async function submitReturn(e: React.FormEvent) {
    e.preventDefault();
    if (!detail) return;
    const clean = (detail.items || [])
      .map((it) => ({
        rental_order_item_id: it.rental_order_item_id,
        quantity: Number(returnLines[it.rental_order_item_id]?.quantity || 0),
        condition: returnLines[it.rental_order_item_id]?.condition || 'GOOD',
      }))
      .filter((x) => x.quantity > 0);
    if (!clean.length) {
      setMessage('Enter at least one return quantity.');
      return;
    }
    setBusy(true);
    try {
      await apiPost(`/rentals/${detail.id}/returns`, {
        return_date: returnDate,
        items: clean,
        payment_amount: Number(returnPayment || 0),
        payment_method: returnPaymentMethod,
        vehicle_rent_amount: vehicleAtReturn ? Number(returnVehicleAmount || 0) : 0,
        vehicle_type: vehicleAtReturn ? returnVehicleType : null,
        vehicle_number: vehicleAtReturn ? returnVehicleNumber : null,
      });
      setMessage('Return bill saved successfully.');
      setDetail(null);
      setReturnHistory([]);
      setSelected(null);
      setMode('delivery');
      setReturnPayment('');
      setVehicleAtReturn(false);
      setReturnVehicleAmount('');
      setReturnVehicleType('');
      setReturnVehicleNumber('');
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : 'Could not save return');
    } finally {
      setBusy(false);
    }
  }
  const activeItems = useMemo(() => items.filter((i) => i.is_active !== false), [items]);
  const categoryOptions = useMemo(
    () =>
      Array.from(new Set(activeItems.map(categoryOf)))
        .sort((a, b) => a.localeCompare(b))
        .map((name) => {
          const count = activeItems.filter((i) => categoryOf(i) === name).length;
          return { value: name, label: name, hint: `${count} item${count === 1 ? '' : 's'}` };
        }),
    [activeItems],
  );
  /** Items for one line, narrowed to the category chosen on that line. */
  function itemOptionsFor(category: string) {
    if (!category) return [];
    return activeItems
      .filter((i) => categoryOf(i) === category)
      .map((i) => {
        const available = stock.find((x) => x.id === i.id)?.available_stock ?? i.total_stock;
        return {
          value: String(i.id),
          label: `${i.item_code} — ${i.item_name}`,
          hint: `Available ${available} ${i.unit}`,
          keywords: `${i.item_name} ${i.item_code}`,
        };
      });
  }
  /** Category for a stock row, resolved from the catalogue (the stock API has no category). */
  const categoryOfStock = useMemo(() => {
    const byId = new Map(items.map((i) => [i.id, categoryOf(i)]));
    return (s: Stock) => byId.get(s.id) || 'Other';
  }, [items]);
  /**
   * Stock rows grouped by category. By default every item is listed; once the user
   * picks a category (or a specific item) on a delivery line the panel narrows to
   * just those rows so the numbers being relied on stay in view.
   */
  const stockGroups = useMemo(() => {
    const pickedItems = new Set(
      mode === 'delivery' ? lines.filter((l) => l.item_id).map((l) => Number(l.item_id)) : [],
    );
    const pickedCategories = new Set(
      mode === 'delivery'
        ? lines.filter((l) => l.category && !l.item_id).map((l) => l.category)
        : [],
    );
    const active = pickedItems.size > 0 || pickedCategories.size > 0;
    const rows = active
      ? stock.filter((s) => pickedItems.has(s.id) || pickedCategories.has(categoryOfStock(s)))
      : stock;
    const groups = new Map<string, Stock[]>();
    for (const s of rows) {
      const key = categoryOfStock(s);
      const bucket = groups.get(key);
      if (bucket) bucket.push(s);
      else groups.set(key, [s]);
    }
    return {
      filtered: active,
      count: rows.length,
      groups: Array.from(groups.entries())
        .sort((a, b) => a[0].localeCompare(b[0]))
        .map(([category, entries]) => ({
          category,
          entries: entries.slice().sort((a, b) => a.item_name.localeCompare(b.item_name)),
        })),
    };
  }, [stock, items, lines, mode, categoryOfStock]);
  const filtered = useMemo(
    () =>
      rentals.filter(
        (r) =>
          `${r.rental_number} ${r.customer_name} ${r.customer_code}`
            .toLowerCase()
            .includes(query.toLowerCase()) &&
          (!statusFilter || r.status === statusFilter),
      ),
    [rentals, query, statusFilter],
  );
  return (
    <>
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">DELIVERY CHALLANS & RETURNS</div>
          <h1>Rental transactions</h1>
          <p className="page-subtitle">
            Issue multiple item types and record partial or full returns against each delivery.
          </p>
        </div>
        <button className="btn btn-secondary" onClick={load}>
          <RefreshCw size={17} />
          Refresh
        </button>
      </div>
      {message && (
        <div className="inline-message" role="status">
          {message}
          <button onClick={() => setMessage('')}>Dismiss</button>
        </div>
      )}
      <div className="mini-stats">
        <div className="mini-stat">
          <span>Open deliveries</span>
          <strong>
            {rentals.filter((r) => r.status !== 'CLOSED' && r.status !== 'CANCELLED').length}
          </strong>
        </div>
        <div className="mini-stat">
          <span>Items currently on rent</span>
          <strong>{stock.reduce((n, s) => n + s.on_rent, 0).toLocaleString('en-IN')}</strong>
        </div>
        <div className="mini-stat">
          <span>Available stock</span>
          <strong>
            {stock.reduce((n, s) => n + s.available_stock, 0).toLocaleString('en-IN')}
          </strong>
        </div>
      </div>
      <div className="transaction-layout">
        <section className="panel transaction-form">
          <div className="segmented">
            <button
              className={mode === 'delivery' ? 'selected' : ''}
              onClick={() => {
                setMode('delivery');
                setDetail(null);
              }}
            >
              <ArrowUpFromLine size={17} /> New delivery
            </button>
            <button
              className={mode === 'return' ? 'selected' : ''}
              onClick={() => {
                setMode('return');
                setDetail(null);
              }}
            >
              <ArrowDownToLine size={17} /> Record return
            </button>
          </div>
          {mode === 'delivery' ? (
            <form className="stack-form" onSubmit={submitDelivery}>
              <h2>Create delivery bill</h2>
              <label>
                Customer
                <Combobox
                  required
                  value={customerId}
                  onChange={setCustomerId}
                  placeholder="Search or select customer"
                  emptyMessage="No matching customer"
                  options={customers
                    .filter((c) => c.is_active !== false)
                    .map((c) => ({
                      value: String(c.id),
                      label: `${c.customer_code} — ${c.customer_name}`,
                      hint: c.phone || undefined,
                      keywords: `${c.customer_name} ${c.customer_code} ${c.phone || ''}`,
                    }))}
                />
              </label>
              <label>
                Issue date
                <input
                  type="date"
                  required
                  value={issueDate}
                  onChange={(e) => setIssueDate(e.target.value)}
                />
              </label>
              <label>
                Site name (optional)
                <input
                  value={siteName}
                  maxLength={180}
                  onChange={(e) => setSiteName(e.target.value)}
                  placeholder="e.g. Tower B – Kakkanad"
                />
              </label>
              <div className="section-divider">
                <strong>Items to issue</strong>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => setLines((p) => [...p, emptyLine()])}
                >
                  + Add item line
                </button>
              </div>
              {lines.map((line, index) => (
                <div className="item-line" key={index}>
                  <label>
                    Category
                    <Combobox
                      required
                      value={line.category}
                      // Changing category invalidates the item chosen under the old one,
                      // and COLUMN BOX turns "Take as daily rental" on by default.
                      onChange={(v) =>
                        setLines((p) =>
                          p.map((x, i) =>
                            i === index
                              ? { ...x, category: v, item_id: '', daily: isColumnBox(v) }
                              : x,
                          ),
                        )
                      }
                      options={categoryOptions}
                      placeholder="Search or select category"
                      emptyMessage="No categories available"
                    />
                  </label>
                  <label>
                    Item
                    <Combobox
                      required
                      disabled={!line.category}
                      value={line.item_id}
                      onChange={(v) =>
                        setLines((p) => p.map((x, i) => (i === index ? { ...x, item_id: v } : x)))
                      }
                      options={itemOptionsFor(line.category)}
                      placeholder={
                        line.category ? 'Search or select item' : 'Select a category first'
                      }
                      emptyMessage="No items in this category"
                    />
                  </label>
                  <label>
                    Qty
                    <input
                      type="number"
                      min="1"
                      required
                      value={line.quantity}
                      onChange={(e) =>
                        setLines((p) =>
                          p.map((x, i) => (i === index ? { ...x, quantity: e.target.value } : x)),
                        )
                      }
                    />
                  </label>
                  <label className="daily-check">
                    <input
                      type="checkbox"
                      checked={line.daily}
                      onChange={(e) =>
                        setLines((p) =>
                          p.map((x, i) => (i === index ? { ...x, daily: e.target.checked } : x)),
                        )
                      }
                    />
                    <span>Take as daily rental (no 30-day minimum)</span>
                  </label>
                  {lines.length > 1 && (
                    <button
                      type="button"
                      className="remove-line"
                      onClick={() => setLines((p) => p.filter((_, i) => i !== index))}
                      aria-label="Remove line"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
              <div className="optional-financial-fields">
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={applyGst}
                    onChange={(e) => setApplyGst(e.target.checked)}
                  />
                  <span>Apply 18% GST to rental charges (including extra-day charges)</span>
                </label>
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={discountAllowed}
                    onChange={(e) => {
                      const on = e.target.checked;
                      setDiscountAllowed(on);
                      if (on) {
                        setDiscountModal(true);
                      } else {
                        setDiscountType('PERCENT');
                        setDiscountValue('');
                      }
                    }}
                  />
                  <span>Is Discount Allowed?</span>
                </label>
                {discountAllowed && (
                  <div className="detail-summary">
                    <span>
                      Discount:{' '}
                      <strong>
                        {discountValue
                          ? discountLabel(discountType, Number(discountValue))
                          : 'not entered'}
                      </strong>{' '}
                      (deducted from rental charges before GST)
                    </span>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => setDiscountModal(true)}
                    >
                      Edit discount
                    </button>
                  </div>
                )}
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={vehicleAtDelivery}
                    onChange={(e) => {
                      const on = e.target.checked;
                      setVehicleAtDelivery(on);
                      if (on) {
                        setVehicleModal('delivery');
                      } else {
                        setVehicleType('');
                        setVehicleNumber('');
                        setVehicleAmount('');
                        setVehiclePaidStatus('UNPAID');
                        setVehicleMethod('CASH');
                      }
                    }}
                  />
                  <span>Add vehicle rent at delivery</span>
                </label>
                {vehicleAtDelivery && (
                  <div className="detail-summary">
                    <span>
                      {vehicleType || vehicleNumber
                        ? `${vehicleType || 'Vehicle'}${vehicleNumber ? ` · ${vehicleNumber}` : ''}`
                        : 'Vehicle details not entered'}{' '}
                      · <strong>{money(Number(vehicleAmount || 0))}</strong> · {vehiclePaidStatus}
                    </span>
                    <button
                      type="button"
                      className="text-button"
                      onClick={() => setVehicleModal('delivery')}
                    >
                      Edit vehicle details
                    </button>
                  </div>
                )}
                <label className="check-row">
                  <input
                    type="checkbox"
                    checked={advanceAtDelivery}
                    onChange={(e) => {
                      const on = e.target.checked;
                      setAdvanceAtDelivery(on);
                      if (!on) {
                        setAdvancePaid('');
                        setAdvanceMethod('CASH');
                      }
                    }}
                  />
                  <span>Advance received at delivery</span>
                </label>
                {advanceAtDelivery && (
                  <div className="inline-fields">
                    <label>
                      Advance amount (Rs.)
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={advancePaid}
                        onChange={(e) => setAdvancePaid(e.target.value)}
                        placeholder="0.00"
                      />
                    </label>
                    <label>
                      Payment method
                      <select
                        value={advanceMethod}
                        onChange={(e) => setAdvanceMethod(e.target.value)}
                      >
                        <option>CASH</option>
                        <option>UPI</option>
                        <option>BANK TRANSFER</option>
                        <option>CHEQUE</option>
                      </select>
                    </label>
                  </div>
                )}
              </div>
              <label>
                Notes (optional)
                <textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
              </label>
              <div className="info-note">
                Each delivery line captures the current daily rate. Rental days start from the day
                after delivery. Lines marked as daily rental are charged only for the days used; all
                other lines follow the 30-day minimum rule.
              </div>
              <button
                className="btn btn-primary"
                type="submit"
                disabled={busy || !customers.length || !items.length}
              >
                {busy ? 'Saving…' : 'Save delivery bill'}
              </button>
            </form>
          ) : (
            <form className="stack-form" onSubmit={submitReturn}>
              <h2>Record item return</h2>
              {!detail ? (
                <>
                  <label>
                    Find open delivery
                    <label className="search-box">
                      <Search size={17} />
                      <input
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        placeholder="Search bill or customer"
                      />
                    </label>
                  </label>
                  <div className="delivery-pick-list">
                    {filtered
                      .filter((r) => r.status !== 'CLOSED' && r.status !== 'CANCELLED')
                      .map((r) => (
                        <button type="button" key={r.id} onClick={() => openReturn(r)}>
                          <span>
                            <strong>{r.rental_number}</strong>
                            <small>
                              {r.customer_name} · {r.issue_date}
                            </small>
                          </span>
                          <span className="status-pill">{r.status.replace('_', ' ')}</span>
                        </button>
                      ))}
                    {!filtered.some((r) => r.status !== 'CLOSED' && r.status !== 'CANCELLED') && (
                      <p className="muted">No open deliveries found.</p>
                    )}
                  </div>
                </>
              ) : (
                <>
                  <div className="selected-delivery">
                    <strong>{detail.rental_number}</strong>
                    <span>
                      {detail.customer_name} · issued {detail.issue_date}
                    </span>
                    <button type="button" className="text-button" onClick={() => setDetail(null)}>
                      Change delivery
                    </button>
                  </div>
                  <label>
                    Return date
                    <input
                      type="date"
                      required
                      min={detail.issue_date}
                      value={returnDate}
                      onChange={(e) => setReturnDate(e.target.value)}
                    />
                  </label>
                  {(detail.items || []).map((it) => (
                    <div className="return-line" key={it.rental_order_item_id}>
                      <div>
                        <strong>{it.item_name}</strong>
                        <small>
                          {it.item_code} · outstanding {it.quantity_outstanding} {it.unit}
                          {it.is_daily_rental ? ' · daily rental' : ''}
                        </small>
                      </div>
                      <label>
                        Qty
                        <input
                          type="number"
                          min="0"
                          max={it.quantity_outstanding}
                          value={returnLines[it.rental_order_item_id]?.quantity || '0'}
                          onChange={(e) =>
                            setReturnLines((p) => ({
                              ...p,
                              [it.rental_order_item_id]: {
                                ...p[it.rental_order_item_id],
                                quantity: e.target.value,
                              },
                            }))
                          }
                        />
                      </label>
                      <label>
                        Condition
                        <select
                          value={returnLines[it.rental_order_item_id]?.condition || 'GOOD'}
                          onChange={(e) =>
                            setReturnLines((p) => ({
                              ...p,
                              [it.rental_order_item_id]: {
                                ...p[it.rental_order_item_id],
                                condition: e.target.value,
                              },
                            }))
                          }
                        >
                          <option value="GOOD">Good</option>
                          <option value="DAMAGED">Damaged</option>
                          <option value="MISSING">Missing</option>
                        </select>
                      </label>
                    </div>
                  ))}
                  <div className="optional-financial-fields">
                    <label className="check-row">
                      <input
                        type="checkbox"
                        checked={vehicleAtReturn}
                        onChange={(e) => {
                          const on = e.target.checked;
                          setVehicleAtReturn(on);
                          if (on) {
                            setVehicleModal('return');
                          } else {
                            setReturnVehicleType('');
                            setReturnVehicleNumber('');
                            setReturnVehicleAmount('');
                          }
                        }}
                      />
                      <span>Add vehicle rent at return</span>
                    </label>
                    {vehicleAtReturn && (
                      <div className="detail-summary">
                        <span>
                          {returnVehicleType || returnVehicleNumber
                            ? `${returnVehicleType || 'Vehicle'}${returnVehicleNumber ? ` · ${returnVehicleNumber}` : ''}`
                            : 'Vehicle details not entered'}{' '}
                          · <strong>{money(Number(returnVehicleAmount || 0))}</strong>
                        </span>
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => setVehicleModal('return')}
                        >
                          Edit vehicle details
                        </button>
                      </div>
                    )}
                    <label>
                      Payment received now (optional, Rs.)
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={returnPayment}
                        onChange={(e) => setReturnPayment(e.target.value)}
                        placeholder="0.00"
                      />
                    </label>
                    <label>
                      Payment method
                      <select
                        value={returnPaymentMethod}
                        onChange={(e) => setReturnPaymentMethod(e.target.value)}
                      >
                        <option>CASH</option>
                        <option>UPI</option>
                        <option>BANK TRANSFER</option>
                        <option>CHEQUE</option>
                      </select>
                    </label>
                  </div>
                  <div className="info-note">
                    Good items return to available stock. Damaged and missing items are recorded
                    separately and are not counted as available stock.
                  </div>
                  <button className="btn btn-primary" disabled={busy} type="submit">
                    {busy ? 'Saving…' : 'Save return bill'}
                  </button>
                </>
              )}
            </form>
          )}
        </section>
        {/* Shell keeps the stock panel locked to the height of the bill form beside it. */}
        <div className="stock-panel-shell">
          <section className="panel stock-panel">
            <div className="panel-heading">
              <div>
                <h2>Physical stock & availability</h2>
                <p>
                  {stockGroups.filtered
                    ? 'Narrowed to the categories and items selected on this bill.'
                    : 'Calculated from catalogue stock and recorded rental movements.'}
                </p>
              </div>
              {stockGroups.filtered && (
                <span className="stock-filter-badge">
                  {stockGroups.count} of {stock.length}
                </span>
              )}
            </div>
            <div className="table-responsive stock-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Total</th>
                    <th>On rent</th>
                    <th>Available</th>
                  </tr>
                </thead>
                {stockGroups.groups.map((group) => (
                  <tbody key={group.category}>
                    <tr className="stock-group-row">
                      <th colSpan={4} scope="colgroup">
                        <div className="stock-group-label">
                          {group.category}
                          <span>
                            {group.entries.length} item{group.entries.length === 1 ? '' : 's'}
                          </span>
                        </div>
                      </th>
                    </tr>
                    {group.entries.map((s) => (
                      <tr key={s.id}>
                        <td>
                          <strong>{s.item_name}</strong>
                          <div className="muted">{s.item_code}</div>
                        </td>
                        <td>{s.total_stock}</td>
                        <td>{s.on_rent}</td>
                        <td>
                          <strong>{s.available_stock}</strong>{' '}
                          <span className="muted">{s.unit}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                ))}
              </table>
              {!stockGroups.count && (
                <div className="empty-state">
                  {stock.length
                    ? 'No stock rows match the selected category or item.'
                    : 'No inventory items available.'}
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
      {detail && mode === 'return' && (
        <section className="panel table-panel">
          <div className="panel-heading">
            <div>
              <h2>Return history — {detail.rental_number}</h2>
              <p>
                Edit or delete individual return lines. A reason is required and previous values are
                retained in audit history.
              </p>
            </div>
          </div>
          <div className="table-responsive">
            <table>
              <thead>
                <tr>
                  <th>Actual return date</th>
                  <th>Bill submitted at</th>
                  <th>Return bill</th>
                  <th>Item</th>
                  <th>Qty</th>
                  <th>Condition</th>
                  <th>Notes</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {returnHistory.map((r, idx) => (
                  <tr key={r.return_item_id ?? `void-${r.return_id}-${idx}`}>
                    <td>{String(r.return_date || '').slice(0, 10) || '—'}</td>
                    <td>{String(r.submitted_at || '').slice(0, 10) || '—'}</td>
                    <td>
                      {r.return_number}
                      {!r.return_item_id && <div className="muted">No active lines / voided</div>}
                      {Number(r.adj_vehicle_rent_amount) > 0 && (
                        <div className="muted">
                          Vehicle rent {money(Number(r.adj_vehicle_rent_amount))}
                        </div>
                      )}
                      {Number(r.adj_discount_value) > 0 && (
                        <div className="muted">
                          Discount{' '}
                          {discountLabel(r.adj_discount_type, Number(r.adj_discount_value))}
                        </div>
                      )}
                    </td>
                    <td>{r.item_name || '—'}</td>
                    <td>{r.quantity_returned ?? '—'}</td>
                    <td>{r.item_condition || '—'}</td>
                    <td>{r.notes || r.return_notes || ''}</td>
                    <td>
                      <div className="export-actions">
                        {r.return_item_id && (
                          <>
                            <button
                              className="btn btn-secondary"
                              type="button"
                              disabled={busy}
                              onClick={() => correctReturnLine(r)}
                            >
                              <Pencil size={15} />
                              Edit
                            </button>
                            <button
                              className="btn btn-secondary"
                              type="button"
                              disabled={busy}
                              onClick={() => deleteReturnLine(r)}
                            >
                              <Trash2 size={15} />
                              Delete
                            </button>
                          </>
                        )}
                        <button
                          className="btn btn-secondary"
                          type="button"
                          onClick={() => viewReturnAudit(r)}
                        >
                          Audit
                        </button>
                        {r.return_item_id && (
                          <button
                            className="btn btn-secondary"
                            type="button"
                            disabled={busy}
                            onClick={() => openAdjustments(r)}
                            title="Add vehicle rent and/or discount for this return bill"
                          >
                            <Truck size={15} />
                            Vehicle rent & discount
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!returnHistory.length && (
              <div className="empty-state">No return history recorded for this delivery.</div>
            )}
          </div>
        </section>
      )}
      <section className="panel table-panel rental-list-panel">
        <div className="panel-heading">
          <div>
            <h2>Delivery bills</h2>
            <p>Each delivery has independent item lines and return history.</p>
          </div>
        </div>
        <div className="table-toolbar">
          <label className="search-box">
            <Search size={18} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search bill number or customer"
            />
          </label>
          <select
            aria-label="Filter delivery status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="PARTIALLY_RETURNED">Partially returned</option>
            <option value="CLOSED">Closed</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
        <div className="table-responsive">
          <table>
            <thead>
              <tr>
                <th>Delivery bill</th>
                <th>Customer</th>
                <th>Issue date</th>
                <th>Item lines</th>
                <th>Qty issued</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((r) => (
                <tr key={r.id}>
                  <td>
                    <strong>{r.rental_number}</strong>
                  </td>
                  <td>
                    {r.customer_name}
                    <div className="muted">{r.customer_code}</div>
                    {r.site_name && <div className="muted">Site: {r.site_name}</div>}
                  </td>
                  <td>{r.issue_date}</td>
                  <td>{r.line_count}</td>
                  <td>{r.total_issued}</td>
                  <td>
                    <span className={`status-pill ${r.status === 'CLOSED' ? 'inactive' : ''}`}>
                      <i />
                      {r.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td>
                    <div className="export-actions">
                      <button
                        className="btn btn-secondary"
                        type="button"
                        disabled={r.status === 'CANCELLED'}
                        onClick={() => editDelivery(r)}
                        title="Edit delivery date and notes"
                      >
                        <Pencil size={15} />
                        Edit
                      </button>
                      <button
                        className="btn btn-secondary"
                        type="button"
                        disabled={r.status === 'CANCELLED'}
                        onClick={() => cancelDelivery(r)}
                        title="Cancel bill while preserving history"
                      >
                        <Trash2 size={15} />
                        Cancel
                      </button>
                      <button
                        className="btn btn-secondary"
                        type="button"
                        disabled={r.status === 'CANCELLED'}
                        onClick={() => openReturn(r)}
                      >
                        Returns / history
                      </button>
                      <button
                        className="btn btn-secondary"
                        type="button"
                        disabled={r.status === 'CANCELLED'}
                        onClick={() => recordPayment(r)}
                      >
                        Record payment
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filtered.length && (
            <div className="empty-state">
              No delivery bills yet. Create a delivery to start tracking rentals.
            </div>
          )}
        </div>
      </section>
      {discountModal && (
        <Modal
          title="Discount"
          subtitle="Choose how the discount is given. It is deducted from the rental charges (before GST) and shown on the statement."
          onClose={() => {
            // Closing without a valid value means no discount was actually set.
            if (!validDiscount(discountType, discountValue)) {
              setDiscountAllowed(false);
              setDiscountValue('');
            }
            setDiscountModal(false);
          }}
        >
          <div className="form-grid">
            <DiscountFields
              type={discountType}
              value={discountValue}
              onType={setDiscountType}
              onValue={setDiscountValue}
            />
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setDiscountAllowed(false);
                  setDiscountType('PERCENT');
                  setDiscountValue('');
                  setDiscountModal(false);
                }}
              >
                Remove discount
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={!validDiscount(discountType, discountValue)}
                onClick={() => setDiscountModal(false)}
              >
                Apply discount
              </button>
            </div>
          </div>
        </Modal>
      )}
      {adjustRow && (
        <Modal
          title={`Vehicle rent & discount — ${adjustRow.return_number}`}
          subtitle="Both are optional and are charged on this return's date in the customer statement. Leave a field empty to remove it."
          onClose={() => setAdjustRow(null)}
        >
          <div className="form-grid">
            <div className="section-divider">
              <strong>Vehicle rent</strong>
            </div>
            <label>
              Vehicle type
              <input
                value={adjVehicleType}
                onChange={(e) => setAdjVehicleType(e.target.value)}
                placeholder="Truck / Pickup"
              />
            </label>
            <label>
              Vehicle number
              <input
                value={adjVehicleNumber}
                onChange={(e) => setAdjVehicleNumber(e.target.value)}
                placeholder="e.g. TN 01 AB 1234"
              />
            </label>
            <label>
              Vehicle rent (Rs.)
              <input
                type="number"
                min="0"
                step="0.01"
                value={adjVehicleAmount}
                onChange={(e) => setAdjVehicleAmount(e.target.value)}
                placeholder="0.00"
              />
            </label>
            <div className="section-divider">
              <strong>Discount on this return's rental charges</strong>
            </div>
            <DiscountFields
              type={adjDiscountType}
              value={adjDiscountValue}
              onType={setAdjDiscountType}
              onValue={setAdjDiscountValue}
            />
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setAdjustRow(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                onClick={saveAdjustments}
              >
                {busy ? 'Saving…' : 'Save'}
              </button>
            </div>
          </div>
        </Modal>
      )}
      {vehicleModal === 'delivery' && (
        <Modal
          title="Vehicle details — delivery"
          subtitle="Capture transport details and vehicle rent charged on this delivery."
          onClose={() => setVehicleModal(null)}
        >
          <div className="form-grid">
            <label>
              Vehicle type
              <input
                value={vehicleType}
                onChange={(e) => setVehicleType(e.target.value)}
                placeholder="Truck / Pickup"
              />
            </label>
            <label>
              Vehicle number
              <input
                value={vehicleNumber}
                onChange={(e) => setVehicleNumber(e.target.value)}
                placeholder="e.g. TN 01 AB 1234"
              />
            </label>
            <label>
              Vehicle rent (Rs.)
              <input
                type="number"
                min="0"
                step="0.01"
                value={vehicleAmount}
                onChange={(e) => setVehicleAmount(e.target.value)}
                placeholder="0.00"
              />
            </label>
            <label>
              Paid status
              <select
                value={vehiclePaidStatus}
                onChange={(e) => setVehiclePaidStatus(e.target.value)}
              >
                <option value="UNPAID">Unpaid</option>
                <option value="PARTIAL">Partial</option>
                <option value="PAID">Paid</option>
              </select>
            </label>
            <label>
              Payment method
              <select value={vehicleMethod} onChange={(e) => setVehicleMethod(e.target.value)}>
                <option>CASH</option>
                <option>UPI</option>
                <option>BANK TRANSFER</option>
                <option>CHEQUE</option>
                <option>CREDIT</option>
              </select>
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setVehicleAtDelivery(false);
                  setVehicleType('');
                  setVehicleNumber('');
                  setVehicleAmount('');
                  setVehiclePaidStatus('UNPAID');
                  setVehicleMethod('CASH');
                  setVehicleModal(null);
                }}
              >
                Remove vehicle rent
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setVehicleModal(null)}
              >
                Done
              </button>
            </div>
          </div>
        </Modal>
      )}
      {vehicleModal === 'return' && (
        <Modal
          title="Vehicle details — return"
          subtitle="Capture transport details and vehicle rent charged on this return."
          onClose={() => setVehicleModal(null)}
        >
          <div className="form-grid">
            <label>
              Vehicle type
              <input
                value={returnVehicleType}
                onChange={(e) => setReturnVehicleType(e.target.value)}
                placeholder="Truck / Pickup"
              />
            </label>
            <label>
              Vehicle number
              <input
                value={returnVehicleNumber}
                onChange={(e) => setReturnVehicleNumber(e.target.value)}
                placeholder="e.g. TN 01 AB 1234"
              />
            </label>
            <label>
              Vehicle rent (Rs.)
              <input
                type="number"
                min="0"
                step="0.01"
                value={returnVehicleAmount}
                onChange={(e) => setReturnVehicleAmount(e.target.value)}
                placeholder="0.00"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setVehicleAtReturn(false);
                  setReturnVehicleType('');
                  setReturnVehicleNumber('');
                  setReturnVehicleAmount('');
                  setVehicleModal(null);
                }}
              >
                Remove vehicle rent
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => setVehicleModal(null)}
              >
                Done
              </button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
