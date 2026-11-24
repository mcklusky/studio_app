import { daysFromToday, formatDate, formatDateTime } from '../../lib/format'
import type { OrderSummary } from './types'

export function DueCell({ order }: { order: OrderSummary }) {
  if (order.status === 'delivered')
    return (
      <span className="muted">
        Delivered{order.delivered_at && <small className="cell-sub">{formatDateTime(order.delivered_at)}</small>}
      </span>
    )
  if (order.status === 'cancelled') return <span className="muted">—</span>
  const days = daysFromToday(order.due_date)
  const relative =
    days < 0 ? `${-days} day${days === -1 ? '' : 's'} late` : days === 0 ? 'Today' : days === 1 ? 'Tomorrow' : `In ${days} days`
  return (
    <span className={days < 0 ? 'due-late' : days <= 3 ? 'due-soon' : ''}>
      {formatDate(order.due_date)}
      <small className="cell-sub">
        {relative}
        {order.shoot_at && ` · shoot ${formatDateTime(order.shoot_at)}`}
      </small>
    </span>
  )
}

export function OrderStatusBadge({ order }: { order: Pick<OrderSummary, 'status' | 'status_label' | 'step' | 'overdue'> }) {
  const tone =
    order.status === 'cancelled'
      ? 'status-muted'
      : order.status === 'delivered'
        ? 'status-ok'
        : order.overdue
          ? 'status-out'
          : 'status-progress'
  return (
    <span className={`status-badge ${tone}`}>
      {order.status_label}
      {order.step.index && order.status !== 'delivered' && (
        <span className="step-count">
          {' '}
          {order.step.index}/{order.step.count}
        </span>
      )}
    </span>
  )
}
