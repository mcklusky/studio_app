import { Lead, StatusBadge, TableSkeleton } from '../../components/Feedback'
import { Banknote, FileDown, ReceiptText, Undo2 } from 'lucide-react'
import './sales.css'
import { ANY_DATE, DateRangeFilter, rangeParams } from '../../components/DateRangeFilter'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextField } from '../../components/Form'
import { ActionsHeader, actionColumns, RowActions } from '../../components/RowActions'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { formatDateTime, formatMoney, newIdempotencyKey } from '../../lib/format'
import { CurrencySwitch, TxnAmount } from '../currencies/DisplayCurrency'
import { useAuth } from '../identity/AuthContext'
import { Checkout } from './Checkout'
import { Receipt, ReceiptActions } from './Receipt'
import { PAYMENT_METHODS, type PaymentMethod, type SaleDetail, type SaleSummary } from './types'
import type { Focus } from '../../app/focus'

const TABS: [string, string][] = [
  ['', 'All'],
  ['unpaid', 'Balance due'],
  ['reversed', 'Reversed'],
]

export function SalesPage({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { can, focus: viewFocus } = useAuth()
  const actionCols = actionColumns('Receipt', can('sales.create') && 'Payment', can('sales.reverse') && 'Reverse')
  const [mode, setMode] = useState<'list' | 'checkout'>('list')
  const [completed, setCompleted] = useState<SaleDetail | null>(null)
  const [tab, setTab] = useState('')
  const [query, setQuery] = useState(focus?.query ?? '')
  const [page, setPage] = useState(1)
  const [range, setRange] = useState(ANY_DATE)
  const [data, setData] = useState<Page<SaleSummary> | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [openId, setOpenId] = useState<string | null>(focus?.id ?? null)
  const [openMode, setOpenMode] = useState<SaleMode>('view')
  const openSale = (id: string, mode: SaleMode = 'view') => {
    setOpenMode(mode)
    setOpenId(id)
  }

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setData(
        await api.get<Page<SaleSummary>>('/sales/', {
          search: query,
          page,
          unpaid: tab === 'unpaid' ? 'true' : undefined,
          status: tab === 'reversed' ? 'reversed' : undefined,
          ...rangeParams(range),
        }),
      )
    } catch (err) {
      setLoadError(err)
    }
  }, [query, page, tab, range])

  useEffect(() => {
    if (mode !== 'list') return
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query, mode])

  if (mode === 'checkout') {
    return (
      <Checkout
        onCancel={() => setMode('list')}
        onComplete={(sale) => {
          setCompleted(sale)
          setMode('list')
        }}
      />
    )
  }

  if (completed) {
    return (
      <div className="page sale-done">
        <div className="sale-done-banner" role="status">
          <span className="sale-done-icon" aria-hidden="true">
            ✓
          </span>
          <div>
            <h1>Sale complete</h1>
            <p className="subheading">
              {completed.number} · {formatMoney(completed.total, completed.currency)}
              {Number(completed.balance_due) > 0 && (
                <>
                  {' '}
                  · <b>{formatMoney(completed.balance_due, completed.currency)} still due</b>
                </>
              )}
            </p>
          </div>
        </div>
        {completed.payments.some((p) => p.change && Number(p.change) > 0) && (
          <p className="change-due change-due-large">
            Give change: <b>{formatMoney(completed.payments.find((p) => p.change)?.change, completed.currency)}</b>
          </p>
        )}
        <ReceiptActions sale={completed} />
        <Receipt sale={completed} />
        <div className="dialog-actions sale-done-actions">
          <button className="button button-secondary" onClick={() => setCompleted(null)}>
            Back to sales
          </button>
          <button
            className="button button-primary"
            onClick={() => {
              setCompleted(null)
              setMode('checkout')
            }}
          >
            ＋ Next sale
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">WORKSPACE</p>
          <h1>Sales</h1>
          <p className="subheading">{data ? `${data.count} sales` : 'Loading…'}</p>
        </div>
        <CurrencySwitch />
        {can('sales.create') && (
          <button className="button button-primary button-large" onClick={() => setMode('checkout')}>
            ＋ New sale
          </button>
        )}
      </div>

      <div className="segmented-tabs" role="tablist" aria-label="Sale filter">
        {TABS.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? 'active' : ''}
            onClick={() => {
              setTab(value)
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
          placeholder="Search receipt number, customer or phone"
          aria-label="Search sales"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        <DateRangeFilter
          label="Sale date"
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
          icon={ReceiptText}
          title={tab || query || range.choice !== 'any' || viewFocus.section || viewFocus.branch ? 'No sales match' : 'No sales yet'}
        >
          {!tab && !query && range.choice === 'any' && !viewFocus.section && !viewFocus.branch && can('sales.create') && (
            <button className="button button-primary" onClick={() => setMode('checkout')}>
              Record the first sale
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
                <th scope="col">Sale</th>
                <th scope="col" className="hide-mobile">
                  When
                </th>
                <th scope="col">Status</th>
                <th scope="col" className="num">
                  Total
                </th>
                <ActionsHeader />
              </tr>
            </thead>
            <tbody>
              {data.results.map((s) => (
                <tr key={s.id} onClick={() => openSale(s.id)}>
                  <td>
                    <Lead icon={ReceiptText} tone={s.status === 'reversed' ? 'neutral' : Number(s.balance_due) > 0 ? 'amber' : 'green'}>
                      <button
                        className="link-button"
                        onClick={(e) => {
                          e.stopPropagation()
                          openSale(s.id)
                        }}
                      >
                        {s.number}
                      </button>
                      <small className="cell-sub">
                        {s.customer_name} · {s.section_name}
                      </small>
                    </Lead>
                  </td>
                  <td className="hide-mobile">
                    {formatDateTime(s.posted_at)}
                    <small className="cell-sub">{s.created_by_name}</small>
                  </td>
                  <td>
                    <SaleStatus sale={s} />
                  </td>
                  <td className="num">
                    <TxnAmount amount={s.total} currency={s.currency} baseAmount={s.base_total} />
                  </td>
                  <RowActions
                    label={`Actions for ${s.number}`}
                    columns={actionCols}
                    actions={{
                      Receipt: {
                        label: 'Download receipt',
                        icon: FileDown,
                        tone: 'blue',
                        onClick: () =>
                          void api.download(`/sales/${s.id}/receipt/`).catch(() => notify('The receipt could not be downloaded.')),
                      },
                      Payment: s.status === 'posted' &&
                        Number(s.balance_due) > 0 && {
                          label: 'Take payment',
                          icon: Banknote,
                          tone: 'green',
                          onClick: () => openSale(s.id, 'pay'),
                        },
                      Reverse: s.status === 'posted' && {
                        label: 'Reverse sale',
                        icon: Undo2,
                        tone: 'red',
                        onClick: () => openSale(s.id, 'reverse'),
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

      {openId && (
        <SaleDetailDialog
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

function SaleStatus({ sale }: { sale: SaleSummary }) {
  if (sale.status === 'reversed') return <StatusBadge tone="muted">Reversed</StatusBadge>
  if (Number(sale.balance_due) > 0) return <StatusBadge tone="low">{formatMoney(sale.balance_due, sale.currency)} due</StatusBadge>
  return <StatusBadge tone="ok">Paid</StatusBadge>
}

type SaleMode = 'view' | 'pay' | 'reverse'

function SaleDetailDialog({
  id,
  initialMode = 'view',
  onClose,
  onChanged,
}: {
  id: string
  initialMode?: SaleMode
  onClose: () => void
  onChanged: (message: string) => void
}) {
  const { can, organization } = useAuth()
  const [sale, setSale] = useState<SaleDetail | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [mode, setMode] = useState<SaleMode>(initialMode)

  useEffect(() => {
    api.get<SaleDetail>(`/sales/${id}/`).then(setSale).catch(setError)
  }, [id])

  if (!sale)
    return (
      <Dialog title="Sale" onClose={onClose} wide>
        <ErrorBanner error={error} />
        {!error && <p className="subheading">Loading…</p>}
      </Dialog>
    )

  const done = (next: SaleDetail, message: string) => {
    setSale(next)
    setMode('view')
    onChanged(message)
  }
  const canPay = can('sales.create') && sale.status === 'posted' && Number(sale.balance_due) > 0
  const canReverse = can('sales.reverse') && sale.status === 'posted'

  return (
    <Dialog title={`${sale.number} · ${sale.customer_name}`} onClose={onClose} wide>
      {sale.status === 'reversed' && (
        <div className="error-banner">
          Reversed by {sale.reversed_by_name} on {formatDateTime(sale.reversed_at!)}: {sale.reversal_reason}. Stock was returned and
          payments refunded.
        </div>
      )}
      {sale.gross_profit_base && (
        <p className="dialog-lead">
          Gross profit ≈ {formatMoney(sale.gross_profit_base, organization?.base_currency)} (at weighted-average cost)
        </p>
      )}
      {mode === 'pay' && (
        <PaymentForm sale={sale} onBack={() => setMode('view')} onDone={(next) => done(next, `Payment recorded on ${next.number}.`)} />
      )}
      {mode === 'reverse' && (
        <ReverseForm sale={sale} onBack={() => setMode('view')} onDone={(next) => done(next, `${next.number} reversed. Stock returned.`)} />
      )}
      <ReceiptActions sale={sale} />
      <Receipt sale={sale} />

      {mode === 'view' && (
        <div className="dialog-actions">
          {canReverse && (
            <button className="button button-secondary" onClick={() => setMode('reverse')}>
              Reverse sale
            </button>
          )}
          <button className="button button-secondary" onClick={onClose}>
            Close
          </button>
          {canPay && (
            <button className="button button-primary" onClick={() => setMode('pay')}>
              Record payment
            </button>
          )}
        </div>
      )}
    </Dialog>
  )
}

function PaymentForm({ sale, onBack, onDone }: { sale: SaleDetail; onBack: () => void; onDone: (s: SaleDetail) => void }) {
  const [amount, setAmount] = useState(sale.balance_due)
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [reference, setReference] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!(Number(amount) > 0) || Number(amount) > Number(sale.balance_due)) {
      setFieldErrors({ amount: [`Enter up to ${formatMoney(sale.balance_due, sale.currency)}.`] })
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      onDone(await api.post<SaleDetail>(`/sales/${sale.id}/payments/`, { amount, method, reference: reference.trim() }, idempotencyKey))
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
          label={`Amount (${sale.currency})`}
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
      {method !== 'cash' && <TextField label="Reference (optional)" value={reference} onChange={(e) => setReference(e.target.value)} />}
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

function ReverseForm({ sale, onBack, onDone }: { sale: SaleDetail; onBack: () => void; onDone: (s: SaleDetail) => void }) {
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
      onDone(await api.post<SaleDetail>(`/sales/${sale.id}/reverse/`, { reason: reason.trim() }))
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="reason-form" onSubmit={submit} noValidate>
      <p className="dialog-lead">
        Reversing returns all items to stock and marks {formatMoney(sale.paid_amount, sale.currency)} of payments as refunded. Make sure the
        money has been given back.
      </p>
      <ErrorBanner error={error} />
      <TextField
        label="Reason"
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        error={fieldError}
        placeholder="e.g. Customer returned items"
      />
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onBack}>
          Back
        </button>
        <button type="submit" className="button button-danger" disabled={saving}>
          {saving ? 'Saving…' : 'Reverse sale'}
        </button>
      </div>
    </form>
  )
}
