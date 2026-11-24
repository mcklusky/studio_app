import './mobile.css'
import { LayoutGrid, MessagesSquare, X, type LucideIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { PageKey } from './AppShell'

export interface MobileNavEntry {
  key: PageKey
  label: string
  icon: LucideIcon
}

const PRIMARY: PageKey[] = ['overview', 'sales', 'orders']

/** Phone navigation: three main pages and "More" (every other page the role can open, plus team chat). */
export function MobileNav({
  entries,
  current,
  unreadMessages,
  onNavigate,
  onChat,
}: {
  entries: MobileNavEntry[]
  current: PageKey | undefined
  unreadMessages: number
  onNavigate: (key: PageKey) => void
  onChat: () => void
}) {
  const [moreOpen, setMoreOpen] = useState(false)
  const primary = [...entries.filter((e) => PRIMARY.includes(e.key)), ...entries.filter((e) => !PRIMARY.includes(e.key))].slice(0, 3)
  const rest = entries.filter((e) => !primary.includes(e))
  const moreActive = rest.some((e) => e.key === current)

  useEffect(() => {
    if (!moreOpen) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setMoreOpen(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [moreOpen])

  const go = (key: PageKey) => {
    setMoreOpen(false)
    onNavigate(key)
  }

  return (
    <>
      <nav className="mobile-nav" aria-label="Main">
        {primary.map((entry) => {
          const Icon = entry.icon
          return (
            <button
              key={entry.key}
              type="button"
              className={current === entry.key ? 'is-active' : ''}
              aria-current={current === entry.key ? 'page' : undefined}
              onClick={() => go(entry.key)}
            >
              <Icon size={22} aria-hidden="true" />
              <span>{entry.label}</span>
            </button>
          )
        })}
        <button
          type="button"
          className={moreActive || moreOpen ? 'is-active' : ''}
          aria-expanded={moreOpen}
          aria-haspopup="dialog"
          onClick={() => setMoreOpen((o) => !o)}
        >
          <LayoutGrid size={22} aria-hidden="true" />
          <span>More</span>
          {unreadMessages > 0 && <i className="mobile-nav-dot" aria-label={`${unreadMessages} unread messages`} />}
        </button>
      </nav>
      {moreOpen && (
        <div className="mobile-sheet-layer" onMouseDown={(e) => e.target === e.currentTarget && setMoreOpen(false)}>
          <section className="mobile-sheet" role="dialog" aria-modal="true" aria-label="More pages">
            <header>
              <b>More</b>
              <button type="button" className="mobile-sheet-close" aria-label="Close" onClick={() => setMoreOpen(false)}>
                <X size={20} />
              </button>
            </header>
            <div className="mobile-sheet-grid">
              {rest.map((entry) => {
                const Icon = entry.icon
                return (
                  <button
                    key={entry.key}
                    type="button"
                    className={current === entry.key ? 'is-active' : ''}
                    aria-current={current === entry.key ? 'page' : undefined}
                    onClick={() => go(entry.key)}
                  >
                    <span className="mobile-sheet-icon" aria-hidden="true">
                      <Icon size={22} />
                    </span>
                    {entry.label}
                  </button>
                )
              })}
              <button
                type="button"
                onClick={() => {
                  setMoreOpen(false)
                  onChat()
                }}
              >
                <span className="mobile-sheet-icon" aria-hidden="true">
                  <MessagesSquare size={22} />
                  {unreadMessages > 0 && <i className="mobile-sheet-count">{unreadMessages > 99 ? '99+' : unreadMessages}</i>}
                </span>
                Team chat
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  )
}
