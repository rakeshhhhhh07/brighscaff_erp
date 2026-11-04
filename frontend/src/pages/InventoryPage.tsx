import { useState } from 'react';
import {
  Boxes,
  Download,
  FileSpreadsheet,
  Package,
  Pencil,
  Plus,
  Search,
  Trash2,
} from 'lucide-react';
import type { Item } from '../types';
import { money } from '../services/formatters';
type Props = {
  items: Item[];
  query: string;
  setQuery: (q: string) => void;
  onAdd: () => void;
  onEdit: (i: Item) => void;
  onDelete: (i: Item) => void;
};
export default function InventoryPage({ items, query, setQuery, onAdd, onEdit, onDelete }: Props) {
  const [statusFilter, setStatusFilter] = useState('');
  const [selected, setSelected] = useState<number[]>([]);
  const [categoryFilter, setCategoryFilter] = useState('');
  const categories = Array.from(new Set(items.map((i) => i.category || 'Other'))).sort();
  // Category-wise order (A-Z, uncategorised "Other" last), then item name within a category.
  const categoryRank = (i: Item) => ((i.category || 'Other') === 'Other' ? 1 : 0);
  const visibleItems = items
    .filter(
      (i) =>
        (!statusFilter ||
          (statusFilter === 'ACTIVE' ? i.is_active !== false : i.is_active === false)) &&
        (!categoryFilter || (i.category || 'Other') === categoryFilter),
    )
    .sort(
      (a, b) =>
        categoryRank(a) - categoryRank(b) ||
        (a.category || 'Other').localeCompare(b.category || 'Other', undefined, {
          sensitivity: 'base',
        }) ||
        a.item_name.localeCompare(b.item_name, undefined, { numeric: true, sensitivity: 'base' }),
    );
  return (
    <>
      <div className="page-heading-row">
        <div>
          <div className="eyebrow">STOCK & ITEM CATALOGUE</div>
          <h1>Inventory</h1>
          <p className="page-subtitle">
            Manage scaffolding products, stock quantities and rental rates.
          </p>
        </div>
        <button className="btn btn-primary" onClick={onAdd}>
          <Plus size={19} />
          Add item
        </button>
      </div>
      <div className="mini-stats">
        <div className="mini-stat">
          <span>Catalogue items</span>
          <strong>{items.length}</strong>
        </div>
        <div className="mini-stat">
          <span>Total listed stock</span>
          <strong>
            {items.reduce((a, i) => a + Number(i.total_stock), 0).toLocaleString('en-IN')}
          </strong>
        </div>
        <div className="mini-stat">
          <span>Rental model</span>
          <strong>30-day minimum + daily</strong>
        </div>
      </div>
      <div className="panel table-panel">
        <div className="table-toolbar">
          <label className="search-box">
            <Search size={19} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search item name, code or category…"
            />
          </label>
          <select
            aria-label="Filter inventory status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="">All statuses</option>
            <option value="ACTIVE">Active</option>
            <option value="INACTIVE">Inactive</option>
          </select>
          <select
            aria-label="Filter inventory category"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <button
            className="btn btn-secondary"
            onClick={() => alert('Inventory import will be implemented in the next phase.')}
          >
            <Download size={18} />
            Import Excel
          </button>
          <button
            className="btn btn-secondary"
            onClick={() => {
              const csv = [
                [
                  'Item Code',
                  'Item Name',
                  'Category',
                  'Unit',
                  'Total Stock',
                  'Monthly Rent (Daily x 30)',
                  'Rent Per Day',
                ],
                ...items.map((i) => [
                  i.item_code,
                  i.item_name,
                  i.category || '',
                  i.unit,
                  i.total_stock,
                  Number(i.initial_daily_rate) * 30,
                  i.initial_daily_rate,
                ]),
              ]
                .map((r) => r.map((v) => '"' + String(v ?? '').replace(/"/g, '""') + '"').join(','))
                .join('\r\n');
              const a = document.createElement('a');
              a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
              a.download = 'bright-scaff-inventory.csv';
              a.click();
              URL.revokeObjectURL(a.href);
            }}
          >
            <FileSpreadsheet size={18} />
            Export
          </button>
        </div>
        {selected.length > 0 && (
          <div className="table-toolbar">
            <strong>{selected.length} selected</strong>
            <button
              className="btn btn-secondary"
              onClick={() => {
                if (window.confirm(`Deactivate ${selected.length} selected inventory items?`)) {
                  visibleItems.filter((x) => selected.includes(Number(x.id))).forEach(onDelete);
                  setSelected([]);
                }
              }}
            >
              Deactivate selected
            </button>
          </div>
        )}
        <div className="table-responsive">
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    aria-label="Select all visible items"
                    type="checkbox"
                    checked={
                      visibleItems.length > 0 &&
                      visibleItems.every((x) => selected.includes(Number(x.id)))
                    }
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? visibleItems.map((x) => Number(x.id)).filter(Boolean)
                          : [],
                      )
                    }
                  />
                </th>
                <th>Item</th>
                <th>Item code</th>
                <th>Category</th>
                <th>Total stock</th>
                <th>Monthly rent (daily × 30)</th>
                <th>Rent per day</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.map((i, idx) => (
                <tr key={i.id || i.item_code}>
                  <td>
                    <input
                      aria-label={`Select ${i.item_name}`}
                      type="checkbox"
                      checked={selected.includes(Number(i.id))}
                      onChange={(e) =>
                        setSelected((p) =>
                          e.target.checked
                            ? [...p, Number(i.id)]
                            : p.filter((id) => id !== Number(i.id)),
                        )
                      }
                    />
                  </td>
                  <td>
                    <div className="table-customer">
                      <div className={`item-avatar avatar-${idx % 4}`}>
                        <Package size={19} />
                      </div>
                      <div>
                        <strong>{i.item_name}</strong>
                        <span>{i.unit}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <span className="code-pill">{i.item_code}</span>
                  </td>
                  <td>{i.category || '—'}</td>
                  <td>
                    <strong>{Number(i.total_stock).toLocaleString('en-IN')}</strong>{' '}
                    <span className="muted">{i.unit}</span>
                  </td>
                  <td>{money(Number(i.initial_daily_rate) * 30)}</td>
                  <td>{money(Number(i.initial_daily_rate))}</td>
                  <td>
                    <span className={`status-pill ${i.is_active === false ? 'inactive' : ''}`}>
                      <i />
                      {i.is_active === false ? 'Inactive' : 'Active'}
                    </span>
                  </td>
                  <td>
                    <button
                      className="icon-button"
                      aria-label={`Edit ${i.item_name}`}
                      onClick={() => onEdit(i)}
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      className="icon-button danger-icon"
                      aria-label={`Deactivate ${i.item_name}`}
                      title="Deactivate item (history is preserved)"
                      onClick={() => onDelete(i)}
                      disabled={i.is_active === false}
                    >
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {visibleItems.length === 0 && (
            <div className="empty-state">
              <Boxes size={30} />
              <strong>No items found</strong>
              <span>Add your first inventory item or adjust the search.</span>
            </div>
          )}
        </div>
        <div className="table-footer">
          <span>
            Showing <strong>{visibleItems.length}</strong> catalogue items
          </span>
          <span>Available stock updates automatically as deliveries and returns are recorded.</span>
        </div>
      </div>
    </>
  );
}
