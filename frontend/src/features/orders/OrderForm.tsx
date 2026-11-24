import { MenuSelect } from '../../components/MenuSelect'
import { useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { ErrorBanner, SelectField, TextAreaField, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors } from '../../lib/api'
import { formatMoney, newIdempotencyKey, todayIso } from '../../lib/format'
import type { Contact } from '../contacts/ContactsPage'
import { RateBanner } from '../currencies/ExchangeRate'
import { useDisplayCurrency } from '../currencies/DisplayCurrency'
import { useAuth } from '../identity/AuthContext'
import { CustomerPicker } from '../sales/Checkout'
import { PAYMENT_METHODS, type PaymentMethod } from '../sales/types'
import { KIND_LABEL, type ClothingLine, type OrderDetail, type OrderKind } from './types'

interface Staff {
  id: number
  name: string
}
type Spec = Record<string, string>

const SHOOT_TYPES = ['Wedding', 'Portrait', 'Birthday', 'Graduation', 'Event', 'Product', 'Family', 'Passport photos']
const SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', 'Kids']

function addDays(iso: string, days: number) {
  const [y, m, d] = iso.split('-').map(Number)
  const date = new Date(y, m - 1, d + days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function localDateTimeValue(iso: string | null | undefined) {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function specFrom(order: OrderDetail | null): Spec {
  if (!order) return {}
  const spec: Spec = {}
  for (const [key, value] of Object.entries(order.detail)) spec[key] = value === null || value === undefined ? '' : String(value)
  if (spec.shoot_at) spec.shoot_at = localDateTimeValue(spec.shoot_at)
  return spec
}

/** Create a new order, or edit an open one (price changes need orders.manage). */
/** Starting values for a new order, e.g. from a website request. */
export interface OrderPrefill {
  customer?: Contact
  title?: string
  notes?: string
  dueDate?: string
}

export function OrderFormDialog({
  order = null,
  defaultKind,
  prefill,
  onClose,
  onSaved,
}: {
  order?: OrderDetail | null
  defaultKind?: OrderKind
  prefill?: OrderPrefill
  onClose: () => void
  onSaved: (order: OrderDetail) => void
}) {
  const { sections, can } = useAuth()
  const { rates, reloadRates } = useDisplayCurrency()
  const orderSections = sections.filter((s) => s.code in KIND_LABEL)
  const editing = order !== null
  const [sectionId, setSectionId] = useState(
    order?.section ?? (orderSections.find((s) => s.code === defaultKind) ?? orderSections[0])?.id ?? '',
  )
  const kind = (order?.kind ?? orderSections.find((s) => s.id === sectionId)?.code) as OrderKind | undefined
  const [customer, setCustomer] = useState<Contact | null>(
    order
      ? { id: order.customer, name: order.customer_name, phone: order.customer_phone, email: '', notes: '', active: true }
      : (prefill?.customer ?? null),
  )
  const [spec, setSpec] = useState<Spec>(() => specFrom(order))
  const [items, setItems] = useState<ClothingLine[]>(
    order?.items.length ? order.items : [{ size: 'M', custom_name: '', custom_number: '', quantity: 1 }],
  )
  const [currency, setCurrency] = useState<'USD' | 'LRD'>((order?.currency as 'USD' | 'LRD') ?? 'USD')
  const [total, setTotal] = useState(order?.total ?? '')
  const [productionCost, setProductionCost] = useState(order?.production_cost ?? '')
  const [dueDate, setDueDate] = useState(order?.due_date ?? prefill?.dueDate ?? addDays(todayIso(), 7))
  const [title, setTitle] = useState(order?.title ?? prefill?.title ?? '')
  const [assignee, setAssignee] = useState<string>(order?.assigned_to ? String(order.assigned_to) : '')
  const [notes, setNotes] = useState(order?.notes ?? prefill?.notes ?? '')
  const [depositAmount, setDepositAmount] = useState('')
  const [depositMethod, setDepositMethod] = useState<PaymentMethod>('cash')
  const [depositReference, setDepositReference] = useState('')
  const [staff, setStaff] = useState<Staff[]>([])
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)

  useEffect(() => {
    if (!sectionId) return
    api
      .get<Staff[]>('/orders/staff/', { section: sectionId })
      .then(setStaff)
      .catch(() => setStaff([]))
  }, [sectionId])

  const set = (key: string) => (e: { target: { value: string } }) => setSpec((s) => ({ ...s, [key]: e.target.value }))
  const err = (key: string) => fieldErrors[`detail.${key}`]
  const canChangePrice = !editing || can('orders.manage')
  const lrdMissing = currency === 'LRD' && !rates?.rates.LRD
  const pieces = items.reduce((n, i) => n + (Number(i.quantity) || 0), 0)

  function updateItem(index: number, patch: Partial<ClothingLine>) {
    setItems((list) => list.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  function buildDetail(): Record<string, unknown> {
    if (kind === 'photography') {
      return {
        shoot_type: spec.shoot_type ?? '',
        package: spec.package ?? '',
        location: spec.location ?? '',
        shoot_at: spec.shoot_at ? new Date(spec.shoot_at).toISOString() : '',
        photos_promised: spec.photos_promised ? Number(spec.photos_promised) : null,
      }
    }
    if (kind === 'printing') {
      return {
        item: spec.item ?? '',
        quantity: spec.quantity || '1',
        size: spec.size ?? '',
        material: spec.material ?? '',
        design: spec.design ?? '',
      }
    }
    return { item: spec.item ?? '', color: spec.color ?? '', design: spec.design ?? '' }
  }

  function validate() {
    const errors: FieldErrors = {}
    if (!customer) errors.customer = ['Choose the customer.']
    if (total === '' || Number(total) < 0 || Number.isNaN(Number(total))) errors.total = ['Enter the agreed price.']
    if (!dueDate) errors.due_date = ['Choose a due date.']
    if (kind === 'photography') {
      if (!spec.shoot_type?.trim()) errors['detail.shoot_type'] = ['Enter the type of shoot.']
      if (!spec.shoot_at) errors['detail.shoot_at'] = ['Choose the shoot date and time.']
    } else if (!spec.item?.trim()) {
      errors['detail.item'] = [`Enter what is being ${kind === 'printing' ? 'printed' : 'made'}.`]
    }
    if (kind === 'clothing' && !items.some((i) => i.size.trim())) errors.items = ['Add at least one size line.']
    if (depositAmount && (Number(depositAmount) <= 0 || Number(depositAmount) > Number(total)))
      errors['deposit.amount'] = ['The deposit must be more than 0 and no more than the price.']
    return errors
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const errors = validate()
    setFieldErrors(errors)
    if (Object.keys(errors).length) return
    setSaving(true)
    setError(null)
    const body: Record<string, unknown> = {
      customer: customer!.id,
      due_date: dueDate,
      title: title.trim(),
      notes: notes.trim(),
      assigned_to: assignee ? Number(assignee) : null,
      production_cost: productionCost === '' ? null : productionCost,
      detail: buildDetail(),
    }
    if (kind === 'clothing') body.items = items.filter((i) => i.size.trim()).map((i) => ({ ...i, quantity: Number(i.quantity) || 1 }))
    if (canChangePrice) body.total = total
    try {
      let saved: OrderDetail
      if (editing) {
        saved = await api.patch<OrderDetail>(`/orders/${order.id}/`, body)
      } else {
        body.section = sectionId
        body.currency = currency
        if (depositAmount && Number(depositAmount) > 0)
          body.deposit = { amount: depositAmount, method: depositMethod, reference: depositReference.trim() }
        saved = await api.post<OrderDetail>('/orders/', body, idempotencyKey)
      }
      onSaved(saved)
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors)
      setError(e)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title={editing ? `Edit ${order.number}` : 'New order'} onClose={onClose} onSubmit={submit} wide>
      <ErrorBanner error={error} />
      {!editing && orderSections.length > 1 && (
        <div className="segmented-tabs segmented-full" role="radiogroup" aria-label="Department">
          {orderSections.map((s) => (
            <button
              key={s.id}
              type="button"
              role="radio"
              aria-checked={sectionId === s.id}
              className={sectionId === s.id ? 'active' : ''}
              onClick={() => {
                setSectionId(s.id)
                setAssignee('')
              }}
            >
              <span className={`kind-dot kind-${s.code}`} aria-hidden="true" />
              {KIND_LABEL[s.code as OrderKind]}
            </button>
          ))}
        </div>
      )}

      {editing ? (
        <div className="customer-chosen">
          <span>
            <small>Customer</small>
            <b>{order.customer_name}</b>
            {order.customer_phone && <small>{order.customer_phone}</small>}
          </span>
        </div>
      ) : (
        <CustomerPicker customer={customer} onChange={setCustomer} error={fieldErrors.customer} required />
      )}

      {kind === 'photography' && (
        <fieldset className="form-section">
          <legend>Shoot</legend>
          <div className="field-row">
            <TextField
              label="Type of shoot"
              list="shoot-types"
              value={spec.shoot_type ?? ''}
              onChange={set('shoot_type')}
              error={err('shoot_type')}
              placeholder="e.g. Wedding"
            />
            <datalist id="shoot-types">
              {SHOOT_TYPES.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
            <TextField
              label="Package (optional)"
              value={spec.package ?? ''}
              onChange={set('package')}
              error={err('package')}
              placeholder="e.g. Gold"
            />
          </div>
          <div className="field-row">
            <TextField
              label="Shoot date and time"
              type="datetime-local"
              value={spec.shoot_at ?? ''}
              error={err('shoot_at')}
              onChange={(e) => {
                const value = e.target.value
                setSpec((s) => ({ ...s, shoot_at: value }))
                if (!editing && value) setDueDate(addDays(value.slice(0, 10), 7))
              }}
            />
            <TextField
              label="Location (optional)"
              value={spec.location ?? ''}
              onChange={set('location')}
              placeholder="Studio, Sinkor, church…"
            />
          </div>
          <TextField
            label="Photos promised (optional)"
            inputMode="numeric"
            value={spec.photos_promised ?? ''}
            onChange={set('photos_promised')}
            error={err('photos_promised')}
          />
        </fieldset>
      )}

      {kind === 'printing' && (
        <fieldset className="form-section">
          <legend>Print job</legend>
          <div className="field-row">
            <TextField
              label="What is being printed"
              value={spec.item ?? ''}
              onChange={set('item')}
              error={err('item')}
              placeholder="e.g. Banner, flyers, business cards"
            />
            <TextField
              label="Quantity"
              inputMode="decimal"
              value={spec.quantity ?? '1'}
              onChange={set('quantity')}
              error={err('quantity')}
            />
          </div>
          <div className="field-row">
            <TextField label="Size (optional)" value={spec.size ?? ''} onChange={set('size')} placeholder="e.g. 3x6 ft, A5" />
            <TextField
              label="Material (optional)"
              value={spec.material ?? ''}
              onChange={set('material')}
              placeholder="e.g. Flex, gloss paper"
            />
          </div>
          <TextAreaField
            label="Design / specification"
            rows={3}
            value={spec.design ?? ''}
            onChange={set('design')}
            error={err('design')}
            placeholder="Wording, colours, artwork supplied by customer…"
          />
        </fieldset>
      )}

      {kind === 'clothing' && (
        <fieldset className="form-section">
          <legend>Garments</legend>
          <div className="field-row">
            <TextField
              label="Item"
              value={spec.item ?? ''}
              onChange={set('item')}
              error={err('item')}
              placeholder="e.g. Jersey, T-shirt, uniform"
            />
            <TextField label="Colour (optional)" value={spec.color ?? ''} onChange={set('color')} placeholder="e.g. Blue / white" />
          </div>
          <TextAreaField
            label="Design (optional)"
            rows={2}
            value={spec.design ?? ''}
            onChange={set('design')}
            placeholder="Crest, sponsor logo, print position…"
          />
          <div className={`size-lines ${fieldErrors.items ? 'has-error' : ''}`}>
            <div className="size-line size-line-head" aria-hidden="true">
              <span>Size</span>
              <span>Name on it</span>
              <span>No.</span>
              <span>Qty</span>
              <span />
            </div>
            {items.map((item, index) => (
              <div className="size-line" key={index}>
                <MenuSelect
                  variant="field"
                  aria-label={`Line ${index + 1} size`}
                  value={item.size}
                  onChange={(e) => updateItem(index, { size: e.target.value })}
                >
                  {[...new Set([...SIZES, item.size])].map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </MenuSelect>
                <input
                  aria-label={`Line ${index + 1} name`}
                  value={item.custom_name}
                  maxLength={40}
                  placeholder="Optional"
                  onChange={(e) => updateItem(index, { custom_name: e.target.value.toUpperCase() })}
                />
                <input
                  aria-label={`Line ${index + 1} number`}
                  value={item.custom_number}
                  maxLength={10}
                  inputMode="numeric"
                  onChange={(e) => updateItem(index, { custom_number: e.target.value })}
                />
                <input
                  aria-label={`Line ${index + 1} quantity`}
                  value={item.quantity}
                  inputMode="numeric"
                  onChange={(e) => updateItem(index, { quantity: Number(e.target.value.replace(/\D/g, '')) || 0 })}
                />
                <button
                  type="button"
                  className="button button-ghost icon-button"
                  aria-label={`Remove line ${index + 1}`}
                  disabled={items.length === 1}
                  onClick={() => setItems((list) => list.filter((_, i) => i !== index))}
                >
                  ×
                </button>
              </div>
            ))}
            {fieldErrors.items && <p className="field-error">{fieldErrors.items.join(' ')}</p>}
            <div className="size-lines-foot">
              <button
                type="button"
                className="button button-ghost"
                onClick={() =>
                  setItems((list) => [...list, { size: list.at(-1)?.size ?? 'M', custom_name: '', custom_number: '', quantity: 1 }])
                }
              >
                ＋ Add line
              </button>
              <span>
                {pieces} piece{pieces === 1 ? '' : 's'}
              </span>
            </div>
          </div>
        </fieldset>
      )}

      <fieldset className="form-section">
        <legend>Price and delivery</legend>
        {!editing && currency === 'LRD' && <RateBanner rates={rates} onChanged={reloadRates} />}
        <div className="field-row">
          {!editing && (
            <SelectField label="Currency" value={currency} onChange={(e) => setCurrency(e.target.value as 'USD' | 'LRD')}>
              <option value="USD">USD</option>
              <option value="LRD">LRD</option>
            </SelectField>
          )}
          <TextField
            label={`Agreed price (${currency})`}
            inputMode="decimal"
            value={total}
            onChange={(e) => setTotal(e.target.value)}
            error={fieldErrors.total}
            disabled={!canChangePrice}
            hint={
              !canChangePrice
                ? 'Only a manager can change the price.'
                : editing && Number(order.paid_amount) > 0
                  ? `${formatMoney(order.paid_amount, order.currency)} already paid`
                  : undefined
            }
          />
          <TextField
            label={`Production cost (optional)`}
            inputMode="decimal"
            value={productionCost}
            onChange={(e) => setProductionCost(e.target.value)}
            error={fieldErrors.production_cost}
            hint="Outside costs, e.g. printing bureau"
          />
        </div>
        <div className="field-row">
          <TextField
            label={kind === 'photography' ? 'Photos due by' : 'Due date'}
            type="date"
            min={editing ? undefined : todayIso()}
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            error={fieldErrors.due_date}
          />
          <SelectField
            label="Assigned to (optional)"
            value={assignee}
            onChange={(e) => setAssignee(e.target.value)}
            error={fieldErrors.assigned_to}
          >
            <option value="">Not assigned</option>
            {staff.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </SelectField>
        </div>
        <TextField
          label="Short title (optional)"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={160}
          hint="Shown in the order list. Left empty, it is made from the details above."
        />
        <TextAreaField label="Notes (optional)" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </fieldset>

      {!editing && can('orders.payments') && (
        <fieldset className="form-section">
          <legend>Deposit (optional)</legend>
          <div className="field-row">
            <TextField
              label={`Amount paid now (${currency})`}
              inputMode="decimal"
              value={depositAmount}
              onChange={(e) => setDepositAmount(e.target.value)}
              error={fieldErrors['deposit.amount']}
              placeholder="0.00"
            />
            <SelectField label="Method" value={depositMethod} onChange={(e) => setDepositMethod(e.target.value as PaymentMethod)}>
              {PAYMENT_METHODS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </SelectField>
          </div>
          {depositMethod !== 'cash' && Number(depositAmount) > 0 && (
            <TextField
              label="Reference (optional)"
              value={depositReference}
              onChange={(e) => setDepositReference(e.target.value)}
              placeholder="Transaction ID"
            />
          )}
          {Number(total) > 0 && Number(depositAmount) > 0 && Number(depositAmount) <= Number(total) && (
            <p className="field-hint">
              Balance after deposit: <b>{formatMoney(String(Number(total) - Number(depositAmount)), currency)}</b>
            </p>
          )}
        </fieldset>
      )}

      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving || (!editing && (lrdMissing || !kind))}>
          {saving ? 'Saving…' : editing ? 'Save changes' : 'Create order'}
        </button>
      </div>
    </Dialog>
  )
}
