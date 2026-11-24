import { useEffect, useId, useRef, type FormEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'

interface DialogProps {
  title: string
  onClose: () => void
  children: ReactNode
  /** When set, the dialog body is a <form> and Enter submits it. */
  onSubmit?: (event: FormEvent) => void
  wide?: boolean
}

// Open dialogs, innermost last: Escape closes only the top one.
const openStack: string[] = []

export function Dialog({ title, onClose, children, onSubmit, wide }: DialogProps) {
  const titleId = useId()
  const onCloseRef = useRef(onClose)
  useEffect(() => {
    onCloseRef.current = onClose
  })

  useEffect(() => {
    openStack.push(titleId)
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && openStack[openStack.length - 1] === titleId) onCloseRef.current()
    }
    window.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      openStack.splice(openStack.indexOf(titleId), 1)
      document.body.style.overflow = previous
    }
  }, [titleId])

  const header = (
    <div className="dialog-header">
      <h2 id={titleId}>{title}</h2>
      <button type="button" className="icon-close" aria-label="Close" onClick={onClose}>
        ×
      </button>
    </div>
  )
  const className = `dialog ${wide ? 'dialog-wide' : ''}`

  // Portal to <body> so a dialog opened from inside a form is not a nested form, and stop submit events
  // bubbling through the React tree (portals still propagate React events to their parents).
  const handleSubmit =
    onSubmit &&
    ((event: FormEvent) => {
      event.stopPropagation()
      onSubmit(event)
    })

  return createPortal(
    <div
      className="dialog-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      {onSubmit ? (
        <form className={className} role="dialog" aria-modal="true" aria-labelledby={titleId} onSubmit={handleSubmit} noValidate>
          {header}
          {children}
        </form>
      ) : (
        <div className={className} role="dialog" aria-modal="true" aria-labelledby={titleId}>
          {header}
          {children}
        </div>
      )}
    </div>,
    document.body,
  )
}
