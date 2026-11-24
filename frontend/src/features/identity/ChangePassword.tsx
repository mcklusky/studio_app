import { useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { ErrorBanner, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors } from '../../lib/api'

export function ChangePasswordDialog({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    if (!current) errors.current_password = ['Enter your current password.']
    if (next.length < 8) errors.password = ['Use at least 8 characters.']
    else if (next !== confirm) errors.confirm = ['The two new passwords do not match.']
    setFieldErrors(errors)
    if (Object.keys(errors).length) return
    setSaving(true)
    setError(null)
    try {
      await api.post('/auth/password/', { current_password: current, new_password: next })
      onDone()
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title="Change your password" onClose={onClose} onSubmit={submit}>
      <ErrorBanner error={error} />
      <TextField
        label="Current password"
        type="password"
        autoComplete="current-password"
        autoFocus
        value={current}
        onChange={(e) => setCurrent(e.target.value)}
        error={fieldErrors.current_password}
      />
      <TextField
        label="New password"
        type="password"
        autoComplete="new-password"
        value={next}
        onChange={(e) => setNext(e.target.value)}
        error={fieldErrors.password}
        hint="At least 8 characters, not a common password, not only numbers."
      />
      <TextField
        label="New password again"
        type="password"
        autoComplete="new-password"
        value={confirm}
        onChange={(e) => setConfirm(e.target.value)}
        error={fieldErrors.confirm}
      />
      <p className="field-hint">Other devices signed in to your account will be signed out.</p>
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Change password'}
        </button>
      </div>
    </Dialog>
  )
}
