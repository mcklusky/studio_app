import './feedback.css'
import { Inbox, type LucideIcon } from 'lucide-react'
import { MenuSelect, type MenuSelectProps } from './MenuSelect'
import { useId, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { ApiError } from '../lib/api'

interface FieldShellProps {
  label: string
  error?: string[]
  hint?: string
  children: (id: string, describedBy: string | undefined) => ReactNode
}

function FieldShell({ label, error, hint, children }: FieldShellProps) {
  const id = useId()
  const describedBy = error?.length ? `${id}-error` : hint ? `${id}-hint` : undefined
  return (
    <div className={`field ${error?.length ? 'has-error' : ''}`}>
      <label htmlFor={id}>{label}</label>
      {children(id, describedBy)}
      {error?.length ? (
        <p className="field-error" id={`${id}-error`}>
          {error.join(' ')}
        </p>
      ) : hint ? (
        <p className="field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      ) : null}
    </div>
  )
}

type InputProps = InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string[]; hint?: string }
export function TextField({ label, error, hint, ...props }: InputProps) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      {(id, describedBy) => <input id={id} aria-invalid={!!error?.length} aria-describedby={describedBy} {...props} />}
    </FieldShell>
  )
}

type SelectProps = Omit<MenuSelectProps, 'variant' | 'id' | 'value'> & {
  label: string
  error?: string[]
  hint?: string
  value?: string | number | readonly string[]
}
export function SelectField({ label, error, hint, value, ...props }: SelectProps) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      {(id, describedBy) => (
        <MenuSelect
          id={id}
          variant="field"
          value={String(value ?? '')}
          aria-invalid={!!error?.length}
          aria-describedby={describedBy}
          {...props}
        />
      )}
    </FieldShell>
  )
}

type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { label: string; error?: string[]; hint?: string }
export function TextAreaField({ label, error, hint, ...props }: TextAreaProps) {
  return (
    <FieldShell label={label} error={error} hint={hint}>
      {(id, describedBy) => <textarea id={id} aria-invalid={!!error?.length} aria-describedby={describedBy} {...props} />}
    </FieldShell>
  )
}

/** Page- or form-level error with the request ID, so staff can quote it to an administrator. */
export function ErrorBanner({ error }: { error: unknown }) {
  if (!error) return null
  const message = error instanceof Error ? error.message : 'Something went wrong.'
  const requestId = error instanceof ApiError ? error.requestId : null
  return (
    <div className="error-banner" role="alert">
      <span>{message}</span>
      {requestId && <small>Reference: {requestId.slice(0, 8)}</small>}
    </div>
  )
}

/** Nothing to show: an icon, what is going on, and (when it helps) the next thing to do. */
export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  children,
}: {
  title: string
  description?: string
  icon?: LucideIcon
  children?: ReactNode
}) {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">
        <Icon size={26} strokeWidth={1.8} />
      </span>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {children}
    </div>
  )
}
