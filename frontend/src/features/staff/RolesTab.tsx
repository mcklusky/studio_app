import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { ErrorBanner, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors } from '../../lib/api'
import { useAuth } from '../identity/AuthContext'
import type { PermissionGroup, Role } from './types'

/** Roles side by side with the permission catalog. Built-in roles are read-only. */
export function RolesTab({ notify }: { notify: (message: string) => void }) {
  const { can } = useAuth()
  const [roles, setRoles] = useState<Role[] | null>(null)
  const [catalog, setCatalog] = useState<PermissionGroup[]>([])
  const [error, setError] = useState<unknown>(null)
  const [editing, setEditing] = useState<Role | 'new' | null>(null)

  const load = useCallback(() => {
    api
      .get<{ results: Role[] }>('/roles/')
      .then((page) => setRoles(page.results))
      .catch(setError)
  }, [])
  useEffect(() => {
    load()
    api.get<PermissionGroup[]>('/roles/catalog/').then(setCatalog).catch(setError)
  }, [load])

  if (!roles)
    return (
      <>
        <ErrorBanner error={error} />
        {!error && <p className="subheading">Loading…</p>}
      </>
    )

  return (
    <>
      <ErrorBanner error={error} />
      <div className="toolbar roles-toolbar">
        <p className="field-hint">
          Built-in roles are kept up to date by the system. To give a different mix of access, create a custom role.
        </p>
        {can('roles.manage') && (
          <button className="button button-primary" onClick={() => setEditing('new')}>
            ＋ Custom role
          </button>
        )}
      </div>
      <div className="panel table-panel role-matrix-wrap">
        <table className="data-table role-matrix">
          <thead>
            <tr>
              <th scope="col">Permission</th>
              {roles.map((r) => (
                <th key={r.id} scope="col" className="role-col">
                  {r.name}
                  <small className="cell-sub">
                    {r.member_count} active{r.is_system ? '' : ' · custom'}
                  </small>
                  {!r.is_system && can('roles.manage') && (
                    <button className="button button-ghost role-edit" onClick={() => setEditing(r)}>
                      Edit
                    </button>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          {catalog.map((group) => (
            <tbody key={group.title}>
              <tr className="matrix-group">
                <th scope="rowgroup" colSpan={roles.length + 1}>
                  {group.title}
                </th>
              </tr>
              {group.permissions.map((p) => (
                <tr key={p.code}>
                  <th scope="row">{p.description}</th>
                  {roles.map((r) => (
                    <td key={r.id} className="role-col">
                      {r.permissions.includes(p.code) ? (
                        <span className="tick" aria-label="Allowed">
                          ✓
                        </span>
                      ) : (
                        <span className="no" aria-label="Not allowed">
                          –
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      </div>
      {editing && (
        <RoleDialog
          role={editing === 'new' ? null : editing}
          catalog={catalog}
          onClose={() => setEditing(null)}
          onSaved={(saved) => {
            setEditing(null)
            notify(`Role “${saved.name}” saved.`)
            load()
          }}
        />
      )}
    </>
  )
}

function RoleDialog({
  role,
  catalog,
  onClose,
  onSaved,
}: {
  role: Role | null
  catalog: PermissionGroup[]
  onClose: () => void
  onSaved: (role: Role) => void
}) {
  const { organization } = useAuth()
  const mine = new Set(organization?.permissions ?? [])
  const isOwner = organization?.role_code === 'owner-admin'
  const [name, setName] = useState(role?.name ?? '')
  const [chosen, setChosen] = useState<Set<string>>(new Set(role?.permissions ?? []))
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  function toggle(code: string) {
    setChosen((current) => {
      const next = new Set(current)
      if (next.has(code)) next.delete(code)
      else next.add(code)
      return next
    })
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    if (!name.trim()) errors.name = ['Name the role, e.g. Senior cashier.']
    if (chosen.size === 0) errors.permissions = ['Choose at least one permission.']
    setFieldErrors(errors)
    if (Object.keys(errors).length) return
    setSaving(true)
    setError(null)
    try {
      const body = { name: name.trim(), permissions: [...chosen] }
      onSaved(role ? await api.patch<Role>(`/roles/${role.id}/`, body) : await api.post<Role>('/roles/', body))
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title={role ? `Edit ${role.name}` : 'New custom role'} onClose={onClose} onSubmit={submit} wide>
      <ErrorBanner error={error} />
      <TextField
        label="Role name"
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        error={fieldErrors.name}
        placeholder="e.g. Senior cashier"
      />
      {fieldErrors.permissions && <p className="field-error">{fieldErrors.permissions.join(' ')}</p>}
      <div className="permission-groups">
        {catalog.map((group) => (
          <fieldset key={group.title} className="scope-box">
            <legend>{group.title}</legend>
            {group.permissions.map((p) => {
              const grantable = isOwner || mine.has(p.code)
              return (
                <label
                  key={p.code}
                  className="checkbox"
                  title={grantable ? undefined : 'You can only grant permissions you hold yourself.'}
                >
                  <input type="checkbox" checked={chosen.has(p.code)} disabled={!grantable} onChange={() => toggle(p.code)} />{' '}
                  {p.description}
                </label>
              )
            })}
          </fieldset>
        ))}
      </div>
      {role && role.member_count > 0 && (
        <p className="field-hint warn-hint">Changes apply at once to the {role.member_count} people with this role.</p>
      )}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save role'}
        </button>
      </div>
    </Dialog>
  )
}
