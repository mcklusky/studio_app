import { useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { ErrorBanner, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors } from '../../lib/api'
import { formatDateTime, initials } from '../../lib/format'
import { useAuth } from './AuthContext'
import type { CurrentUser } from './types'

/** Edit your own name and email. Role and access are set by an administrator on Team & access. */
export function ProfileDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const { user, organization, updateUser } = useAuth()
  const [first, setFirst] = useState(user?.first_name ?? '')
  const [last, setLast] = useState(user?.last_name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  if (!user || !organization) return null
  const preview = `${first} ${last}`.trim() || user.username

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      updateUser(await api.patch<CurrentUser>('/auth/me/', { first_name: first, last_name: last, email }))
      onDone()
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title="My profile" onClose={onClose} onSubmit={submit}>
      <div className="profile-card">
        <span className="profile-card-avatar" aria-hidden="true">
          {initials(preview)}
        </span>
        <div>
          <b>{preview}</b>
          <small>
            @{user.username} · {organization.role}
          </small>
          {user.last_login && <small>Last signed in {formatDateTime(user.last_login)}</small>}
        </div>
      </div>
      <ErrorBanner error={error} />
      <div className="profile-name-row">
        <TextField
          label="First name"
          autoComplete="given-name"
          autoFocus
          value={first}
          onChange={(e) => setFirst(e.target.value)}
          error={fieldErrors.first_name}
        />
        <TextField
          label="Last name"
          autoComplete="family-name"
          value={last}
          onChange={(e) => setLast(e.target.value)}
          error={fieldErrors.last_name}
        />
      </div>
      <TextField
        label="Email"
        type="email"
        autoComplete="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        error={fieldErrors.email}
        hint="Used to reset your password if you forget it."
      />
      <p className="field-hint">Your username, role and access are managed by an administrator.</p>
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save profile'}
        </button>
      </div>
    </Dialog>
  )
}
