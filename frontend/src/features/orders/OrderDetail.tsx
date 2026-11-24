import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { formatDateTime, formatMoney, formatQuantity, newIdempotencyKey } from '../../lib/format'
import { useAuth } from '../identity/AuthContext'
import { PAYMENT_METHODS, type PaymentMethod } from '../sales/types'
import { DueCell, OrderStatusBadge } from './OrderBits'
import { OrderFormDialog } from './OrderForm'
import type { OrderDetail } from './types'

type Mode = 'view' | 'pay' | 'status' | 'cancel' | 'material' | { returning: string }

export function OrderDetailDialog({
  id,
  initialMode = 'view',
  onClose,
  onChanged,
}: {
  id: string
  initialMode?: 'view' | 'pay'
  onClose: () => void
  onChanged: (message: string) => void
}) {
  const { can, organization } = useAuth()
  const [order, setOrder] = useState<OrderDetail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [mode, setMode] = useState<Mode>(initialMode)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.get<OrderDetail>(`/orders/${id}/`).then(setOrder).catch(setError)
  }, [id])

  const done = useCallback(
    (next: OrderDetail, message: string) => {
      setOrder(next)
      setMode('view')
      setError(null)
      onChanged(message)
    },
    [onChanged],
  )

  if (!order)
    return (
      <Dialog title="Order" onClose={onClose} wide>
        <ErrorBanner error={error} />
        {!error && <p className="subheading">Loading…</p>}
      </Dialog>
    )

  const open = order.status !== 'delivered' && order.status !== 'cancelled'
  const flowIndex = order.flow.findIndex((s) => s.code === order.status)
  const next = open ? order.flow[flowIndex + 1] : undefined
  const balance = Number(order.balance_due)
  const canUpdate = can('orders.update') && open

  async function advance() {
    if (!next || !order) return
    if (
      next.code === 'delivered' &&
      balance > 0 &&
      !window.confirm(`${formatMoney(order.balance_due, order.currency)} is still unpaid. Mark ${order.number} as delivered anyway?`)
    )
      return
    setBusy(true)
    setError(null)
    try {
      done(await api.post<OrderDetail>(`/orders/${order.id}/status/`, { status: next.code }), `${order.number}: ${next.label}.`)
    } catch (err) {
      setError(err)
    } finally {
      setBusy(false)
    }
  }

  if (editing) {
    return (
      <OrderFormDialog
        order={order}
        onClose={() => setEditing(false)}
        onSaved={(saved) => {
          setEditing(false)
          done(saved, `${saved.number} updated.`)
        }}
      />
    )
  }

  return (
    <Dialog title={`${order.number} · ${order.customer_name}`} onClose={onClose} wide>
      <ErrorBanner error={error} />
      {order.status === 'cancelled' && (
        <div className="error-banner">
          Cancelled{order.cancelled_at && ` on ${formatDateTime(order.cancelled_at)}`}: {order.cancel_reason}
        </div>
      )}

      <div className="order-head">
        <div>
          <p className="order-kind">
            <span className={`kind-dot kind-${order.kind}`} aria-hidden="true" />
            {order.kind_label} · {order.section_name}
          </p>
          <h3 className="order-heading">{order.title}</h3>
          <p className="field-hint">
            {order.customer_phone && <>{order.customer_phone} · </>}Taken by {order.created_by_name} on {formatDateTime(order.created_at)}
          </p>
        </div>
        <OrderStatusBadge order={order} />
      </div>

      {order.status !== 'cancelled' && (
        <ol className="order-steps" aria-label="Progress">
          {order.flow.map((step, i) => (
            <li
              key={step.code}
              className={i < flowIndex ? 'done' : i === flowIndex ? 'current' : ''}
              aria-current={i === flowIndex ? 'step' : undefined}
            >
              <span className="step-dot" aria-hidden="true">
                {i < flowIndex || order.status === 'delivered' ? '✓' : i + 1}
              </span>
              <span className="step-label">{step.label}</span>
            </li>
          ))}
        </ol>
      )}

      <div className="order-facts">
        <div>
          <small>Due</small>
          <DueCell order={order} />
        </div>
        <div>
          <small>Assigned to</small>
          <b>{order.assigned_to_name ?? 'Not assigned'}</b>
        </div>
        <div>
          <small>Price</small>
          <b>{formatMoney(order.total, order.currency)}</b>
          {order.currency !== 'USD' && <small className="cell-sub">≈ {formatMoney(order.base_total, 'USD')}</small>}
        </div>
        <div>
          <small>Paid</small>
          <b>{formatMoney(order.paid_amount, order.currency)}</b>
        </div>
        <div className={balance > 0 && order.status !== 'cancelled' ? 'fact-due' : ''}>
          <small>Balance</small>
          <b>{order.status === 'cancelled' ? '—' : balance > 0 ? formatMoney(order.balance_due, order.currency) : 'Paid in full'}</b>
        </div>
      </div>

      {mode === 'view' && (
        <div className="order-actions">
          {canUpdate && next && (
            <button className="button button-primary" disabled={busy} onClick={advance}>
              {busy ? 'Saving…' : `Mark as ${next.label.toLowerCase()} →`}
            </button>
          )}
          {can('orders.payments') && order.status !== 'cancelled' && balance > 0 && (
            <button className={`button ${next ? 'button-secondary' : 'button-primary'}`} onClick={() => setMode('pay')}>
              Record payment
            </button>
          )}
          {canUpdate && (
            <button className="button button-secondary" onClick={() => setEditing(true)}>
              Edit details
            </button>
          )}
          {can('orders.update') && order.status !== 'cancelled' && (
            <button className="button button-ghost" onClick={() => setMode('status')}>
              Change status…
            </button>
          )}
          {can('orders.manage') && open && (
            <button className="button button-ghost text-danger" onClick={() => setMode('cancel')}>
              Cancel order
            </button>
          )}
        </div>
      )}
      {mode === 'pay' && <PayForm order={order} onBack={() => setMode('view')} onDone={(o, m) => done(o, m)} />}
      {mode === 'status' && <StatusForm order={order} onBack={() => setMode('view')} onDone={(o, m) => done(o, m)} />}
      {mode === 'cancel' && <CancelForm order={order} onBack={() => setMode('view')} onDone={(o, m) => done(o, m)} />}

      <Specification order={order} />

      {order.notes && (
        <>
          <h3 className="section-title">Notes</h3>
          <p className="order-notes">{order.notes}</p>
        </>
      )}

      <h3 className="section-title">Payments</h3>
      {order.payments.length === 0 ? (
        <p className="field-hint">No payments yet.</p>
      ) : (
        <ol className="timeline">
          {order.payments.map((p) => (
            <li key={`${p.id}-${p.amount}`} className={p.status === 'reversed' ? 'is-reversed' : ''}>
              <span className="delta delta-in">{formatMoney(p.amount, order.currency)}</span>
              <div>
                <b>
                  {p.number} · {p.method_label}
                  {p.reference && ` (${p.reference})`}
                </b>
                <small>
                  {formatDateTime(p.received_at)} · {p.created_by_name}
                </small>
                {p.status === 'reversed' && <small className="reversed-note">Reversed: {p.reversal_reason}</small>}
              </div>
            </li>
          ))}
        </ol>
      )}

      <div className="section-title-row">
        <h3 className="section-title">Materials used from stock</h3>
        {canUpdate && can('inventory.view') && mode !== 'material' && (
          <button className="button button-ghost" onClick={() => setMode('material')}>
            ＋ Use material
          </button>
        )}
      </div>
      {mode === 'material' && <MaterialForm order={order} onBack={() => setMode('view')} onDone={(o, m) => done(o, m)} />}
      {typeof mode === 'object' && (
        <ReturnMaterialForm order={order} materialId={mode.returning} onBack={() => setMode('view')} onDone={(o, m) => done(o, m)} />
      )}
      {order.materials.length === 0 ? (
        <p className="field-hint">None recorded. Orders only take stock when you record it here (e.g. blank shirts, paper, vinyl).</p>
      ) : (
        <table className="data-table compact">
          <thead>
            <tr>
              <th scope="col">Item</th>
              <th scope="col" className="num">
                Qty
              </th>
              {order.material_cost_base !== undefined && (
                <th scope="col" className="num">
                  Cost
                </th>
              )}
              <th scope="col">
                <span className="visually-hidden">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {order.materials.map((m) => (
              <tr key={m.id} className={m.returned ? 'is-inactive' : ''}>
                <td>
                  {m.description}
                  <small className="cell-sub">
                    {m.returned ? `Returned: ${m.reversal_reason}` : `${m.created_by_name} · ${formatDateTime(m.created_at)}`}
                    {m.note && ` · ${m.note}`}
                  </small>
                </td>
                <td className="num">{formatQuantity(m.quantity)}</td>
                {m.unit_cost_base !== undefined && (
                  <td className="num">{formatMoney(String(Number(m.quantity) * Number(m.unit_cost_base)), organization?.base_currency)}</td>
                )}
                <td className="cell-actions">
                  {!m.returned && open && can('orders.manage') && (
                    <button className="button button-ghost" onClick={() => setMode({ returning: m.id })}>
                      Return
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {order.material_cost_base !== undefined && Number(order.material_cost_base) > 0 && (
        <p className="field-hint">
          Material cost: <b>{formatMoney(order.material_cost_base, organization?.base_currency)}</b> (at weighted-average cost)
        </p>
      )}

      <h3 className="section-title">History</h3>
      <ol className="timeline">
        {[...order.history].reverse().map((h, i) => (
          <li key={i}>
            <span className={`history-dot ${h.correction ? 'is-correction' : ''}`} aria-hidden="true" />
            <div>
              <b>
                {h.from ? `${h.to_label}` : 'Order created'}
                {h.correction && <span className="badge">Correction</span>}
              </b>
              <small>
                {formatDateTime(h.at)} · {h.actor}
                {h.note && h.from && ` · ${h.note}`}
              </small>
            </div>
          </li>
        ))}
      </ol>

      <div className="dialog-actions">
        <button className="button button-secondary" onClick={onClose}>
          Close
        </button>
      </div>
    </Dialog>
  )
}

function Specification({ order }: { order: OrderDetail }) {
  const d = order.detail
  const rows: [string, string | number | null | undefined][] =
    order.kind === 'photography'
      ? [
          ['Shoot', [d.shoot_type, d.package].filter(Boolean).join(' · ')],
          ['When', d.shoot_at ? formatDateTime(String(d.shoot_at)) : null],
          ['Location', d.location],
          ['Photos promised', d.photos_promised],
        ]
      : order.kind === 'printing'
        ? [
            ['Item', d.item],
            ['Quantity', d.quantity ? formatQuantity(String(d.quantity)) : null],
            ['Size', d.size],
            ['Material', d.material],
            ['Design', d.design],
          ]
        : [
            ['Item', d.item],
            ['Colour', d.color],
            ['Design', d.design],
          ]
  return (
    <>
      <h3 className="section-title">Specification</h3>
      <dl className="spec-list">
        {rows
          .filter(([, v]) => v !== null && v !== undefined && v !== '')
          .map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        {order.production_cost && (
          <div>
            <dt>Production cost</dt>
            <dd>{formatMoney(order.production_cost, order.currency)}</dd>
          </div>
        )}
      </dl>
      {order.kind === 'clothing' && order.items.length > 0 && (
        <table className="data-table compact size-table">
          <thead>
            <tr>
              <th scope="col">Size</th>
              <th scope="col">Name</th>
              <th scope="col">No.</th>
              <th scope="col" className="num">
                Qty
              </th>
            </tr>
          </thead>
          <tbody>
            {order.items.map((item, i) => (
              <tr key={i}>
                <td>
                  <b>{item.size}</b>
                </td>
                <td>{item.custom_name || '—'}</td>
                <td>{item.custom_number || '—'}</td>
                <td className="num">{item.quantity}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={3}>Total pieces</td>
              <td className="num">
                <b>{order.items.reduce((n, i) => n + i.quantity, 0)}</b>
              </td>
            </tr>
          </tfoot>
        </table>
      )}
    </>
  )
}

interface SubFormProps {
  order: OrderDetail
  onBack: () => void
  onDone: (order: OrderDetail, message: string) => void
}

function PayForm({ order, onBack, onDone }: SubFormProps) {
  const [amount, setAmount] = useState(order.balance_due)
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [reference, setReference] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!(Number(amount) > 0) || Number(amount) > Number(order.balance_due)) {
      setFieldErrors({ amount: [`Enter up to ${formatMoney(order.balance_due, order.currency)}.`] })
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const next = await api.post<OrderDetail>(`/orders/${order.id}/pay/`, { amount, method, reference: reference.trim() }, idempotencyKey)
      onDone(next, `${formatMoney(amount, order.currency)} recorded on ${order.number}.`)
    } catch (err) {
      if (err instanceof ApiError)
        setFieldErrors(Object.fromEntries(Object.entries(err.fieldErrors).map(([k, v]) => [k.replace('payment.', ''), v])))
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
          label={`Amount (${order.currency})`}
          inputMode="decimal"
          autoFocus
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          error={fieldErrors.amount}
          hint={`${formatMoney(order.balance_due, order.currency)} due`}
        />
        <SelectField label="Method" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
          {PAYMENT_METHODS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectField>
      </div>
      {method !== 'cash' && (
        <TextField
          label="Reference (optional)"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          placeholder="Transaction ID"
        />
      )}
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

function StatusForm({ order, onBack, onDone }: SubFormProps) {
  const { can } = useAuth()
  const current = order.flow.findIndex((s) => s.code === order.status)
  const canCorrect = can('orders.manage')
  const choices = order.flow.filter((s, i) => s.code !== order.status && (i > current || canCorrect))
  const [status, setStatus] = useState(choices.find((_, i) => i >= current)?.code ?? choices[0]?.code ?? '')
  const [note, setNote] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const backwards = order.flow.findIndex((s) => s.code === status) < current

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (backwards && !note.trim()) {
      setFieldErrors({ note: ['Explain why the status is being corrected.'] })
      return
    }
    setSaving(true)
    setError(null)
    try {
      const next = await api.post<OrderDetail>(`/orders/${order.id}/status/`, { status, note: note.trim() })
      onDone(next, `${order.number}: ${next.status_label}${backwards ? ' (corrected)' : ''}.`)
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  if (!choices.length)
    return (
      <div className="reason-form">
        <p className="field-hint">No other status is available.</p>
        <button className="button button-secondary" onClick={onBack}>
          Back
        </button>
      </div>
    )
  return (
    <form className="reason-form" onSubmit={submit} noValidate>
      <ErrorBanner error={error} />
      <SelectField label="Move to" value={status} onChange={(e) => setStatus(e.target.value)} error={fieldErrors.status}>
        {choices.map((s) => (
          <option key={s.code} value={s.code}>
            {s.label}
            {order.flow.findIndex((f) => f.code === s.code) < current ? ' (correction)' : ''}
          </option>
        ))}
      </SelectField>
      <TextField
        label={backwards ? 'Reason for correction' : 'Note (optional)'}
        value={note}
        onChange={(e) => setNote(e.target.value)}
        error={fieldErrors.note}
        placeholder={backwards ? 'e.g. Client sent new artwork' : ''}
      />
      {!canCorrect && <p className="field-hint">Moving back to an earlier step needs a manager.</p>}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Update status'}
        </button>
      </div>
    </form>
  )
}

function CancelForm({ order, onBack, onDone }: SubFormProps) {
  const [reason, setReason] = useState('')
  const [fieldError, setFieldError] = useState<string[] | undefined>()
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const paid = Number(order.paid_amount) > 0

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!reason.trim()) {
      setFieldError(['A reason is required.'])
      return
    }
    setSaving(true)
    setError(null)
    try {
      onDone(await api.post<OrderDetail>(`/orders/${order.id}/cancel/`, { reason: reason.trim() }), `${order.number} cancelled.`)
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="reason-form" onSubmit={submit} noValidate>
      {paid ? (
        <p className="dialog-lead">
          {formatMoney(order.paid_amount, order.currency)} has been paid on this order. Refund it and reverse the payment from the
          customer's statement first; then the order can be cancelled.
        </p>
      ) : (
        <p className="dialog-lead">Cancelling closes {order.number}. It stays in the records with your reason.</p>
      )}
      <ErrorBanner error={error} />
      <TextField
        label="Reason"
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        error={fieldError}
        placeholder="e.g. Customer withdrew the job"
      />
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-danger" disabled={saving || paid}>
          {saving ? 'Saving…' : 'Cancel order'}
        </button>
      </div>
    </form>
  )
}

interface StockOption {
  variant_id: string
  label: string
  on_hand: string
}

function MaterialForm({ order, onBack, onDone }: SubFormProps) {
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<StockOption[]>([])
  const [chosen, setChosen] = useState<StockOption | null>(null)
  const [quantity, setQuantity] = useState('1')
  const [note, setNote] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const timer = window.setTimeout(
      () => {
        api
          .get<Page<StockOption>>('/stock/', { search: query.trim(), branch: order.branch, page_size: 8 })
          .then((page) => setOptions(page.results))
          .catch(() => setOptions([]))
      },
      query ? 250 : 0,
    )
    return () => window.clearTimeout(timer)
  }, [query, order.branch])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!chosen) {
      setFieldErrors({ variant: ['Choose the item taken from stock.'] })
      return
    }
    if (!(Number(quantity) > 0)) {
      setFieldErrors({ quantity: ['Enter a quantity greater than zero.'] })
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const next = await api.post<OrderDetail>(`/orders/${order.id}/materials/`, {
        variant: chosen.variant_id,
        quantity,
        note: note.trim(),
      })
      onDone(next, `${formatQuantity(quantity)} × ${chosen.label} taken from stock for ${order.number}.`)
    } catch (err) {
      if (err instanceof ApiError) {
        const errors = { ...err.fieldErrors }
        if (errors.quantity_delta) errors.quantity = errors.quantity_delta
        setFieldErrors(errors)
      }
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="reason-form" onSubmit={submit} noValidate>
      <ErrorBanner error={error} />
      {chosen ? (
        <div className="customer-chosen">
          <span>
            <small>Item</small>
            <b>{chosen.label}</b>
            <small>{formatQuantity(chosen.on_hand)} in stock</small>
          </span>
          <button type="button" className="button button-ghost" onClick={() => setChosen(null)}>
            Change
          </button>
        </div>
      ) : (
        <div className={`field ${fieldErrors.variant ? 'has-error' : ''}`}>
          <label htmlFor="material-search">Item from stock</label>
          <input
            id="material-search"
            type="search"
            autoFocus
            autoComplete="off"
            placeholder="Search stock"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          {fieldErrors.variant && <p className="field-error">{fieldErrors.variant.join(' ')}</p>}
          {options.length === 0 ? (
            <EmptyState title={query ? 'No matching stock' : 'No stocked items'} />
          ) : (
            <ul className="suggestions suggestions-static" role="listbox">
              {options.map((o) => (
                <li key={o.variant_id}>
                  <button type="button" disabled={Number(o.on_hand) <= 0} onClick={() => setChosen(o)}>
                    {o.label}
                    <small> · {Number(o.on_hand) > 0 ? `${formatQuantity(o.on_hand)} in stock` : 'out of stock'}</small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="field-row">
        <TextField
          label="Quantity used"
          inputMode="decimal"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          error={fieldErrors.quantity}
        />
        <TextField
          label="Note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="e.g. 2 spoiled in printing"
        />
      </div>
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Take from stock'}
        </button>
      </div>
    </form>
  )
}

function ReturnMaterialForm({ order, materialId, onBack, onDone }: SubFormProps & { materialId: string }) {
  const material = order.materials.find((m) => m.id === materialId)
  const [reason, setReason] = useState('')
  const [fieldError, setFieldError] = useState<string[] | undefined>()
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!reason.trim()) {
      setFieldError(['A reason is required.'])
      return
    }
    setSaving(true)
    setError(null)
    try {
      onDone(
        await api.post<OrderDetail>(`/orders/${order.id}/materials/${materialId}/return/`, { reason: reason.trim() }),
        `${material?.description ?? 'Material'} returned to stock.`,
      )
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="reason-form" onSubmit={submit} noValidate>
      <p className="dialog-lead">
        Put {material && formatQuantity(material.quantity)} × {material?.description} back into stock?
      </p>
      <ErrorBanner error={error} />
      <TextField
        label="Reason"
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        error={fieldError}
        placeholder="e.g. Not needed after all"
      />
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Return to stock'}
        </button>
      </div>
    </form>
  )
}
