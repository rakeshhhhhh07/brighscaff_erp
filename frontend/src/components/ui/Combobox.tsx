import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { Check, ChevronDown, X } from 'lucide-react';

export type ComboboxOption = {
  /** Stable value submitted by the form. */
  value: string;
  /** Primary line shown in the list and in the closed input. */
  label: string;
  /** Optional secondary line shown under the label. */
  hint?: string;
  /** Extra text matched against the query but never displayed. */
  keywords?: string;
};

type Props = {
  options: ComboboxOption[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
  required?: boolean;
  id?: string;
  /** Accessible name, used when the control is not wrapped in a <label>. */
  ariaLabel?: string;
};

/**
 * Searchable single-select. Clicking the field opens the full option list;
 * typing narrows it with a case-insensitive substring match over the label,
 * hint and keywords. Keyboard: Up/Down to move, Enter to pick, Escape to close.
 */
export default function Combobox({
  options,
  value,
  onChange,
  placeholder = 'Search or select',
  emptyMessage = 'No matches found',
  disabled = false,
  required = false,
  id,
  ariaLabel,
}: Props) {
  const generatedId = useId();
  const listId = `${id || generatedId}-listbox`;
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);

  const selected = useMemo(() => options.find((o) => o.value === value) || null, [options, value]);

  // An empty query means "show everything", which is what a plain click should do.
  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return options;
    return options.filter((o) =>
      `${o.label} ${o.hint || ''} ${o.keywords || ''}`.toLowerCase().includes(q),
    );
  }, [options, query]);

  // Close when focus or a click lands outside the component.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
        setQuery('');
      }
    }
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  // Keep the highlighted row inside the scroll viewport.
  useEffect(() => {
    if (!open || !listRef.current) return;
    const node = listRef.current.children[active] as HTMLElement | undefined;
    node?.scrollIntoView({ block: 'nearest' });
  }, [active, open]);

  function openList() {
    if (disabled) return;
    setOpen(true);
    setQuery('');
    const index = selected ? matches.findIndex((o) => o.value === selected.value) : 0;
    setActive(index < 0 ? 0 : index);
  }

  function commit(option: ComboboxOption) {
    onChange(option.value);
    setOpen(false);
    setQuery('');
    inputRef.current?.blur();
  }

  function clear() {
    onChange('');
    setQuery('');
    setOpen(false);
  }

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!open) {
        openList();
        return;
      }
      if (!matches.length) return;
      const step = event.key === 'ArrowDown' ? 1 : -1;
      setActive((i) => (i + step + matches.length) % matches.length);
      return;
    }
    if (event.key === 'Enter' && open) {
      event.preventDefault();
      const option = matches[active];
      if (option) commit(option);
      return;
    }
    if (event.key === 'Escape' && open) {
      event.preventDefault();
      setOpen(false);
      setQuery('');
      return;
    }
    if (event.key === 'Tab' && open) {
      setOpen(false);
      setQuery('');
    }
  }

  // Closed: show the selection. Open: show what the user is typing.
  const inputValue = open ? query : selected?.label || '';

  return (
    <div className={`combobox${open ? ' is-open' : ''}`} ref={rootRef}>
      <div className="combobox-control">
        <input
          id={id}
          ref={inputRef}
          type="text"
          className="combobox-input"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={
            open && matches[active] ? `${listId}-opt-${matches[active].value}` : undefined
          }
          aria-label={ariaLabel}
          autoComplete="off"
          disabled={disabled}
          placeholder={selected ? selected.label : placeholder}
          value={inputValue}
          onMouseDown={(e) => {
            // Toggle on click without letting focus re-open an already open list.
            e.preventDefault();
            if (open) {
              setOpen(false);
              setQuery('');
            } else {
              openList();
              inputRef.current?.focus();
            }
          }}
          onChange={(e) => {
            if (!open) setOpen(true);
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
        />
        {selected && !disabled && (
          <button
            type="button"
            className="combobox-clear"
            onClick={clear}
            aria-label="Clear selection"
            tabIndex={-1}
          >
            <X size={15} />
          </button>
        )}
        <ChevronDown size={16} className="combobox-caret" aria-hidden="true" />
        {/* Mirrors the selection so native form validation still applies.
            Disabled when the control is disabled so an intentionally
            inactive field cannot block form submission. */}
        {required && (
          <input
            className="combobox-required-mirror"
            tabIndex={-1}
            aria-hidden="true"
            required
            disabled={disabled}
            value={value}
            onChange={() => {}}
          />
        )}
      </div>
      {open && (
        <ul className="combobox-list" id={listId} role="listbox" ref={listRef}>
          {matches.map((option, index) => (
            <li
              key={option.value}
              id={`${listId}-opt-${option.value}`}
              role="option"
              aria-selected={option.value === value}
              className={`combobox-option${index === active ? ' is-active' : ''}${
                option.value === value ? ' is-selected' : ''
              }`}
              onMouseEnter={() => setActive(index)}
              onMouseDown={(e) => {
                e.preventDefault();
                commit(option);
              }}
            >
              <span className="combobox-option-text">
                <strong>{option.label}</strong>
                {option.hint && <small>{option.hint}</small>}
              </span>
              {option.value === value && <Check size={15} />}
            </li>
          ))}
          {!matches.length && <li className="combobox-empty">{emptyMessage}</li>}
        </ul>
      )}
    </div>
  );
}
