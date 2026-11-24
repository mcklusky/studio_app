import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors } from '../../lib/api'
import { formatDateTime, formatMoney, newIdempotencyKey, todayIso } from '../../lib/format'
import { useAuth } from '../identity/AuthContext'
import { PAYMENT_METHODS, type PaymentMethod } from '../sales/types'
import type { Contact, ContactKind } from './ContactsPage'

interface OpenDocument {
  id: string
  number: string
  date: string
  currency: string
  total: string
  paid: string
  due: string
  status?: string
}
interface PaymentRow {
  id: string
  number: string
  status: 'posted' | 'reversed'
  method_label: string
  reference: string
  amount: string
  currency: string
  received_at?: string
  paid_on?: string
  created_by_name: string
  reversal_reason: string
  allocations: { number: string; amount: string }[]
}
interface Statement {
  balances: Record<string, string>
  open_documents: OpenDocument[]
  payments: PaymentRow[]
}

/** Balances shown per currency, e.g. "USD 20.00 · LRD 2,000.00". */
export function BalanceText({ balances }: { balances?: Record<string, string> }) {
  const entries = Object.entries(balances ?? {})
  if (!entries.length) return <span className="muted">—</span>
  return <b className="balance-text">{entries.map(([c, v]) => formatMoney(v, c)).join(' · ')}</b>
}

