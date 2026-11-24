import { MenuSelect } from '../../components/MenuSelect'
import { Tags, Undo2, Wallet } from 'lucide-react'
import { Lead, TableSkeleton } from '../../components/Feedback'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Attachments, PendingFilePicker, RECEIPT_ACCEPT, uploadAttachment } from '../../components/Attachments'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextField } from '../../components/Form'
import { ActionsHeader, actionColumns, RowActions } from '../../components/RowActions'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { formatDateTime, formatMoney, newIdempotencyKey, todayIso } from '../../lib/format'
import { CurrencySwitch, TxnAmount, useDisplayCurrency } from '../currencies/DisplayCurrency'
import { RateBanner } from '../currencies/ExchangeRate'
import { useAuth } from '../identity/AuthContext'
import { PAYMENT_METHODS, type PaymentMethod } from '../sales/types'
import type { Focus } from '../../app/focus'

interface Category {
  id: string
  name: string
  active: boolean
}
interface Expense {
  id: string
  number: string
  status: 'posted' | 'reversed'
  category_name: string
  section_name: string
  expense_date: string
  description: string
  method_label: string
  reference: string
  amount: string
  currency: string
  fx_units_per_usd: string
  base_amount: string
  recorded_by_name: string
  created_at: string
  reversed_at: string | null
  reversed_by_name: string | null
  reversal_reason: string
}
interface ExpensePage extends Page<Expense> {
  totals: { by_currency: Record<string, string>; base_total: string }
}

function monthRange(offset: number) {
  const now = new Date()
  const start = new Date(now.getFullYear(), now.getMonth() + offset, 1)
  const end = new Date(now.getFullYear(), now.getMonth() + offset + 1, 0)
  const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  return { from: iso(start), to: iso(end) }
}

const PERIODS: [string, string][] = [
  ['this', 'This month'],
  ['last', 'Last month'],
  ['all', 'All time'],
]

