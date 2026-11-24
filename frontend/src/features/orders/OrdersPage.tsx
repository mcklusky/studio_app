import { Lead, StatusBadge, TableSkeleton } from '../../components/Feedback'
import { Banknote, Camera, CircleArrowRight, ClipboardList, type LucideIcon, Printer, Shirt } from 'lucide-react'
import './orders.css'
import { useCallback, useEffect, useState } from 'react'
import { EmptyState, ErrorBanner } from '../../components/Form'
import { ActionsHeader, actionColumns, RowActions } from '../../components/RowActions'
import { api } from '../../lib/api'
import { formatMoney } from '../../lib/format'
import { CurrencySwitch, TxnAmount } from '../currencies/DisplayCurrency'
import { useAuth } from '../identity/AuthContext'
import { DueCell, OrderStatusBadge } from './OrderBits'
import { OrderDetailDialog } from './OrderDetail'
import { OrderFormDialog } from './OrderForm'
import { KIND_LABEL, type OrderKind, type OrderPage, type OrderSummary } from './types'
import type { Focus } from '../../app/focus'

type View = 'active' | 'due_soon' | 'overdue' | 'unpaid' | 'delivered' | 'cancelled' | 'all'
const VIEWS: [View, string][] = [
  ['active', 'Active'],
  ['due_soon', 'Due soon'],
  ['overdue', 'Overdue'],
  ['unpaid', 'Balance due'],
  ['delivered', 'Delivered'],
  ['cancelled', 'Cancelled'],
  ['all', 'All'],
]

const KIND_ICON: Record<string, LucideIcon> = { clothing: Shirt, photography: Camera, printing: Printer }

