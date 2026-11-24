import { MenuSelect } from '../../components/MenuSelect'
import { Boxes, History, Layers, Package, SlidersHorizontal } from 'lucide-react'
import { Lead, StatusBadge, TableSkeleton } from '../../components/Feedback'
import { ActionsHeader, actionColumns, RowActions } from '../../components/RowActions'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { formatDateTime, formatMoney, formatQuantity, newIdempotencyKey } from '../../lib/format'
import { CurrencySwitch, useDisplayCurrency } from '../currencies/DisplayCurrency'
import { useAuth } from '../identity/AuthContext'
import type { Focus } from '../../app/focus'

type StockStatus = 'ok' | 'low' | 'out'

interface StockLevel {
  variant_id: string
  product_id: string
  label: string
  sku: string
  section: { id: string; name: string }
  on_hand: string
  minimum_stock: string
  status: StockStatus
  average_cost_base?: string
  stock_value_base?: string
}

interface StockPage extends Page<StockLevel> {
  valuation_basis: string
  total_value_base?: string
}

interface Movement {
  id: string
  movement_type_label: string
  quantity_delta: string
  quantity_after: string
  unit_cost_base?: string
  reason: string
  created_by_name: string
  created_at: string
}

const STATUS_LABEL: Record<StockStatus, string> = { ok: 'In stock', low: 'Low', out: 'Out of stock' }
const FILTERS = [
  ['', 'All items'],
  ['attention', 'Needs attention'],
  ['low', 'Low'],
  ['out', 'Out of stock'],
] as const

