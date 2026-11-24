import { Lead, TableSkeleton } from '../../components/Feedback'
import { HandCoins, PackageCheck, ShoppingBag } from 'lucide-react'
import { ANY_DATE, DateRangeFilter, rangeParams } from '../../components/DateRangeFilter'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextField } from '../../components/Form'
import { ActionsHeader, actionColumns, RowActions } from '../../components/RowActions'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { formatDateTime, formatMoney, formatQuantity, newIdempotencyKey, todayIso } from '../../lib/format'
import type { Product } from '../catalog/ProductsPage'
import { ContactDialog, SUPPLIERS, type Contact } from '../contacts/ContactsPage'
import { CurrencySwitch, TxnAmount, useDisplayCurrency } from '../currencies/DisplayCurrency'
import { RateBanner, type CurrentRates } from '../currencies/ExchangeRate'
import { useAuth } from '../identity/AuthContext'
import { PAYMENT_METHODS, type PaymentMethod } from '../sales/types'
import type { Focus } from '../../app/focus'

type Status = 'open' | 'partially_received' | 'received' | 'cancelled'

interface PurchaseSummary {
  id: string
  number: string
  supplier_name: string
  section_name: string
  purchase_date: string
  supplier_reference: string
  status: Status
  status_label: string
  currency: string
  total: string
  base_total: string
  balance_due: string
  line_count: number
}

interface PurchaseLine {
  id: string
  variant: string
  label: string
  tracks_stock: boolean
  quantity: string
  quantity_received: string
  quantity_outstanding: string
  unit_cost: string
  line_total: string
}

interface Receipt {
  id: string
  number: string
  received_date: string
  note: string
  created_by_name: string
  created_at: string
  reversed_at: string | null
  reversed_by_name: string | null
  reversal_reason: string
  lines: { purchase_line: string; label: string; quantity: string }[]
}

interface PurchaseDetail extends PurchaseSummary {
  supplier: string
  paid_amount: string
  balance_due: string
  fx_units_per_usd: string
  fx_rate_date: string | null
  shipping_cost: string
  other_cost: string
  subtotal: string
  notes: string
  cancel_reason: string
  created_by_name: string
  lines: PurchaseLine[]
  receipts: Receipt[]
}

const STATUS_TABS: [string, string][] = [
  ['', 'All'],
  ['open', 'Open'],
  ['partially_received', 'Partly received'],
  ['received', 'Received'],
  ['cancelled', 'Cancelled'],
]
const STATUS_TONE: Record<Status, string> = {
  open: 'status-low',
  partially_received: 'status-low',
  received: 'status-ok',
  cancelled: 'status-muted',
}