export function OrdersPage({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { can, sections, viewSections } = useAuth()
  const actionCols = actionColumns(can('orders.update') && 'Next step', can('orders.payments') && 'Payment')
  const orderSections = sections.filter((s) => s.code in KIND_LABEL)
  const tabSections = viewSections.filter((s) => s.code in KIND_LABEL)
  const [kind, setKind] = useState<OrderKind | ''>('')
  const [view, setView] = useState<View>('active')
  const [mine, setMine] = useState(false)
  const [query, setQuery] = useState(focus?.query ?? '')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<OrderPage | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [openId, setOpenId] = useState<string | null>(focus?.id ?? null)
  const [openPaying, setOpenPaying] = useState(false)
  const [advancing, setAdvancing] = useState<string | null>(null)
  const openOrder = (id: string, paying = false) => {
    setOpenPaying(paying)
    setOpenId(id)
  }
  const [creating, setCreating] = useState(false)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setData(
        await api.get<OrderPage>('/orders/', {
          view,
          kind: kind || undefined,
          assigned: mine ? 'me' : undefined,
          search: query,
          page,
        }),
      )
    } catch (err) {
      setLoadError(err)
    }
  }, [view, kind, mine, query, page])

  useEffect(() => {
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  const counts = data?.counts
  const countFor = (v: View) =>
    v === 'active' ? counts?.active : v === 'due_soon' ? counts?.due_soon : v === 'overdue' ? counts?.overdue : undefined
  async function advance(order: OrderSummary) {
    const next = order.step.next
    if (!next) return
    if (
      next.code === 'delivered' &&
      Number(order.balance_due) > 0 &&
      !window.confirm(`${formatMoney(order.balance_due, order.currency)} is still unpaid. Mark ${order.number} as delivered anyway?`)
    )
      return
    setAdvancing(order.id)
    try {
      await api.post(`/orders/${order.id}/status/`, { status: next.code })
      notify(`${order.number}: ${next.label}.`)
      await load()
    } catch (err) {
      setLoadError(err)
    } finally {
      setAdvancing(null)
    }
  }

  const canCreate = can('orders.create') && orderSections.length > 0

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">WORKSPACE</p>
          <h1>Orders</h1>
          <p className="subheading">
            {counts ? (
              <>
                {counts.active} in progress
                {counts.overdue > 0 && (
                  <>
                    {' '}
                    · <b className="text-danger">{counts.overdue} overdue</b>
                  </>
                )}
              </>
            ) : (
              'Loading…'
            )}
          </p>
        </div>
        <CurrencySwitch />
        {canCreate && (
          <button className="button button-primary button-large" onClick={() => setCreating(true)}>
            ＋ New order
          </button>
        )}
      </div>

      {tabSections.length > 1 && (
        <div className="kind-chips" role="group" aria-label="Department">
          {(['', ...tabSections.map((s) => s.code as OrderKind)] as const).map((k) => (
            <button
              key={k || 'all'}
              type="button"
              className={`kind-chip ${kind === k ? 'active' : ''}`}
              aria-pressed={kind === k}
              onClick={() => {
                setKind(k)
                setPage(1)
              }}
            >
              {k ? (
                <>
                  <span className={`kind-dot kind-${k}`} aria-hidden="true" />
                  {KIND_LABEL[k]}
                </>
              ) : (
                'All departments'
              )}
            </button>
          ))}
        </div>
      )}

      <div className="segmented-tabs" role="tablist" aria-label="Order filter">
        {VIEWS.map(([value, label]) => {
          const n = countFor(value)
          return (
            <button
              key={value}
              role="tab"
              aria-selected={view === value}
              className={view === value ? 'active' : ''}
              onClick={() => {
                setView(value)
                setPage(1)
              }}
            >
              {label}
              {n ? <span className={`tab-count ${value === 'overdue' ? 'tab-count-danger' : ''}`}>{n}</span> : null}
            </button>
          )
        })}
      </div>
      <div className="toolbar">
        <input
          type="search"
          className="search-input"
          placeholder="Search order number, job, customer or phone"
          aria-label="Search orders"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
        <label className="checkbox toolbar-check">
          <input
            type="checkbox"
            checked={mine}
            onChange={(e) => {
              setMine(e.target.checked)
              setPage(1)
            }}
          />{' '}
          Assigned to me
        </label>
      </div>
      <ErrorBanner error={loadError} />

      {data && data.results.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          title={
            query
              ? 'No orders match your search'
              : view === 'overdue'
                ? 'Nothing overdue'
                : view === 'active'
                  ? 'No orders in progress'
                  : 'No orders here'
          }
        >
          {view === 'active' && !query && canCreate && (
            <button className="button button-primary" onClick={() => setCreating(true)}>
              Take the first order
            </button>
          )}
        </EmptyState>
      ) : !data ? (
        !loadError && <TableSkeleton columns={6} />
      ) : (
        <div className="panel table-panel">
          <table className="data-table clickable-rows">
            <thead>
              <tr>
                <th scope="col">Order</th>
                <th scope="col">Due</th>
                <th scope="col" className="hide-mobile">
                  Status
                </th>
                <th scope="col" className="hide-mobile">
                  Assigned
                </th>
                <th scope="col" className="num">
                  Balance
                </th>
                <ActionsHeader />
              </tr>
            </thead>
            <tbody>
              {data.results.map((o) => (
                <tr key={o.id} onClick={() => openOrder(o.id)} className={o.status === 'cancelled' ? 'is-inactive' : ''}>
                  <td>
                    <Lead icon={KIND_ICON[o.kind] ?? ClipboardList} tone={`kind-${o.kind}`}>
                      <button
                        className="link-button"
                        onClick={(e) => {
                          e.stopPropagation()
                          openOrder(o.id)
                        }}
                      >
                        {o.number}
                      </button>
                      <span className="order-title"> {o.title}</span>
                      <small className="cell-sub">
                        {o.customer_name}
                        {o.customer_phone && ` · ${o.customer_phone}`}
                      </small>
                      <span className="show-mobile">
                        <OrderStatusBadge order={o} />
                      </span>
                    </Lead>
                  </td>
                  <td>
                    <DueCell order={o} />
                  </td>
                  <td className="hide-mobile">
                    <OrderStatusBadge order={o} />
                  </td>
                  <td className="hide-mobile">{o.assigned_to_name ?? <span className="muted">—</span>}</td>
                  <td className="num">
                    <BalanceCell order={o} />
                  </td>
                  <RowActions
                    label={`Actions for ${o.number}`}
                    columns={actionCols}
                    actions={{
                      'Next step': o.step.next && {
                        label: `Mark ${o.step.next.label.toLowerCase()}`,
                        icon: CircleArrowRight,
                        tone: 'brand',
                        busy: advancing === o.id,
                        onClick: () => void advance(o),
                      },
                      Payment: o.status !== 'cancelled' &&
                        Number(o.balance_due) > 0 && {
                          label: 'Take payment',
                          icon: Banknote,
                          tone: 'green',
                          onClick: () => openOrder(o.id, true),
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
        <OrderFormDialog
          defaultKind={kind || undefined}
          onClose={() => setCreating(false)}
          onSaved={(order) => {
            setCreating(false)
            notify(`${order.number} created for ${order.customer_name}.`)
            void load()
            setOpenId(order.id)
          }}
        />
      )}
      {openId && (
        <OrderDetailDialog
          id={openId}
          initialMode={openPaying ? 'pay' : 'view'}
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

function BalanceCell({ order }: { order: OrderSummary }) {
  if (order.status === 'cancelled') return <span className="muted">—</span>
  if (Number(order.balance_due) <= 0) return <StatusBadge tone="ok">Paid</StatusBadge>
  return (
    <>
      <TxnAmount amount={order.balance_due} currency={order.currency} unitsPerUsd={order.fx_units_per_usd} />
      <small className="cell-sub">of {formatMoney(order.total, order.currency)}</small>
    </>
  )
}
