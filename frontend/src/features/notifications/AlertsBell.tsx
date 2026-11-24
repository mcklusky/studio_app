import './alerts.css'
import { Bell } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { PageKey } from '../../app/AppShell'
import type { Focus } from '../../app/focus'
import { api } from '../../lib/api'

interface Alert {
  key: string
  kind: string
  severity: 'critical' | 'warning' | 'info'
  title: string
  detail: string
  link: { page: PageKey; id: string | null; query: string | null }
  date: string
  read: boolean
}

const ICON: Record<string, string> = {
  stock_out: '▦',
  stock_low: '▦',
  order_overdue: '▤',
  order_due: '▤',
  shoot_soon: '◉',
  receivable: '＄',
  payable: '⇣',
  fx_rate: '⇄',
  website_request: '✉',
}
const REFRESH_MS = 60_000

/** Bell with unread count; alerts are worked out live by the server and limited to what you may see. */
export function AlertsBell({ onOpen }: { onOpen: (page: PageKey, focus: Focus) => void }) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [unread, setUnread] = useState(0)
  const [open, setOpen] = useState(false)
  const boxRef = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    api
      .get<{ unread: number; items: Alert[] }>('/alerts/')
      .then((data) => {
        setAlerts(data.items)
        setUnread(data.unread)
      })
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    load()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, REFRESH_MS)
    const onClick = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onKey)
    return () => {
      window.clearInterval(timer)
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onKey)
    }
  }, [load])

  async function markRead(keys: string[] | 'all') {
    setAlerts((list) => list.map((a) => (keys === 'all' || keys.includes(a.key) ? { ...a, read: true } : a)))
    setUnread((n) => (keys === 'all' ? 0 : Math.max(0, n - keys.filter((k) => alerts.some((a) => a.key === k && !a.read)).length)))
    try {
      await api.post('/alerts/read/', keys === 'all' ? { all: true } : { keys })
    } catch {
      load()
    }
  }

  function choose(alert: Alert) {
    if (!alert.read) void markRead([alert.key])
    onOpen(alert.link.page, { id: alert.link.id, query: alert.link.query })
    setOpen(false)
  }

  return (
    <div className="alerts" ref={boxRef}>
      <button
        type="button"
        className="bell"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={unread ? `Alerts: ${unread} unread` : 'Alerts'}
        onClick={() => {
          setOpen((o) => !o)
          if (!open) load()
        }}
      >
        <Bell size={20} aria-hidden="true" />
        {unread > 0 && (
          <span className="bell-count" aria-hidden="true">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>
      {open && (
        <div className="alerts-panel" role="dialog" aria-label="Alerts">
          <div className="alerts-head">
            <b>Alerts</b>
            {unread > 0 && (
              <button type="button" className="button button-ghost" onClick={() => void markRead('all')}>
                Mark all read
              </button>
            )}
          </div>
          {alerts.length === 0 ? (
            <p className="alerts-empty">All clear. Nothing needs attention right now.</p>
          ) : (
            <ul className="alerts-list">
              {alerts.map((alert) => (
                <li key={alert.key}>
                  <button
                    type="button"
                    className={`alert-item sev-${alert.severity} ${alert.read ? 'is-read' : ''}`}
                    onClick={() => choose(alert)}
                  >
                    <span className="alert-icon" aria-hidden="true">
                      {ICON[alert.kind] ?? '•'}
                    </span>
                    <span className="alert-text">
                      <b>{alert.title}</b>
                      <small>{alert.detail}</small>
                    </span>
                    {!alert.read && <span className="unread-dot" aria-label="Unread" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <p className="alerts-foot">Alerts clear themselves when the problem is fixed.</p>
        </div>
      )}
    </div>
  )
}