export function ExpensesPage({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { can } = useAuth()
  const { base } = useDisplayCurrency()
  const actionCols = actionColumns(can('expenses.manage') && 'Reverse')
  const [period, setPeriod] = useState(focus?.query ? 'all' : 'this')
  const [category, setCategory] = useState('')
  const [query, setQuery] = useState(focus?.query ?? '')
  const [page, setPage] = useState(1)
  const [categories, setCategories] = useState<Category[]>([])
  const [data, setData] = useState<ExpensePage | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [creating, setCreating] = useState(false)
  const [open, setOpen] = useState<Expense | null>(null)
  const [openReversing, setOpenReversing] = useState(false)
  const openExpense = (expense: Expense, reversing = false) => {
    setOpenReversing(reversing)
    setOpen(expense)
  }

  const loadCategories = useCallback(() => {
    api
      .get<Page<Category>>('/expense-categories/', { page_size: 200 })
      .then((p) => setCategories(p.results))
      .catch(() => undefined)
  }, [])
  useEffect(loadCategories, [loadCategories])

  const load = useCallback(async () => {
    setLoadError(null)
    const range = period === 'all' ? {} : monthRange(period === 'this' ? 0 : -1)
    try {
      setData(await api.get<ExpensePage>('/expenses/', { ...range, category, search: query, page }))
    } catch (err) {
      setLoadError(err)
    }
  }, [period, category, query, page])

  useEffect(() => {
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  const byCurrency = Object.entries(data?.totals.by_currency ?? {})

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">MANAGE</p>
          <h1>Expenses</h1>
          <p className="subheading">
            {data ? (
              <>
                Total <b>{base(data.totals.base_total)}</b>
                {byCurrency.length > 0 && <> · recorded as {byCurrency.map(([c, v]) => formatMoney(v, c)).join(' + ')}</>}
              </>
            ) : (
              'Loading…'
            )}
          </p>
        </div>
        <CurrencySwitch />
        {can('expenses.create') && (
          <button className="button button-primary" onClick={() => setCreating(true)}>
            ＋ Record expense
          </button>
        )}
      </div>

      <div className="segmented-tabs" role="tablist" aria-label="Period">
        {PERIODS.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={period === value}
            className={period === value ? 'active' : ''}
            onClick={() => {
              setPeriod(value)
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
          placeholder="Search description, number or reference"
          aria-label="Search expenses"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        {categories.length > 0 && (
          <MenuSelect
            variant="pill"
            icon={Tags}
            className="toolbar-select"
            aria-label="Category"
            value={category}
            onChange={(e) => {
              setCategory(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </MenuSelect>
        )}
      </div>
      <ErrorBanner error={loadError} />

      {data && data.results.length === 0 ? (
        <EmptyState icon={Wallet} title={query || category || period !== 'all' ? 'No expenses in this view' : 'No expenses recorded yet'}>
          {can('expenses.create') && (
            <button className="button button-secondary" onClick={() => setCreating(true)}>
              Record an expense
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
                <th scope="col">Expense</th>
                <th scope="col" className="hide-mobile">
                  Date
                </th>
                <th scope="col" className="hide-mobile">
                  Paid by
                </th>
                <th scope="col" className="num">
                  Amount
                </th>
                <ActionsHeader />
              </tr>
            </thead>
            <tbody>
              {data.results.map((e) => (
                <tr key={e.id} onClick={() => openExpense(e)} className={e.status === 'reversed' ? 'is-inactive' : ''}>
                  <td>
                    <Lead icon={Wallet} tone={e.status === 'reversed' ? 'neutral' : 'violet'}>
                      <button
                        className="link-button"
                        onClick={(ev) => {
                          ev.stopPropagation()
                          openExpense(e)
                        }}
                      >
                        {e.description}
                      </button>
                      {e.status === 'reversed' && <span className="badge">Reversed</span>}
                      <small className="cell-sub">
                        {e.number} · {e.category_name} · {e.section_name}
                      </small>
                    </Lead>
                  </td>
                  <td className="hide-mobile">{e.expense_date}</td>
                  <td className="hide-mobile">{e.method_label}</td>
                  <td className="num">
                    <TxnAmount amount={e.amount} currency={e.currency} baseAmount={e.base_amount} />
                  </td>
                  <RowActions
                    label={`Actions for ${e.number}`}
                    columns={actionCols}
                    actions={{
                      Reverse: e.status === 'posted' && {
                        label: 'Reverse expense',
                        icon: Undo2,
                        tone: 'red',
                        onClick: () => openExpense(e, true),
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
        <ExpenseDialog
          categories={categories}
          onCategoryAdded={loadCategories}
          onClose={() => setCreating(false)}
          onSaved={(expense, note) => {
            setCreating(false)
            notify(`${expense.number} recorded: ${formatMoney(expense.amount, expense.currency)}.${note ? ` ${note}` : ''}`)
            void load()
          }}
        />
      )}
      {open && (
        <ExpenseDetail
          expense={open}
          startReversing={openReversing}
          onClose={() => setOpen(null)}
          onReversed={(expense) => {
            setOpen(null)
            notify(`${expense.number} reversed.`)
            void load()
          }}
        />
      )}
    </div>
  )
}

function ExpenseDialog({
  categories,
  onCategoryAdded,
  onClose,
  onSaved,
}: {
  categories: Category[]
  onCategoryAdded: () => void
  onClose: () => void
  onSaved: (expense: Expense, note?: string) => void
}) {
  const { sections, can } = useAuth()
  const { rates, reloadRates } = useDisplayCurrency()
  const active = categories.filter((c) => c.active)
  const [receipt, setReceipt] = useState<File | null>(null)
  const [form, setForm] = useState({
    category: active.length === 1 ? active[0].id : '',
    section: sections.length === 1 ? sections[0].id : '',
    expense_date: todayIso(),
    description: '',
    amount: '',
    currency: 'LRD',
    method: 'cash' as PaymentMethod,
    reference: '',
  })
  const [newCategory, setNewCategory] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const lrdMissing = form.currency === 'LRD' && !rates?.rates.LRD

  async function addCategory() {
    if (!newCategory?.trim()) return
    try {
      const created = await api.post<Category>('/expense-categories/', { name: newCategory.trim() })
      onCategoryAdded()
      setForm((f) => ({ ...f, category: created.id }))
      setNewCategory(null)
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors({ category: err.fieldErrors.name ?? [err.message] })
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    if (!form.category) errors.category = ['Choose a category.']
    if (!form.section) errors.section = ['Choose a section.']
    if (!form.description.trim()) errors.description = ['Describe what this was for.']
    if (!(Number(form.amount) > 0)) errors.amount = ['Enter an amount greater than zero.']
    if (Object.keys(errors).length) {
      setFieldErrors(errors)
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const expense = await api.post<Expense>(
        '/expenses/',
        { ...form, description: form.description.trim(), reference: form.reference.trim() },
        idempotencyKey,
      )
      let note: string | undefined
      if (receipt) {
        try {
          await uploadAttachment('expense_receipt', expense.id, receipt)
          note = 'Receipt photo attached.'
        } catch {
          note = 'The receipt photo did not upload; open the expense to try again.'
        }
      }
      onSaved(expense, note)
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title="Record expense" onClose={onClose} onSubmit={submit}>
      <ErrorBanner error={error} />
      {form.currency === 'LRD' && <RateBanner rates={rates} onChanged={reloadRates} />}
      {newCategory === null ? (
        <div className="field-row field-row-end">
          <SelectField label="Category" value={form.category} onChange={set('category')} error={fieldErrors.category}>
            <option value="">Choose…</option>
            {active.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </SelectField>
          {can('expenses.create') && (
            <button type="button" className="button button-secondary add-variant" onClick={() => setNewCategory('')}>
              ＋ New
            </button>
          )}
        </div>
      ) : (
        <div className="field-row field-row-end">
          <TextField
            label="New category name"
            autoFocus
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            error={fieldErrors.category}
            placeholder="e.g. Rent, Electricity, Fuel, Salaries"
          />
          <button type="button" className="button button-primary add-variant" onClick={addCategory}>
            Add
          </button>
          <button type="button" className="button button-ghost add-variant" onClick={() => setNewCategory(null)}>
            Cancel
          </button>
        </div>
      )}
      <TextField
        label="What was it for?"
        value={form.description}
        onChange={set('description')}
        error={fieldErrors.description}
        placeholder="e.g. Generator fuel, 20 litres"
      />
      <div className="field-row">
        <TextField
          label={`Amount (${form.currency})`}
          inputMode="decimal"
          value={form.amount}
          onChange={set('amount')}
          error={fieldErrors.amount}
        />
        <SelectField label="Currency" value={form.currency} onChange={set('currency')} error={fieldErrors.currency}>
          <option value="LRD">LRD</option>
          <option value="USD">USD</option>
        </SelectField>
      </div>
      <div className="field-row">
        <SelectField
          label="Section"
          value={form.section}
          onChange={set('section')}
          error={fieldErrors.section}
          hint="Which business this cost belongs to."
        >
          <option value="">Choose…</option>
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Date"
          type="date"
          max={todayIso()}
          value={form.expense_date}
          onChange={set('expense_date')}
          error={fieldErrors.expense_date}
        />
      </div>
      <div className="field-row">
        <SelectField label="Paid by" value={form.method} onChange={set('method')}>
          {PAYMENT_METHODS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </SelectField>
        <TextField
          label="Receipt / reference (optional)"
          value={form.reference}
          onChange={set('reference')}
          error={fieldErrors.reference}
        />
      </div>
      <PendingFilePicker label="Receipt photo (optional)" accept={RECEIPT_ACCEPT} file={receipt} onChange={setReceipt} />
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving || lrdMissing}>
          {saving ? 'Saving…' : 'Record expense'}
        </button>
      </div>
    </Dialog>
  )
}

function ExpenseDetail({
  expense,
  startReversing = false,
  onClose,
  onReversed,
}: {
  expense: Expense
  startReversing?: boolean
  onClose: () => void
  onReversed: (e: Expense) => void
}) {
  const { can } = useAuth()
  const [reversing, setReversing] = useState(startReversing)
  const [reason, setReason] = useState('')
  const [fieldError, setFieldError] = useState<string[] | undefined>()
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  async function reverse(event: FormEvent) {
    event.preventDefault()
    if (!reason.trim()) {
      setFieldError(['A reason is required.'])
      return
    }
    setSaving(true)
    setError(null)
    try {
      onReversed(await api.post<Expense>(`/expenses/${expense.id}/reverse/`, { reason: reason.trim() }))
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title={`${expense.number} · ${expense.description}`} onClose={onClose}>
      {expense.status === 'reversed' && (
        <div className="error-banner">
          Reversed by {expense.reversed_by_name} on {formatDateTime(expense.reversed_at!)}: {expense.reversal_reason}
        </div>
      )}
      <dl className="detail-list">
        <div>
          <dt>Amount</dt>
          <dd>
            <b>{formatMoney(expense.amount, expense.currency)}</b>
            {expense.currency !== 'USD' && (
              <>
                {' '}
                (≈ {formatMoney(expense.base_amount, 'USD')} at {Number(expense.fx_units_per_usd)})
              </>
            )}
          </dd>
        </div>
        <div>
          <dt>Category</dt>
          <dd>{expense.category_name}</dd>
        </div>
        <div>
          <dt>Section</dt>
          <dd>{expense.section_name}</dd>
        </div>
        <div>
          <dt>Date</dt>
          <dd>{expense.expense_date}</dd>
        </div>
        <div>
          <dt>Paid by</dt>
          <dd>
            {expense.method_label}
            {expense.reference && ` · ${expense.reference}`}
          </dd>
        </div>
        <div>
          <dt>Recorded</dt>
          <dd>
            {expense.recorded_by_name} · {formatDateTime(expense.created_at)}
          </dd>
        </div>
      </dl>
      <Attachments
        purpose="expense_receipt"
        owner={expense.id}
        label="Receipt photos"
        accept={RECEIPT_ACCEPT}
        canAdd={can('expenses.create')}
        canRemove={can('expenses.manage')}
        max={5}
      />
      {reversing ? (
        <form className="reason-form" onSubmit={reverse} noValidate>
          <ErrorBanner error={error} />
          <TextField
            label="Why is this expense being reversed?"
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            error={fieldError}
            placeholder="e.g. Entered twice"
          />
          <div className="dialog-actions">
            <button type="button" className="button button-secondary" onClick={() => setReversing(false)}>
              Back
            </button>
            <button type="submit" className="button button-danger" disabled={saving}>
              {saving ? 'Saving…' : 'Reverse expense'}
            </button>
          </div>
        </form>
      ) : (
        <div className="dialog-actions">
          {expense.status === 'posted' && can('expenses.manage') && (
            <button className="button button-secondary" onClick={() => setReversing(true)}>
              Reverse
            </button>
          )}
          <button className="button button-primary" onClick={onClose}>
            Close
          </button>
        </div>
      )}
    </Dialog>
  )
}
