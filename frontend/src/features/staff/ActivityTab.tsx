import { MenuSelect } from '../../components/MenuSelect'
import { Activity, UserRound } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { EmptyState, ErrorBanner } from '../../components/Form'
import { api, type Page } from '../../lib/api'
import { formatDateTime } from '../../lib/format'
import type { AuditEvent, StaffMember } from './types'

const AREAS: [string, string][] = [
  ['', 'Everything'],
  ['sale,payment', 'Sales & payments'],
  ['order', 'Orders'],
  ['purchase,supplier_payment', 'Purchases'],
  ['stock', 'Stock'],
  ['expense', 'Expenses'],
  ['customer,supplier,product,category,productvariant', 'Contacts & products'],
  ['staff,role,auth', 'Staff & sign-ins'],
  ['exchange_rate,report', 'Rates & exports'],
]

const LABELS: Record<string, string> = {
  'auth.login': 'Signed in',
  'auth.password_changed': 'Changed their password',
  'staff.created': 'Added a staff member',
  'staff.updated': 'Changed a staff member',
  'staff.deactivated': 'Deactivated a staff member',
  'staff.reactivated': 'Reactivated a staff member',
  'staff.password_reset': 'Reset a password',
  'role.created': 'Created a role',
  'role.updated': 'Changed a role',
  'sale.posted': 'Recorded a sale',
  'sale.reversed': 'Reversed a sale',
  'payment.received': 'Received a payment',
  'payment.reversed': 'Reversed a payment',
  'payment.reissued': 'Re-issued a payment',
  'order.created': 'Took an order',
  'order.updated': 'Edited an order',
  'order.status_changed': 'Moved an order on',
  'order.status_corrected': 'Corrected an order status',
  'order.cancelled': 'Cancelled an order',
  'order.material_used': 'Used stock for an order',
  'order.material_returned': 'Returned order material to stock',
  'purchase.created': 'Created a purchase',
  'purchase.updated': 'Edited a purchase',
  'purchase.received': 'Received goods',
  'purchase.receipt_reversed': 'Reversed a goods receipt',
  'purchase.cancelled': 'Cancelled a purchase',
  'supplier_payment.created': 'Paid a supplier',
  'supplier_payment.reversed': 'Reversed a supplier payment',
  'stock.adjusted': 'Adjusted stock',
  'expense.recorded': 'Recorded an expense',
  'expense.reversed': 'Reversed an expense',
  'exchange_rate.created': 'Entered an exchange rate',
  'report.exported': 'Downloaded a report',
}

function label(action: string) {
  if (LABELS[action]) return LABELS[action]
  const [thing, verb] = action.split('.')
  return `${(verb ?? '').replace(/_/g, ' ')} ${thing.replace(/_/g, ' ')}`.trim().replace(/^./, (c) => c.toUpperCase())
}

/** A short, human line from the event summary (never raw JSON). */
function details(event: AuditEvent) {
  const s = event.summary
  const parts: string[] = []
  const pick = (key: string) => (typeof s[key] === 'string' || typeof s[key] === 'number' ? String(s[key]) : null)
  for (const key of ['number', 'username', 'name', 'report', 'format']) {
    const v = pick(key)
    if (v) parts.push(v)
  }
  if (pick('amount')) parts.push(`${pick('currency') ?? ''} ${pick('amount')}`.trim())
  if (pick('total')) parts.push(`${pick('currency') ?? ''} ${pick('total')}`.trim())
  if (pick('from') && pick('to') && event.action.startsWith('order.')) parts.push(`${pick('from')} → ${pick('to')}`)
  if (s.changes && typeof s.changes === 'object') parts.push(`changed ${Object.keys(s.changes as object).join(', ')}`)
  if (Array.isArray(s.added) && s.added.length) parts.push(`added ${s.added.join(', ')}`)
  if (Array.isArray(s.removed) && s.removed.length) parts.push(`removed ${s.removed.join(', ')}`)
  const reason = pick('reason') ?? pick('note')
  if (reason) parts.push(`“${reason}”`)
  return parts.join(' · ')
}

export function ActivityTab() {
  const [area, setArea] = useState('')
  const [actor, setActor] = useState('')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page<AuditEvent> | null>(null)
  const [people, setPeople] = useState<StaffMember[]>([])
  const [error, setError] = useState<unknown>(null)

  const load = useCallback(() => {
    api
      .get<Page<AuditEvent>>('/audit-events/', { area: area || undefined, actor: actor || undefined, page, page_size: 50 })
      .then((result) => {
        setData(result)
        setError(null)
      })
      .catch(setError)
  }, [area, actor, page])
  useEffect(load, [load])
  useEffect(() => {
    api
      .get<{ results: StaffMember[] }>('/staff/', { page_size: 200 })
      .then((p) => setPeople(p.results))
      .catch(() => setPeople([]))
  }, [])

  return (
    <>
      <div className="toolbar">
        <MenuSelect
          variant="pill"
          icon={Activity}
          className="toolbar-select"
          aria-label="What"
          value={area}
          onChange={(e) => {
            setArea(e.target.value)
            setPage(1)
          }}
        >
          {AREAS.map(([value, text]) => (
            <option key={value} value={value}>
              {text}
            </option>
          ))}
        </MenuSelect>
        <MenuSelect
          variant="pill"
          icon={UserRound}
          className="toolbar-select"
          aria-label="Who"
          value={actor}
          onChange={(e) => {
            setActor(e.target.value)
            setPage(1)
          }}
        >
          <option value="">Everyone</option>
          {people.map((p) => (
            <option key={p.id} value={p.user_id}>
              {p.name}
            </option>
          ))}
        </MenuSelect>
      </div>
      <ErrorBanner error={error} />
      {data && data.results.length === 0 ? (
        <EmptyState title="No activity matches" />
      ) : (
        data && (
          <div className="panel table-panel">
            <ol className="audit-list">
              {data.results.map((event) => (
                <li key={event.id}>
                  <span className="audit-when">{formatDateTime(event.created_at)}</span>
                  <span className="audit-what">
                    <b>{event.actor_name}</b> {label(event.action).replace(/^./, (c) => c.toLowerCase())}
                    {details(event) && <small className="cell-sub">{details(event)}</small>}
                  </span>
                </li>
              ))}
            </ol>
            {(data.next || data.previous) && (
              <div className="pager">
                <button className="button button-ghost" disabled={!data.previous} onClick={() => setPage((n) => n - 1)}>
                  ← Newer
                </button>
                <span>Page {page}</span>
                <button className="button button-ghost" disabled={!data.next} onClick={() => setPage((n) => n + 1)}>
                  Older →
                </button>
              </div>
            )}
          </div>
        )
      )}
      <p className="field-hint">The activity log cannot be edited or deleted. Each entry carries a reference that matches error reports.</p>
    </>
  )
}