export function InventoryPage({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { can, viewSections: sections } = useAuth()
  const actionCols = actionColumns('History', can('inventory.adjust') && 'Adjust')
  const { base } = useDisplayCurrency()
  const showCosts = can('inventory.costs')
  const [query, setQuery] = useState(focus?.query ?? '')
  const [section, setSection] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<StockPage | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [adjusting, setAdjusting] = useState<StockLevel | null>(null)
  const [history, setHistory] = useState<StockLevel | null>(null)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setData(await api.get<StockPage>('/stock/', { search: query, section, status, page }))
    } catch (err) {
      setLoadError(err)
    }
  }, [query, section, status, page])

  useEffect(() => {
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">MANAGE</p>
          <h1>Inventory</h1>
          <p className="subheading">
            {data ? `${data.count} stocked items` : 'Loading…'}
            {showCosts && data?.total_value_base && (
              <>
                {' '}
                · Stock value <b>{base(data.total_value_base)}</b> (weighted-average cost)
              </>
            )}
          </p>
        </div>
        {showCosts && <CurrencySwitch />}
      </div>

      <div className="segmented-tabs" role="tablist" aria-label="Stock status">
        {FILTERS.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={status === value}
            className={status === value ? 'active' : ''}
            onClick={() => {
              setStatus(value)
              setPage(1)
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="toolbar">
        <input
          type="search"
          className="search-input"
          placeholder="Search product, SKU, size or colour"
          aria-label="Search stock"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        {sections.length > 1 && (
          <MenuSelect
            variant="pill"
            icon={Layers}
            className="toolbar-select"
            aria-label="Section"
            value={section}
            onChange={(e) => {
              setSection(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All sections</option>
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </MenuSelect>
        )}
      </div>

      <ErrorBanner error={loadError} />

      {data && data.results.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title={status ? 'Nothing needs attention here' : query || section ? 'No items match' : 'No stocked products yet'}
        >
          {!status && !query && !section && (
            <p className="subheading">Add products under Products &amp; services, then record opening stock here.</p>
          )}
        </EmptyState>
      ) : !data ? (
        !loadError && <TableSkeleton columns={5} />
      ) : (
        <div className="panel table-panel">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col" className="num">
                  On hand
                </th>
                <th scope="col" className="hide-mobile">
                  Status
                </th>
                {showCosts && (
                  <th scope="col" className="num hide-mobile">
                    Value
                  </th>
                )}
                <ActionsHeader />
              </tr>
            </thead>
            <tbody>
              {data.results.map((row) => (
                <tr key={row.variant_id}>
                  <td>
                    <Lead icon={Package} tone={row.status === 'ok' ? 'green' : row.status === 'low' ? 'amber' : 'red'}>
                      <b>{row.label}</b>
                      <small className="cell-sub">
                        {[row.section.name, row.sku, `alert at ${formatQuantity(row.minimum_stock)}`].filter(Boolean).join(' · ')}
                      </small>
                      <StatusBadge tone={row.status} className="show-mobile">
                        {STATUS_LABEL[row.status]}
                      </StatusBadge>
                    </Lead>
                  </td>
                  <td className="num">
                    <b>{formatQuantity(row.on_hand)}</b>
                  </td>
                  <td className="hide-mobile">
                    <StatusBadge tone={row.status}>{STATUS_LABEL[row.status]}</StatusBadge>
                  </td>
                  {showCosts && <td className="num hide-mobile">{base(row.stock_value_base)}</td>}
                  <RowActions
                    label={`Actions for ${row.label}`}
                    columns={actionCols}
                    actions={{
                      History: { label: 'Stock history', icon: History, tone: 'blue', onClick: () => setHistory(row) },
                      Adjust: {
                        label: 'Adjust stock',
                        icon: SlidersHorizontal,
                        tone: 'amber',
                        onClick: () => setAdjusting(row),
                      },
                    }}
                  />
                </tr>
              ))}
            </tbody>
          </table>
          {(data.next || data.previous) && (
            <div className="pager">
              <button className="button button-ghost" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>
                ← Previous
              </button>
              <span>Page {page}</span>
              <button className="button button-ghost" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>
                Next →
              </button>
            </div>
          )}
        </div>
      )}

      {adjusting && (
        <AdjustDialog
          item={adjusting}
          onClose={() => setAdjusting(null)}
          onSaved={(message) => {
            setAdjusting(null)
            notify(message)
            void load()
          }}
        />
      )}
      {history && <HistoryDialog item={history} onClose={() => setHistory(null)} />}
    </div>
  )
}

const REASONS = {
  in: [
    ['opening', 'Opening stock'],
    ['count_correction', 'Stock count correction'],
    ['customer_return', 'Customer return'],
    ['other', 'Other'],
  ],
  out: [
    ['damage', 'Damaged'],
    ['loss', 'Lost or stolen'],
    ['count_correction', 'Stock count correction'],
    ['other', 'Other'],
  ],
} as const

function AdjustDialog({ item, onClose, onSaved }: { item: StockLevel; onClose: () => void; onSaved: (message: string) => void }) {
  const { organization } = useAuth()
  const currency = organization?.base_currency ?? 'USD'
  const [direction, setDirection] = useState<'in' | 'out'>(Number(item.on_hand) > 0 ? 'out' : 'in')
  const [reason, setReason] = useState<string>(Number(item.on_hand) > 0 ? 'damage' : 'opening')
  const [quantity, setQuantity] = useState('')
  const [unitCost, setUnitCost] = useState(item.average_cost_base && Number(item.average_cost_base) > 0 ? item.average_cost_base : '')
  const [note, setNote] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  // One key per dialog: double-taps and retries of the same adjustment are applied once.
  const [idempotencyKey] = useState(newIdempotencyKey)

  const needsCost = direction === 'in' && reason === 'opening'
  const needsNote = reason === 'other' || reason === 'count_correction'
  const qty = Number(quantity)
  const after = Number(item.on_hand) + (direction === 'in' ? qty : -qty)

  function chooseDirection(next: 'in' | 'out') {
    setDirection(next)
    setReason(REASONS[next][0][0])
    setFieldErrors({})
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    if (!(qty > 0)) errors.quantity_delta = ['Enter a quantity greater than zero.']
    else if (after < 0) errors.quantity_delta = [`Only ${formatQuantity(item.on_hand)} in stock.`]
    if (needsCost && !(Number(unitCost) >= 0 && unitCost !== '')) errors.unit_cost_base = ['Enter the cost per unit.']
    if (needsNote && !note.trim()) errors.note = ['Explain this adjustment.']
    if (Object.keys(errors).length) {
      setFieldErrors(errors)
      return
    }

    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      await api.post(
        '/stock-adjustments/',
        {
          variant: item.variant_id,
          quantity_delta: direction === 'in' ? quantity : `-${quantity}`,
          reason,
          note: note.trim(),
          unit_cost_base: direction === 'in' && unitCost !== '' ? unitCost : null,
        },
        idempotencyKey,
      )
      onSaved(
        `${item.label}: ${direction === 'in' ? 'added' : 'removed'} ${formatQuantity(quantity)}. Now ${formatQuantity(String(after))} on hand.`,
      )
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title={`Adjust stock · ${item.label}`} onClose={onClose} onSubmit={handleSubmit}>
      <p className="dialog-lead">
        On hand now: <b>{formatQuantity(item.on_hand)}</b>
      </p>
      <ErrorBanner error={error} />
      <div className="segmented-tabs segmented-full" role="radiogroup" aria-label="Direction">
        <button
          type="button"
          role="radio"
          aria-checked={direction === 'in'}
          className={direction === 'in' ? 'active' : ''}
          onClick={() => chooseDirection('in')}
        >
          ＋ Add stock
        </button>
        <button
          type="button"
          role="radio"
          aria-checked={direction === 'out'}
          className={direction === 'out' ? 'active' : ''}
          onClick={() => chooseDirection('out')}
        >
          − Remove stock
        </button>
      </div>
      <SelectField label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} error={fieldErrors.reason}>
        {REASONS[direction].map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </SelectField>
      <div className="field-row">
        <TextField
          label="Quantity"
          inputMode="decimal"
          autoFocus
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          error={fieldErrors.quantity_delta}
          hint={qty > 0 && after >= 0 ? `After: ${formatQuantity(String(after))}` : undefined}
        />
        {direction === 'in' && (
          <TextField
            label={`Cost per unit (${currency})${needsCost ? '' : ' (optional)'}`}
            inputMode="decimal"
            value={unitCost}
            onChange={(e) => setUnitCost(e.target.value)}
            error={fieldErrors.unit_cost_base}
            hint={needsCost ? 'Sets the starting average cost.' : 'Leave blank to keep the current average.'}
          />
        )}
      </div>
      <TextField
        label={needsNote ? 'Note' : 'Note (optional)'}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        error={fieldErrors.note}
        placeholder={reason === 'count_correction' ? 'e.g. Monthly count, shelf B' : ''}
      />
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save adjustment'}
        </button>
      </div>
    </Dialog>
  )
}

function HistoryDialog({ item, onClose }: { item: StockLevel; onClose: () => void }) {
  const { organization } = useAuth()
  const [data, setData] = useState<Page<Movement> | null>(null)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    api.get<Page<Movement>>('/stock-movements/', { variant: item.variant_id, page_size: 100 }).then(setData).catch(setError)
  }, [item.variant_id])

  return (
    <Dialog title={`Stock history · ${item.label}`} onClose={onClose} wide>
      <ErrorBanner error={error} />
      {!data && !error && <p className="subheading">Loading…</p>}
      {data && data.results.length === 0 && <EmptyState title="No stock movements yet" />}
      {data && data.results.length > 0 && (
        <ol className="timeline">
          {data.results.map((m) => {
            const positive = Number(m.quantity_delta) > 0
            return (
              <li key={m.id}>
                <span className={`delta ${positive ? 'delta-in' : 'delta-out'}`}>
                  {positive ? '+' : ''}
                  {formatQuantity(m.quantity_delta)}
                </span>
                <div>
                  <b>{m.movement_type_label}</b>
                  {m.reason && m.reason !== m.movement_type_label && <> · {m.reason}</>}
                  <small>
                    {formatDateTime(m.created_at)} · {m.created_by_name} · balance {formatQuantity(m.quantity_after)}
                    {m.unit_cost_base !== undefined && <> · {formatMoney(m.unit_cost_base, organization?.base_currency)}/unit</>}
                  </small>
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </Dialog>
  )
}
