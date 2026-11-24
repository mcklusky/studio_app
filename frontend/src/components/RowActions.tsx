import { LoaderCircle, Pencil, type LucideIcon } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

/**
 * Colour says what kind of action it is, the same on every list:
 * brand = the next step, blue = view or download, green = money, violet = edit, amber = adjust or reset, red = undo or remove.
 */
export type ActionTone = 'brand' | 'blue' | 'green' | 'violet' | 'amber' | 'red' | 'neutral'

export interface RowAction {
  /** What the menu item says, e.g. "Take payment". */
  label: string
  icon: LucideIcon
  tone: ActionTone
  onClick: () => void
  busy?: boolean
}

/** Keep only the actions this person's role can ever use, e.g. actionColumns('Receipt', can('sales.reverse') && 'Reverse'). */
export function actionColumns(...columns: (string | false | null | undefined)[]) {
  return columns.filter(Boolean) as string[]
}

/**
 * One "Edit" button at the end of a list row. With several actions it opens a short menu of what this
 * row allows right now; when editing is the only action it edits straight away. The server still checks every action.
 */
export function RowActions({
  columns,
  actions,
  label,
}: {
  columns: string[]
  actions: Record<string, RowAction | false | null | undefined>
  label: string
}) {
  const available = columns.map((column) => actions[column]).filter(Boolean) as RowAction[]
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<{ top: number; right: number; up: boolean } | null>(null)
  const button = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const busy = available.some((a) => a.busy)
  const direct = available.length === 1 && available[0].icon === Pencil ? available[0] : null

  // The menu is fixed to the viewport so a scrolling table cannot clip it; it opens upward near the bottom.
  useLayoutEffect(() => {
    if (!open || !button.current) return
    const rect = button.current.getBoundingClientRect()
    const up = window.innerHeight - rect.bottom < 56 * available.length + 24
    setPosition({ top: up ? rect.top - 6 : rect.bottom + 6, right: window.innerWidth - rect.right, up })
  }, [open, available.length])

  useEffect(() => {
    if (!open) return
    const close = (event: Event) => {
      if (event.target instanceof Node && (menu.current?.contains(event.target) || button.current?.contains(event.target))) return
      setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        button.current?.focus()
      }
    }
    document.addEventListener('mousedown', close)
    window.addEventListener('scroll', close, true)
    window.addEventListener('resize', close)
    window.addEventListener('keydown', onKey)
    menu.current?.querySelector('button')?.focus()
    return () => {
      document.removeEventListener('mousedown', close)
      window.removeEventListener('scroll', close, true)
      window.removeEventListener('resize', close)
      window.removeEventListener('keydown', onKey)
    }
  }, [open, position])

  return (
    <td className="cell-actions" onClick={(e) => e.stopPropagation()}>
      {available.length > 0 && (
        <>
          <button
            ref={button}
            type="button"
            className="row-edit"
            aria-label={direct ? `${direct.label}: ${label}` : `Edit: ${label}`}
            aria-haspopup={direct ? undefined : 'menu'}
            aria-expanded={direct ? undefined : open}
            disabled={busy}
            onClick={() => (direct ? direct.onClick() : setOpen((o) => !o))}
          >
            {busy ? <LoaderCircle size={14} className="spin" aria-hidden="true" /> : <Pencil size={14} aria-hidden="true" />}
            <span>{busy ? 'Saving…' : 'Edit'}</span>
          </button>
          {open && position && (
            <div
              ref={menu}
              className={`row-menu ${position.up ? 'is-up' : ''}`}
              role="menu"
              aria-label={label}
              style={
                position.up
                  ? { bottom: window.innerHeight - position.top, right: position.right }
                  : { top: position.top, right: position.right }
              }
            >
              {available.map((action) => {
                const Icon = action.icon
                return (
                  <button
                    key={action.label}
                    type="button"
                    role="menuitem"
                    className={`row-menu-item ${action.tone === 'red' ? 'is-danger' : ''}`}
                    onClick={() => {
                      setOpen(false)
                      action.onClick()
                    }}
                  >
                    <span className={`row-menu-icon tone-${action.tone}`} aria-hidden="true">
                      <Icon size={15} strokeWidth={2.2} />
                    </span>
                    {action.label}
                  </button>
                )
              })}
            </div>
          )}
        </>
      )}
    </td>
  )
}

/** Header cell for the actions column. */
export function ActionsHeader() {
  return (
    <th scope="col" className="cell-actions">
      <span className="visually-hidden">Actions</span>
    </th>
  )
}