export function StatementDialog({
  kind,
  contact,
  onClose,
  onChanged,
}: {
  kind: ContactKind
  contact: Contact
  onClose: () => void
  onChanged: (message: string) => void
}) {
  const { can } = useAuth()
  const [statement, setStatement] = useState<Statement | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [paying, setPaying] = useState(false)
  const [reversing, setReversing] = useState<PaymentRow | null>(null)
  const money = kind.money!

  const load = useCallback(() => {
    api.get<Statement>(`${kind.endpoint}${contact.id}/statement/`).then(setStatement).catch(setError)
  }, [kind.endpoint, contact.id])
  useEffect(load, [load])

  const owed = statement ? Object.keys(statement.balances) : []

  return (
    <Dialog title={`${contact.name}: statement`} onClose={onClose} wide>
      <ErrorBanner error={error} />
      {!statement && !error && <p className="subheading">Loading…</p>}
      {statement && (
        <>
          <div className="statement-summary">
            <span>{kind.singular === 'customer' ? 'Owes you' : 'You owe'}</span>
            <BalanceText balances={statement.balances} />
          </div>

          {paying ? (
            <PaymentForm
              kind={kind}
              contact={contact}
              currencies={owed}
              documents={statement.open_documents}
              onBack={() => setPaying(false)}
              onDone={(message) => {
                setPaying(false)
                load()
                onChanged(message)
              }}
            />
          ) : reversing ? (
            <ReverseForm
              kind={kind}
              payment={reversing}
              onBack={() => setReversing(null)}
              onDone={(message) => {
                setReversing(null)
                load()
                onChanged(message)
              }}
            />
          ) : (
            <>
              <h3 className="section-title">Open {money.documentPlural}</h3>
              {statement.open_documents.length === 0 ? (
                <p className="field-hint">Nothing outstanding.</p>
              ) : (
                <table className="data-table compact">
                  <thead>
                    <tr>
                      <th scope="col">{money.documentLabel}</th>
                      <th scope="col" className="hide-mobile">
                        Date
                      </th>
                      <th scope="col" className="num">
                        Total
                      </th>
                      <th scope="col" className="num">
                        Due
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {statement.open_documents.map((d) => (
                      <tr key={d.id}>
                        <td>
                          <b>{d.number}</b>
                          {d.status && <small className="cell-sub">{d.status}</small>}
                        </td>
                        <td className="hide-mobile">{d.date}</td>
                        <td className="num">{formatMoney(d.total, d.currency)}</td>
                        <td className="num">
                          <b>{formatMoney(d.due, d.currency)}</b>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              <h3 className="section-title">Payments</h3>
              {statement.payments.length === 0 ? (
                <EmptyState title="No payments recorded yet" />
              ) : (
                <ol className="timeline">
                  {statement.payments.map((p) => (
                    <li key={p.id} className={p.status === 'reversed' ? 'is-reversed' : ''}>
                      <span className="delta delta-in">{formatMoney(p.amount, p.currency)}</span>
                      <div>
                        <b>
                          {p.number} · {p.method_label}
                          {p.reference && ` (${p.reference})`}
                        </b>
                        <small>
                          {p.received_at ? formatDateTime(p.received_at) : p.paid_on} · {p.created_by_name} · for{' '}
                          {p.allocations.map((a) => `${a.number} (${formatMoney(a.amount, p.currency)})`).join(', ')}
                        </small>
                        {p.status === 'reversed' && <small className="reversed-note">Reversed: {p.reversal_reason}</small>}
                      </div>
                      {p.status === 'posted' && can(money.reversePermission) && (
                        <button className="button button-ghost" onClick={() => setReversing(p)}>
                          Reverse
                        </button>
                      )}
                    </li>
                  ))}
                </ol>
              )}

              <div className="dialog-actions">
                <button className="button button-secondary" onClick={onClose}>
                  Close
                </button>
                {owed.length > 0 && can(money.payPermission) && (
                  <button className="button button-primary" onClick={() => setPaying(true)}>
                    {money.payLabel}
                  </button>
                )}
              </div>
            </>
          )}
        </>
      )}
    </Dialog>
  )
}

function PaymentForm({
  kind,
  contact,
  currencies,
  documents,
  onBack,
  onDone,
}: {
  kind: ContactKind
  contact: Contact
  currencies: string[]
  documents: OpenDocument[]
  onBack: () => void
  onDone: (message: string) => void
}) {
  const money = kind.money!
  const [currency, setCurrency] = useState(currencies[0])
  const openInCurrency = documents.filter((d) => d.currency === currency)
  const totalDue = openInCurrency.reduce((sum, d) => sum + Number(d.due), 0)
  const [amount, setAmount] = useState(totalDue.toFixed(2))
  const [method, setMethod] = useState<PaymentMethod>(kind.singular === 'customer' ? 'cash' : 'bank_transfer')
  const [reference, setReference] = useState('')
  const [paidOn, setPaidOn] = useState(todayIso())
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)

  // Preview of the oldest-first split the server will apply.
  const split = openInCurrency.reduce<{ left: number; rows: (OpenDocument & { take: number })[] }>(
    (acc, d) => {
      const take = Math.min(acc.left, Number(d.due))
      return { left: acc.left - take, rows: take > 0 ? [...acc.rows, { ...d, take }] : acc.rows }
    },
    { left: Number(amount) || 0, rows: [] },
  ).rows

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!(Number(amount) > 0) || Number(amount) > totalDue + 0.0001) {
      setFieldErrors({ amount: [`Enter up to ${formatMoney(String(totalDue), currency)}.`] })
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const body: Record<string, unknown> = {
        [money.ownerField]: contact.id,
        currency,
        amount,
        method,
        reference: reference.trim(),
      }
      if (kind.singular === 'supplier') body.paid_on = paidOn
      const payment = await api.post<{ number: string }>(money.paymentEndpoint, body, idempotencyKey)
      onDone(`${payment.number}: ${formatMoney(amount, currency)} recorded for ${contact.name}.`)
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={submit} noValidate>
      <ErrorBanner error={error} />
      <div className="field-row">
        {currencies.length > 1 && (
          <SelectField
            label="Currency"
            value={currency}
            onChange={(e) => {
              setCurrency(e.target.value)
              setAmount(
                documents
                  .filter((d) => d.currency === e.target.value)
                  .reduce((s, d) => s + Number(d.due), 0)
                  .toFixed(2),
              )
            }}
          >
            {currencies.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </SelectField>
        )}
        <TextField
          label={`Amount (${currency})`}
          inputMode="decimal"
          autoFocus
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          error={fieldErrors.amount}
          hint={`${formatMoney(String(totalDue), currency)} due in ${currency}`}
        />
      </div>
      <div className="field-row">
        <SelectField label="Method" value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)}>
          {PAYMENT_METHODS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Reference (optional)"
          value={reference}
          onChange={(e) => setReference(e.target.value)}
          placeholder="Transaction ID"
        />
      </div>
      {kind.singular === 'supplier' && (
        <TextField
          label="Paid on"
          type="date"
          max={todayIso()}
          value={paidOn}
          onChange={(e) => setPaidOn(e.target.value)}
          error={fieldErrors.paid_on}
        />
      )}
      {split.length > 0 && (
        <p className="field-hint">
          Applied oldest first: {split.map((d) => `${d.number} ${formatMoney(String(d.take), currency)}`).join(' · ')}
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : money.payLabel}
        </button>
      </div>
    </form>
  )
}

function ReverseForm({
  kind,
  payment,
  onBack,
  onDone,
}: {
  kind: ContactKind
  payment: PaymentRow
  onBack: () => void
  onDone: (m: string) => void
}) {
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
      await api.post(`${kind.money!.paymentEndpoint}${payment.id}/reverse/`, { reason: reason.trim() })
      onDone(`${payment.number} reversed. The balance it paid is open again.`)
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="reason-form" onSubmit={submit} noValidate>
      <p className="dialog-lead">
        Reverse {payment.number} ({formatMoney(payment.amount, payment.currency)})? The {kind.money!.documentPlural} it paid will show as
        owing again.
      </p>
      <ErrorBanner error={error} />
      <TextField
        label="Reason"
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        error={fieldError}
        placeholder="e.g. Transfer was recalled"
      />
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-danger" disabled={saving}>
          {saving ? 'Saving…' : 'Reverse payment'}
        </button>
      </div>
    </form>
  )
}
