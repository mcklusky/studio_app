import './feedback.css'
import { AlertCircle, Ban, CheckCircle2, Clock3, Info, X, XCircle, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

/**
 * Placeholder rows shaped like the table that is loading, so the page does not jump when data arrives.
 * Announced to screen readers as busy, not as a list of blanks.
 */
export function TableSkeleton({ rows = 6, columns = 5 }: { rows?: number; columns?: number }) {
  return (
    <div className="panel table-panel skeleton-panel" aria-busy="true" aria-live="polite">
      <span className="visually-hidden">Loading…</span>
      <div className="skeleton-head" aria-hidden="true">
        {Array.from({ length: columns }, (_, c) => (
          <span key={c} className="skeleton-bar skeleton-bar-head" style={{ width: c === 0 ? '18%' : `${10 + ((c * 7) % 8)}%` }} />
        ))}
      </div>
      {Array.from({ length: rows }, (_, r) => (
        <div key={r} className="skeleton-row" aria-hidden="true" style={{ animationDelay: `${r * 60}ms` }}>
          <span className="skeleton-stack">
            <span className="skeleton-bar" style={{ width: `${55 + ((r * 13) % 35)}%` }} />
            <span className="skeleton-bar skeleton-bar-sub" style={{ width: `${30 + ((r * 11) % 25)}%` }} />
          </span>
          {Array.from({ length: columns - 2 }, (_, c) => (
            <span key={c} className="skeleton-bar" style={{ width: `${40 + (((r + 2) * (c + 3) * 7) % 45)}%` }} />
          ))}
          <span className="skeleton-bar skeleton-pill" />
        </div>
      ))}
    </div>
  )
}

export type BadgeTone = 'ok' | 'low' | 'out' | 'muted' | 'info'

const BADGE_ICON: Record<BadgeTone, LucideIcon> = {
  ok: CheckCircle2,
  low: Clock3,
  out: XCircle,
  muted: Ban,
  info: Info,
}

/** Status pill with an icon as well as a colour, so the meaning never rests on colour alone. */
export function StatusBadge({ tone, children, className = '' }: { tone: BadgeTone; children: ReactNode; className?: string }) {
  const Icon = BADGE_ICON[tone]
  return (
    <span className={`status-badge status-${tone} ${className}`}>
      <Icon size={13} strokeWidth={2.4} aria-hidden="true" />
      {children}
    </span>
  )
}

/** Short-lived confirmation at the bottom right. Errors get a red accent and an alert icon. */
export function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  const isError = /could not|couldn't|failed|error|not saved|try again|went wrong/i.test(message)
  const Icon = isError ? AlertCircle : CheckCircle2
  return (
    <div className={`toast-card ${isError ? 'is-error' : 'is-success'}`} role={isError ? 'alert' : 'status'}>
      <span className="toast-icon" aria-hidden="true">
        <Icon size={18} />
      </span>
      <span className="toast-text">{message}</span>
      <button type="button" className="toast-close" onClick={onClose} aria-label="Dismiss">
        <X size={16} />
      </button>
      <span className="toast-timer" aria-hidden="true" />
    </div>
  )
}

/** First cell of a list row: a coloured icon tile (or initials) beside the title and its details. */
export function Lead({
  icon: Icon,
  tone = 'olive',
  initials,
  children,
}: {
  icon?: LucideIcon
  tone?: string
  initials?: string
  children: ReactNode
}) {
  return (
    <span className="lead">
      <span className={`lead-icon ${initials ? 'lead-avatar' : `tone-${tone}`}`} aria-hidden="true">
        {initials ?? (Icon && <Icon size={18} strokeWidth={2} />)}
      </span>
      <span className="lead-text">{children}</span>
    </span>
  )
}