export function PurchasesPage({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { can, focus: viewFocus } = useAuth()
  const actionCols = actionColumns(can('purchases.receive') && 'Receive', can('payables.pay') && 'Pay')
  const { rates, reloadRates } = useDisplayCurrency()
  const [status, setStatus] = useState('')
  const [query, setQuery] = useState(focus?.query ?? '')
  const [range, setRange] = useState(ANY_DATE)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page<PurchaseSummary> | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [creating, setCreating] = useState(false)
  const [openId, setOpenId] = useState<string | null>(focus?.id ?? null)
  const [openMode, setOpenMode] = useState<PurchaseMode>('view')
  const openPurchase = (id: string, mode: PurchaseMode = 'view') => {
    setOpenMode(mode)
    setOpenId(id)
  }

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setData(await api.get<Page<PurchaseSummary>>('/purchases/', { status, search: query, page, ...rangeParams(range) }))
    } catch (err) {
      setLoadError(err)
    }
  }, [status, query, page, range])

  useEffect(() => {
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">MANAGE</p>
          <h1>Purchases</h1>
          <p className="subheading">Stock increases only when goods are received.</p>
        </div>
        <CurrencySwitch />
        {can('purchases.create') && (
          <button className="button button-primary" onClick={() => setCreating(true)}>
            ＋ New purchase
          </button>
        )}
      </div>

      <RateBanner rates={rates} onChanged={reloadRates} />

      <div className="segmented-tabs" role="tablist" aria-label="Purchase status">
        {STATUS_TABS.map(([value, label]) => (
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
          placeholder="Search PO number, supplier or invoice ref"
          aria-label="Search purchases"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        <DateRangeFilter
          label="Purchase date"
          value={range}
          onChange={(next) => {
            setRange(next)
            setPage(1)
          }}
        />
      </div>

      <ErrorBanner error={loadError} />

      {data && data.results.length === 0 ? (
        <EmptyState
          icon={ShoppingBag}
          title={
            status || query || range.choice !== 'any' || viewFocus.section || viewFocus.branch ? 'No purchases match' : 'No purchases yet'
          }
        >
          {!status && !query && can('purchases.create') && (
            <button className="button button-secondary" onClick={() => setCreating(true)}>
              Record your first purchase
            </button>
          )}
        </EmptyState>
      ) : !data ? (
        !loadError && <TableSkeleton columns={5} />
      ) : (
        <div className="panel table-panel">
          <table className="data-table clickable-rows">
            <thead>
              <tr>
                <th scope="col">Purchase</th>
                <th scope="col" className="hide-mobile">
                  Date
                </th>
                <th scope="col">Status</th>
                <th scope="col" className="num">
                  Total
                </th>
                <ActionsHeader />
              </tr>
            </thead>
            <tbody>
              {data.results.map((p) => (
                <tr key={p.id} onClick={() => openPurchase(p.id)}>
                  <td>
                    <Lead icon={ShoppingBag} tone={p.status === 'cancelled' ? 'neutral' : 'blue'}>
                      <button
                        className="link-button"
                        onClick={(e) => {
                          e.stopPropagation()
                          openPurchase(p.id)
                        }}
                      >
                        {p.number}
                      </button>
                      <small className="cell-sub">
                        {p.supplier_name} · {p.section_name}
                        {p.supplier_reference && ` · ${p.supplier_reference}`}
                      </small>
                    </Lead>
                  </td>
                  <td className="hide-mobile">{p.purchase_date}</td>
                  <td>
                    <span className={`status-badge ${STATUS_TONE[p.status]}`}>{p.status_label}</span>
                  </td>
                  <td className="num">
                    <TxnAmount amount={p.total} currency={p.currency} baseAmount={p.base_total} />
                  </td>
                  <RowActions
                    label={`Actions for ${p.number}`}
                    columns={actionCols}
                    actions={{
                      Receive: (p.status === 'open' || p.status === 'partially_received') && {
                        label: 'Receive goods',
                        icon: PackageCheck,
                        tone: 'brand',
                        onClick: () => openPurchase(p.id, 'receive'),
                      },
                      Pay: p.status !== 'cancelled' &&
                        Number(p.balance_due) > 0 && {
                          label: 'Pay supplier',
                          icon: HandCoins,
                          tone: 'green',
                          onClick: () => openPurchase(p.id, 'pay'),
                        },
                    }}
                  />
                </tr>
              ))}
            </tbody>
          </table>
          {(data.next || data.previous) && (
            <div className="pager">
              <button className="button button-ghost" disabled={!data.previous} onClick={() => setPage((n) => n - 1)}>
                ← Previous
              </button>
              <span>Page {page}</span>
              <button className="button button-ghost" disabled={!data.next} onClick={() => setPage((n) => n + 1)}>
                Next →
              </button>
            </div>
          )}
        </div>
      )}

      {creating && (
        <NewPurchaseDialog
          rates={rates}
          onClose={() => setCreating(false)}
          onCreated={(purchase) => {
            setCreating(false)
            notify(`${purchase.number} recorded. Receive the goods when they arrive.`)
            setOpenId(purchase.id)
            void load()
          }}
        />
      )}
      {openId && (
        <PurchaseDetailDialog
          id={openId}
          initialMode={openMode}
          onClose={() => setOpenId(null)}
          onChanged={(message) => {
            notify(message)
            void load()
          }}
        />
      )}
    </div>
  )
}

/* ---------- New purchase ---------- */

interface ItemOption {
  variantId: string
  label: string
  cost: string | undefined
}
interface LineDraft {
  key: string
  variant: string
  quantity: string
  unit_cost: string
}

function blankLine(): LineDraft {
  return { key: newIdempotencyKey(), variant: '', quantity: '1', unit_cost: '' }
}

function NewPurchaseDialog({
  rates,
  onClose,
  onCreated,
}: {
  rates: CurrentRates | null
  onClose: () => void
  onCreated: (p: PurchaseDetail) => void
}) {
  const { sections, can } = useAuth()
  const [suppliers, setSuppliers] = useState<Contact[]>([])
  const [addingSupplier, setAddingSupplier] = useState(false)
  const [items, setItems] = useState<ItemOption[]>([])
  const [form, setForm] = useState({
    supplier: '',
    section: sections.length === 1 ? sections[0].id : '',
    purchase_date: todayIso(),
    currency: 'USD',
    supplier_reference: '',
    shipping_cost: '',
    other_cost: '',
    notes: '',
  })
  const [lines, setLines] = useState<LineDraft[]>([blankLine()])
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)

  useEffect(() => {
    api
      .get<Page<Contact>>('/suppliers/', { page_size: 200 })
      .then((p) => setSuppliers(p.results.filter((s) => s.active)))
      .catch(setError)
  }, [])

  useEffect(() => {
    if (!form.section) return
    api
      .get<Page<Product>>('/products/', { section: form.section, status: 'active', kind: 'product', page_size: 200 })
      .then((page) =>
        setItems(
          page.results.flatMap((product) => {
            const options = product.variants.filter((v) => v.active)
            return options.map((v) => ({
              variantId: v.id,
              label: v.code === 'default' ? product.name : `${product.name} · ${[v.size, v.color].filter(Boolean).join(' / ') || v.code}`,
              cost: product.buying_price_base,
            }))
          }),
        ),
      )
      .catch(setError)
  }, [form.section])

  const setField = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const setLine = (index: number, patch: Partial<LineDraft>) => setLines((all) => all.map((l, i) => (i === index ? { ...l, ...patch } : l)))

  // Display-only preview; the server recalculates and is the source of truth.
  const subtotal = lines.reduce((sum, l) => sum + (Number(l.quantity) || 0) * (Number(l.unit_cost) || 0), 0)
  const total = subtotal + (Number(form.shipping_cost) || 0) + (Number(form.other_cost) || 0)
  const lrd = rates?.rates.LRD
  const lrdBlocked = form.currency === 'LRD' && !lrd

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    if (!form.supplier) errors.supplier = ['Choose a supplier.']
    if (!form.section) errors.section = ['Choose a section.']
    lines.forEach((l, i) => {
      if (!l.variant) errors[`lines.${i}.variant`] = ['Choose an item.']
      if (!(Number(l.quantity) > 0)) errors[`lines.${i}.quantity`] = ['Enter a quantity.']
      if (l.unit_cost === '' || Number(l.unit_cost) < 0) errors[`lines.${i}.unit_cost`] = ['Enter the unit cost.']
    })
    if (Object.keys(errors).length) {
      setFieldErrors(errors)
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const created = await api.post<PurchaseDetail>(
        '/purchases/',
        {
          ...form,
          shipping_cost: form.shipping_cost || '0',
          other_cost: form.other_cost || '0',
          lines: lines.map(({ variant, quantity, unit_cost }) => ({ variant, quantity, unit_cost })),
        },
        idempotencyKey,
      )
      onCreated(created)
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Dialog title="New purchase" onClose={onClose} onSubmit={handleSubmit} wide>
        <ErrorBanner error={error} />
        <div className="field-row field-row-end">
          <SelectField label="Supplier" value={form.supplier} onChange={setField('supplier')} error={fieldErrors.supplier}>
            <option value="">Choose…</option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </SelectField>
          {can('suppliers.create') && (
            <button type="button" className="button button-secondary add-variant" onClick={() => setAddingSupplier(true)}>
              ＋ New
            </button>
          )}
        </div>
        <div className="field-row">
          <SelectField
            label="Section"
            value={form.section}
            onChange={(e) => {
              setField('section')(e)
              setLines([blankLine()])
              setItems([])
            }}
            error={fieldErrors.section}
          >
            <option value="">Choose…</option>
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </SelectField>
          <TextField
            label="Purchase date"
            type="date"
            max={todayIso()}
            value={form.purchase_date}
            onChange={setField('purchase_date')}
            error={fieldErrors.purchase_date}
          />
        </div>
        <div className="field-row">
          <SelectField
            label="Currency"
            value={form.currency}
            onChange={setField('currency')}
            error={fieldErrors.currency}
            hint={
              form.currency === 'LRD' ? (lrd ? `Converted at 1 USD = ${Number(lrd.units_per_usd)} LRD` : 'No LRD rate set yet') : undefined
            }
          >
            <option value="USD">USD</option>
            <option value="LRD">LRD</option>
          </SelectField>
          <TextField
            label="Supplier invoice / ref (optional)"
            value={form.supplier_reference}
            onChange={setField('supplier_reference')}
            error={fieldErrors.supplier_reference}
          />
        </div>

        <fieldset className="subsection">
          <legend>Items</legend>
          {!form.section && <p className="field-hint">Choose a section to list its products.</p>}
          {form.section && items.length === 0 && (
            <p className="field-hint">No products in this section yet. Add them under Products first.</p>
          )}
          {lines.map((line, index) => (
            <div className="line-row" key={line.key}>
              <SelectField
                label="Item"
                value={line.variant}
                error={fieldErrors[`lines.${index}.variant`]}
                onChange={(e) => {
                  const option = items.find((o) => o.variantId === e.target.value)
                  setLine(index, {
                    variant: e.target.value,
                    unit_cost:
                      line.unit_cost ||
                      (form.currency === 'USD' && option?.cost && Number(option.cost) > 0 ? String(Number(option.cost)) : ''),
                  })
                }}
              >
                <option value="">Choose…</option>
                {items.map((o) => (
                  <option key={o.variantId} value={o.variantId}>
                    {o.label}
                  </option>
                ))}
              </SelectField>
              <TextField
                label="Qty"
                inputMode="decimal"
                value={line.quantity}
                onChange={(e) => setLine(index, { quantity: e.target.value })}
                error={fieldErrors[`lines.${index}.quantity`]}
              />
              <TextField
                label={`Unit cost (${form.currency})`}
                inputMode="decimal"
                value={line.unit_cost}
                onChange={(e) => setLine(index, { unit_cost: e.target.value })}
                error={fieldErrors[`lines.${index}.unit_cost`]}
              />
              <button
                type="button"
                className="icon-close line-remove"
                aria-label="Remove item"
                disabled={lines.length === 1}
                onClick={() => setLines((all) => all.filter((_, i) => i !== index))}
              >
                ×
              </button>
            </div>
          ))}
          {fieldErrors.lines && <p className="field-error">{fieldErrors.lines.join(' ')}</p>}
          <button
            type="button"
            className="button button-ghost add-line"
            onClick={() => setLines((all) => [...all, blankLine()])}
            disabled={!form.section}
          >
            ＋ Add another item
          </button>
        </fieldset>

        <div className="field-row">
          <TextField
            label={`Shipping (${form.currency})`}
            inputMode="decimal"
            value={form.shipping_cost}
            onChange={setField('shipping_cost')}
            error={fieldErrors.shipping_cost}
          />
          <TextField
            label={`Other costs (${form.currency})`}
            inputMode="decimal"
            value={form.other_cost}
            onChange={setField('other_cost')}
            error={fieldErrors.other_cost}
            hint="Spread across items as part of their stock cost."
          />
        </div>
        <div className="totals">
          <span>Items {formatMoney(String(subtotal), form.currency)}</span>
          <b>Total {formatMoney(String(total), form.currency)}</b>
          {form.currency === 'LRD' && lrd && <small>≈ {formatMoney(String(total / Number(lrd.units_per_usd)), 'USD')}</small>}
        </div>
        <div className="dialog-actions">
          <button type="button" className="button button-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="button button-primary" disabled={saving || lrdBlocked}>
            {saving ? 'Saving…' : 'Save purchase'}
          </button>
        </div>
      </Dialog>
      {/* Rendered beside, not inside, the purchase form: nested forms would submit both. */}
      {addingSupplier && (
        <ContactDialog
          kind={SUPPLIERS}
          contact={null}
          onClose={() => setAddingSupplier(false)}
          onSaved={(supplier) => {
            setSuppliers((list) => [...list, supplier].sort((a, b) => a.name.localeCompare(b.name)))
            setForm((f) => ({ ...f, supplier: supplier.id }))
            setAddingSupplier(false)
          }}
        />
      )}
    </>
  )
}

/* ---------- Detail, receiving, reversal ---------- */

type PurchaseMode = 'view' | 'receive' | 'pay'

function PurchaseDetailDialog({
  id,
  initialMode = 'view',
  onClose,
  onChanged,
}: {
  id: string
  initialMode?: PurchaseMode
  onClose: () => void
  onChanged: (message: string) => void
}) {
  const { can } = useAuth()
  const [purchase, setPurchase] = useState<PurchaseDetail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [mode, setMode] = useState<PurchaseMode | 'cancel'>(initialMode)
  const [reversing, setReversing] = useState<Receipt | null>(null)

  useEffect(() => {
    api.get<PurchaseDetail>(`/purchases/${id}/`).then(setPurchase).catch(setError)
  }, [id])

  const updated = (next: PurchaseDetail, message: string) => {
    setPurchase(next)
    setMode('view')
    setReversing(null)
    onChanged(message)
  }

  if (!purchase) {
    return (
      <Dialog title="Purchase" onClose={onClose} wide>
        <ErrorBanner error={error} />
        {!error && <p className="subheading">Loading…</p>}
      </Dialog>
    )
  }

  const canReceive = can('purchases.receive') && (purchase.status === 'open' || purchase.status === 'partially_received')
  const nothingReceived = purchase.lines.every((l) => Number(l.quantity_received) === 0)
  const canCancel = can('purchases.create') && purchase.status === 'open' && nothingReceived && Number(purchase.paid_amount) === 0

  return (
    <Dialog title={`${purchase.number} · ${purchase.supplier_name}`} onClose={onClose} wide>
      <div className="detail-meta">
        <span className={`status-badge ${STATUS_TONE[purchase.status]}`}>{purchase.status_label}</span>
        <span>{purchase.section_name}</span>
        <span>{purchase.purchase_date}</span>
        {purchase.supplier_reference && <span>Ref {purchase.supplier_reference}</span>}
        {purchase.currency !== 'USD' && (
          <span>
            1 USD = {Number(purchase.fx_units_per_usd)} {purchase.currency}
          </span>
        )}
      </div>
      <ErrorBanner error={error} />
      {purchase.status === 'cancelled' && <div className="error-banner">Cancelled: {purchase.cancel_reason}</div>}

      {mode === 'receive' ? (
        <ReceiveForm
          purchase={purchase}
          onCancel={() => setMode('view')}
          onDone={(next) => updated(next, `Goods received on ${next.number}. Stock updated.`)}
        />
      ) : (
        <>
          <table className="data-table compact">
            <thead>
              <tr>
                <th scope="col">Item</th>
                <th scope="col" className="num">
                  Ordered
                </th>
                <th scope="col" className="num">
                  Received
                </th>
                <th scope="col" className="num">
                  Cost
                </th>
              </tr>
            </thead>
            <tbody>
              {purchase.lines.map((l) => (
                <tr key={l.id}>
                  <td>
                    {l.label}
                    {!l.tracks_stock && <small className="cell-sub">Stock not tracked</small>}
                  </td>
                  <td className="num">{formatQuantity(l.quantity)}</td>
                  <td className="num">{formatQuantity(l.quantity_received)}</td>
                  <td className="num">
                    {formatMoney(l.line_total, purchase.currency)}
                    <small className="cell-sub">{formatMoney(l.unit_cost, purchase.currency)} each</small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="totals">
            <span>Items {formatMoney(purchase.subtotal, purchase.currency)}</span>
            {Number(purchase.shipping_cost) > 0 && <span>Shipping {formatMoney(purchase.shipping_cost, purchase.currency)}</span>}
            {Number(purchase.other_cost) > 0 && <span>Other {formatMoney(purchase.other_cost, purchase.currency)}</span>}
            <b>Total {formatMoney(purchase.total, purchase.currency)}</b>
            {purchase.currency !== 'USD' && purchase.base_total && <small>≈ {formatMoney(purchase.base_total, 'USD')}</small>}
          </div>
          {purchase.status !== 'cancelled' && (
            <div className="totals paid-line">
              <span>Paid {formatMoney(purchase.paid_amount, purchase.currency)}</span>
              <b className={Number(purchase.balance_due) > 0 ? 'owing' : 'settled'}>
                {Number(purchase.balance_due) > 0 ? `Balance ${formatMoney(purchase.balance_due, purchase.currency)}` : 'Fully paid'}
              </b>
            </div>
          )}

          {purchase.receipts.length > 0 && (
            <>
              <h3 className="section-title">Deliveries</h3>
              <ol className="timeline">
                {purchase.receipts.map((r) => (
                  <li key={r.id} className={r.reversed_at ? 'is-reversed' : ''}>
                    <span className="delta delta-in">{r.number}</span>
                    <div>
                      <b>{r.lines.map((l) => `${formatQuantity(l.quantity)} × ${l.label}`).join(', ')}</b>
                      <small>
                        {r.received_date} · {r.created_by_name}
                        {r.note && ` · ${r.note}`}
                      </small>
                      {r.reversed_at && (
                        <small className="reversed-note">
                          Reversed by {r.reversed_by_name} on {formatDateTime(r.reversed_at)}: {r.reversal_reason}
                        </small>
                      )}
                    </div>
                    {!r.reversed_at && can('purchases.receive') && (
                      <button className="button button-ghost" onClick={() => setReversing(r)}>
                        Reverse
                      </button>
                    )}
                  </li>
                ))}
              </ol>
            </>
          )}

          {mode === 'pay' ? (
            <PaySupplierForm purchase={purchase} onBack={() => setMode('view')} onDone={(next, message) => updated(next, message)} />
          ) : mode === 'cancel' ? (
            <ReasonForm
              label="Why is this purchase being cancelled?"
              submitLabel="Cancel purchase"
              onBack={() => setMode('view')}
              onSubmit={(reason) => api.post<PurchaseDetail>(`/purchases/${purchase.id}/cancel/`, { reason })}
              onDone={(next) => updated(next, `${next.number} cancelled.`)}
            />
          ) : reversing ? (
            <ReasonForm
              label={`Why is ${reversing.number} being reversed? Its stock will be removed.`}
              submitLabel="Reverse delivery"
              onBack={() => setReversing(null)}
              onSubmit={(reason) => api.post<PurchaseDetail>(`/purchases/${purchase.id}/receipts/${reversing.id}/reverse/`, { reason })}
              onDone={(next) => updated(next, `${reversing.number} reversed. Stock removed.`)}
            />
          ) : (
            <div className="dialog-actions">
              {canCancel && (
                <button className="button button-secondary" onClick={() => setMode('cancel')}>
                  Cancel purchase
                </button>
              )}
              {can('payables.pay') && purchase.status !== 'cancelled' && Number(purchase.balance_due) > 0 && (
                <button className="button button-secondary" onClick={() => setMode('pay')}>
                  Pay supplier
                </button>
              )}
              <button className="button button-secondary" onClick={onClose}>
                Close
              </button>
              {canReceive && (
                <button className="button button-primary" onClick={() => setMode('receive')}>
                  Receive goods
                </button>
              )}
            </div>
          )}
        </>
      )}
    </Dialog>
  )
}

function ReceiveForm({
  purchase,
  onCancel,
  onDone,
}: {
  purchase: PurchaseDetail
  onCancel: () => void
  onDone: (p: PurchaseDetail) => void
}) {
  const outstanding = purchase.lines.filter((l) => Number(l.quantity_outstanding) > 0)
  const [quantities, setQuantities] = useState<Record<string, string>>(() =>
    Object.fromEntries(outstanding.map((l) => [l.id, String(Number(l.quantity_outstanding))])),
  )
  const [date, setDate] = useState(todayIso())
  const [note, setNote] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    for (const line of outstanding) {
      const qty = Number(quantities[line.id] || 0)
      if (qty < 0 || qty > Number(line.quantity_outstanding))
        errors[`lines.${line.id}`] = [`Enter 0 to ${formatQuantity(line.quantity_outstanding)}.`]
    }
    if (!Object.values(quantities).some((q) => Number(q) > 0)) errors.lines = ['Enter a quantity for at least one item.']
    if (Object.keys(errors).length) {
      setFieldErrors(errors)
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      onDone(
        await api.post<PurchaseDetail>(
          `/purchases/${purchase.id}/receive/`,
          { lines: quantities, received_date: date, note: note.trim() },
          idempotencyKey,
        ),
      )
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <p className="dialog-lead">Enter what actually arrived. Anything not delivered stays outstanding for a later delivery.</p>
      <ErrorBanner error={error} />
      {outstanding.map((line) => (
        <div className="receive-row" key={line.id}>
          <div>
            <b>{line.label}</b>
            <small className="cell-sub">
              {formatQuantity(line.quantity_outstanding)} outstanding of {formatQuantity(line.quantity)}
            </small>
          </div>
          <TextField
            label="Received now"
            inputMode="decimal"
            value={quantities[line.id] ?? ''}
            error={fieldErrors[`lines.${line.id}`]}
            onChange={(e) => setQuantities((q) => ({ ...q, [line.id]: e.target.value }))}
          />
        </div>
      ))}
      {fieldErrors.lines && <p className="field-error">{fieldErrors.lines.join(' ')}</p>}
      <div className="field-row">
        <TextField label="Date received" type="date" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />
        <TextField label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Delivery note #" />
      </div>
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onCancel}>
          Back
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Confirm receipt'}
        </button>
      </div>
    </form>
  )
}

function ReasonForm({
  label,
  submitLabel,
  onBack,
  onSubmit,
  onDone,
}: {
  label: string
  submitLabel: string
  onBack: () => void
  onSubmit: (reason: string) => Promise<PurchaseDetail>
  onDone: (p: PurchaseDetail) => void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [fieldError, setFieldError] = useState<string[] | undefined>()

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!reason.trim()) {
      setFieldError(['A reason is required.'])
      return
    }
    setSaving(true)
    setError(null)
    try {
      onDone(await onSubmit(reason.trim()))
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="reason-form" onSubmit={handleSubmit} noValidate>
      <ErrorBanner error={error} />
      <TextField label={label} autoFocus value={reason} onChange={(e) => setReason(e.target.value)} error={fieldError} />
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-danger" disabled={saving}>
          {saving ? 'Saving…' : submitLabel}
        </button>
      </div>
    </form>
  )
}

function PaySupplierForm({
  purchase,
  onBack,
  onDone,
}: {
  purchase: PurchaseDetail
  onBack: () => void
  onDone: (p: PurchaseDetail, message: string) => void
}) {
  const [amount, setAmount] = useState(purchase.balance_due)
  const [method, setMethod] = useState<PaymentMethod>('bank_transfer')
  const [reference, setReference] = useState('')
  const [paidOn, setPaidOn] = useState(todayIso())
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!(Number(amount) > 0) || Number(amount) > Number(purchase.balance_due)) {
      setFieldErrors({ amount: [`Enter up to ${formatMoney(purchase.balance_due, purchase.currency)}.`] })
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const payment = await api.post<{ number: string }>(
        '/supplier-payments/',
        {
          supplier: purchase.supplier,
          currency: purchase.currency,
          amount,
          method,
          reference: reference.trim(),
          paid_on: paidOn,
          allocations: { [purchase.id]: amount },
        },
        idempotencyKey,
      )
      const next = await api.get<PurchaseDetail>(`/purchases/${purchase.id}/`)
      onDone(next, `${payment.number}: paid ${formatMoney(amount, purchase.currency)} to ${purchase.supplier_name}.`)
    } catch (err) {
      if (err instanceof ApiError)
        setFieldErrors(Object.fromEntries(Object.entries(err.fieldErrors).map(([k, v]) => [k.startsWith('allocations') ? 'amount' : k, v])))
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="reason-form" onSubmit={submit} noValidate>
      <ErrorBanner error={error} />
      <div className="field-row">
        <TextField
          label={`Amount (${purchase.currency})`}
          inputMode="decimal"
          autoFocus
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          error={fieldErrors.amount}
        />
        <SelectField label="Method" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
          {PAYMENT_METHODS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectField>
      </div>
      <div className="field-row">
        <TextField
          label="Reference (optional)"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          placeholder="Transfer or receipt no."
        />
        <TextField
          label="Paid on"
          type="date"
          max={todayIso()}
          value={paidOn}
          onChange={(e) => setPaidOn(e.target.value)}
          error={fieldErrors.paid_on}
        />
      </div>
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Record payment'}
        </button>
      </div>
    </form>
  )
}
