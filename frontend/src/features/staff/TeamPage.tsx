import { MenuSelect } from '../../components/MenuSelect'
import { TableSkeleton } from '../../components/Feedback'
import { KeyRound, Pencil, UserCheck, UserX, Users } from 'lucide-react'
import { ActionsHeader, RowActions } from '../../components/RowActions'
import './staff.css'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors } from '../../lib/api'
import { formatDateTime } from '../../lib/format'
import { useAuth } from '../identity/AuthContext'
import { ActivityTab } from './ActivityTab'
import { RolesTab } from './RolesTab'
import type { Branch, Role, StaffMember } from './types'
import type { Focus } from '../../app/focus'

type Tab = 'staff' | 'roles' | 'activity'

const TEAM_ACTIONS = ['Edit', 'Password', 'Access']

export function TeamPage({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { can } = useAuth()
  const tabs: [Tab, string][] = [
    ...(can('staff.manage')
      ? ([
          ['staff', 'Staff'],
          ['roles', 'Roles'],
        ] as [Tab, string][])
      : []),
    ...(can('audit.view') ? ([['activity', 'Activity log']] as [Tab, string][]) : []),
  ]
  const [tab, setTab] = useState<Tab>(tabs[0]?.[0] ?? 'activity')
  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">INSIGHTS</p>
          <h1>Team &amp; access</h1>
          <p className="subheading">Who can sign in, what they can do, and what has been done.</p>
        </div>
      </div>
      <div className="segmented-tabs" role="tablist" aria-label="Team">
        {tabs.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? 'active' : ''}
            onClick={() => setTab(value)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'staff' && <StaffTab notify={notify} focus={focus} />}
      {tab === 'roles' && <RolesTab notify={notify} />}
      {tab === 'activity' && <ActivityTab />}
    </div>
  )
}

function StaffTab({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { sections } = useAuth()
  const [status, setStatus] = useState<'active' | 'inactive' | ''>(focus?.query ? '' : 'active')
  const [query, setQuery] = useState(focus?.query ?? '')
  const [rows, setRows] = useState<StaffMember[] | null>(null)
  const [roles, setRoles] = useState<Role[]>([])
  const [branches, setBranches] = useState<Branch[]>([])
  const [error, setError] = useState<unknown>(null)
  const [editing, setEditing] = useState<StaffMember | 'new' | null>(null)
  const [action, setAction] = useState<{ kind: 'deactivate' | 'reset'; member: StaffMember } | null>(null)
  const [password, setPassword] = useState<{ member: StaffMember; value: string } | null>(null)

  const load = useCallback(async () => {
    try {
      const page = await api.get<{ results: StaffMember[] }>('/staff/', { status: status || undefined, search: query, page_size: 200 })
      setRows(page.results)
      setError(null)
    } catch (err) {
      setError(err)
    }
  }, [status, query])

  useEffect(() => {
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])
  useEffect(() => {
    api
      .get<{ results: Role[] }>('/roles/')
      .then((page) => setRoles(page.results))
      .catch(setError)
    api
      .get<Branch[]>('/branches/')
      .then(setBranches)
      .catch(() => setBranches([]))
  }, [])

  const sectionName = (id: string) => sections.find((s) => s.id === id)?.name ?? 'Unknown'
  const scopeText = (m: StaffMember) => (m.all_sections ? 'All sections' : m.section_ids.map(sectionName).join(', ') || 'No sections')

  async function reactivate(member: StaffMember) {
    try {
      await api.post(`/staff/${member.id}/reactivate/`)
      notify(`${member.name} can sign in again.`)
      void load()
    } catch (err) {
      setError(err)
    }
  }

  return (
    <>
      <div className="toolbar">
        <input
          type="search"
          className="search-input"
          placeholder="Search name, username or email"
          aria-label="Search staff"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <MenuSelect
          variant="pill"
          icon={UserCheck}
          className="toolbar-select"
          aria-label="Status"
          value={status}
          onChange={(e) => setStatus(e.target.value as typeof status)}
        >
          <option value="active">Active</option>
          <option value="inactive">Deactivated</option>
          <option value="">Everyone</option>
        </MenuSelect>
        <button className="button button-primary" onClick={() => setEditing('new')}>
          ＋ Add staff
        </button>
      </div>
      <ErrorBanner error={error} />

      {rows && rows.length === 0 ? (
        <EmptyState icon={Users} title={query ? 'No one matches your search' : 'No staff here'} />
      ) : !rows ? (
        !error && <TableSkeleton columns={5} />
      ) : (
        <div className="panel table-panel">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Person</th>
                <th scope="col">Role</th>
                <th scope="col" className="hide-mobile">
                  Works in
                </th>
                <th scope="col" className="hide-mobile">
                  Last sign-in
                </th>
                <ActionsHeader />
              </tr>
            </thead>
            <tbody>
              {rows.map((m) => (
                <tr key={m.id} className={m.active ? '' : 'is-inactive'}>
                  <td>
                    <span className="staff-person">
                      <span className="staff-avatar" aria-hidden="true">
                        {(m.first_name[0] ?? m.username[0]).toUpperCase()}
                        {(m.last_name[0] ?? '').toUpperCase()}
                      </span>
                      <span>
                        <b>{m.name}</b>
                        {m.is_you && <span className="badge">You</span>}
                        {!m.active && <span className="badge">Deactivated</span>}
                        <small className="cell-sub">
                          {m.username}
                          {m.email && ` · ${m.email}`}
                        </small>
                      </span>
                    </span>
                  </td>
                  <td>
                    <span className={`role-pill role-${m.role_code}`}>{m.role_name}</span>
                  </td>
                  <td className="hide-mobile">
                    {scopeText(m)}
                    {branches.length > 1 && !m.all_branches && <small className="cell-sub">{m.branch_ids.length} branch(es)</small>}
                  </td>
                  <td className="hide-mobile">{m.last_login ? formatDateTime(m.last_login) : <span className="muted">Never</span>}</td>
                  <RowActions
                    label={`Actions for ${m.name}`}
                    columns={TEAM_ACTIONS}
                    actions={{
                      Edit: m.active && { label: 'Edit details', icon: Pencil, tone: 'violet', onClick: () => setEditing(m) },
                      Password: m.active &&
                        !m.is_you && {
                          label: 'Reset password',
                          icon: KeyRound,
                          tone: 'amber',
                          onClick: () => setAction({ kind: 'reset', member: m }),
                        },
                      Access:
                        !m.is_you &&
                        (m.active
                          ? {
                              label: 'Deactivate',
                              icon: UserX,
                              tone: 'red',
                              onClick: () => setAction({ kind: 'deactivate', member: m }),
                            }
                          : { label: 'Reactivate', icon: UserCheck, tone: 'green', onClick: () => void reactivate(m) }),
                    }}
                  />
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing && (
        <StaffDialog
          member={editing === 'new' ? null : editing}
          roles={roles}
          branches={branches}
          onClose={() => setEditing(null)}
          onSaved={(saved, temporary) => {
            setEditing(null)
            void load()
            if (temporary) setPassword({ member: saved, value: temporary })
            else notify(`Saved ${saved.name}.`)
          }}
        />
      )}
      {action && (
        <ConfirmAction
          kind={action.kind}
          member={action.member}
          onClose={() => setAction(null)}
          onDone={(member, temporary) => {
            setAction(null)
            void load()
            if (temporary) setPassword({ member, value: temporary })
            else notify(`${member.name} has been deactivated and can no longer sign in.`)
          }}
        />
      )}
      {password && <TemporaryPassword member={password.member} value={password.value} onClose={() => setPassword(null)} />}
    </>
  )
}

function suggestUsername(first: string, last: string) {
  return `${first}${last ? `.${last}` : ''}`
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^\w.]/g, '')
    .slice(0, 30)
}

function StaffDialog({
  member,
  roles,
  branches,
  onClose,
  onSaved,
}: {
  member: StaffMember | null
  roles: Role[]
  branches: Branch[]
  onClose: () => void
  onSaved: (member: StaffMember, temporaryPassword?: string) => void
}) {
  const { sections, organization } = useAuth()
  const [first, setFirst] = useState(member?.first_name ?? '')
  const [last, setLast] = useState(member?.last_name ?? '')
  const [username, setUsername] = useState(member?.username ?? '')
  const [usernameTouched, setUsernameTouched] = useState(!!member)
  const [email, setEmail] = useState(member?.email ?? '')
  const [roleId, setRoleId] = useState(member?.role ?? roles.find((r) => r.code === 'cashier')?.id ?? roles[0]?.id ?? '')
  const [allSections, setAllSections] = useState(member?.all_sections ?? false)
  const [sectionIds, setSectionIds] = useState<string[]>(member?.section_ids ?? [])
  const [allBranches, setAllBranches] = useState(member?.all_branches ?? true)
  const [branchIds, setBranchIds] = useState<string[]>(member?.branch_ids ?? [])
  const [ownPassword, setOwnPassword] = useState(false)
  const [password, setPassword] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const role = roles.find((r) => r.id === roleId)
  const isOwnerRole = role?.code === 'owner-admin'
  const canGrantOwner = organization?.role_code === 'owner-admin'

  const toggle = (list: string[], id: string) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id])

  async function submit(event: FormEvent) {
    event.preventDefault()
    const errors: FieldErrors = {}
    if (!first.trim()) errors.first_name = ["Enter the person's first name."]
    if (!member && !username.trim()) errors.username = ['Choose a username.']
    if (!allSections && sectionIds.length === 0) errors.sections = ['Choose at least one section, or tick All sections.']
    if (branches.length > 1 && !allBranches && branchIds.length === 0) errors.branches = ['Choose at least one branch.']
    if (ownPassword && password.length < 8) errors.password = ['Use at least 8 characters.']
    setFieldErrors(errors)
    if (Object.keys(errors).length) return
    setSaving(true)
    setError(null)
    const body: Record<string, unknown> = {
      first_name: first.trim(),
      last_name: last.trim(),
      email: email.trim(),
      role: roleId,
      all_sections: allSections,
      sections: allSections ? [] : sectionIds,
      all_branches: branches.length > 1 ? allBranches : true,
      branches: allBranches ? [] : branchIds,
    }
    try {
      if (member) {
        onSaved(await api.patch<StaffMember>(`/staff/${member.id}/`, body))
      } else {
        body.username = username.trim()
        if (ownPassword) body.password = password
        const created = await api.post<StaffMember & { temporary_password?: string }>('/staff/', body)
        onSaved(created, created.temporary_password)
      }
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title={member ? `Edit ${member.name}` : 'Add staff member'} onClose={onClose} onSubmit={submit} wide>
      <ErrorBanner error={error} />
      <div className="field-row">
        <TextField
          label="First name"
          autoFocus
          value={first}
          error={fieldErrors.first_name}
          onChange={(e) => {
            setFirst(e.target.value)
            if (!usernameTouched) setUsername(suggestUsername(e.target.value, last))
          }}
        />
        <TextField
          label="Last name (optional)"
          value={last}
          onChange={(e) => {
            setLast(e.target.value)
            if (!usernameTouched) setUsername(suggestUsername(first, e.target.value))
          }}
        />
      </div>
      <div className="field-row">
        <TextField
          label="Username (used to sign in)"
          value={username}
          disabled={!!member}
          autoComplete="off"
          error={fieldErrors.username}
          hint={member ? 'Usernames cannot be changed.' : 'No spaces. They type this on the sign-in screen.'}
          onChange={(e) => {
            setUsername(e.target.value.replace(/\s/g, ''))
            setUsernameTouched(true)
          }}
        />
        <TextField
          label="Email (optional)"
          type="email"
          value={email}
          autoComplete="off"
          onChange={(e) => setEmail(e.target.value)}
          error={fieldErrors.email}
          hint="Lets them reset a forgotten password."
        />
      </div>

      <SelectField
        label="Role"
        value={roleId}
        onChange={(e) => setRoleId(e.target.value)}
        error={fieldErrors.role}
        disabled={member?.is_you}
        hint={member?.is_you ? 'You cannot change your own role.' : undefined}
      >
        {roles.map((r) => (
          <option key={r.id} value={r.id} disabled={r.code === 'owner-admin' && !canGrantOwner}>
            {r.name}
            {r.is_system ? '' : ' (custom)'}
          </option>
        ))}
      </SelectField>
      {role && <RoleSummary role={role} />}
      {isOwnerRole && (
        <p className="field-hint warn-hint">Owner/admins can do everything, including managing staff and seeing all money figures.</p>
      )}

      <fieldset className={`scope-box ${fieldErrors.sections ? 'has-error' : ''}`}>
        <legend>Works in</legend>
        <label className="checkbox">
          <input type="checkbox" checked={allSections} onChange={(e) => setAllSections(e.target.checked)} /> All sections (including ones
          added later)
        </label>
        {!allSections && (
          <div className="scope-options">
            {sections.map((s) => (
              <label key={s.id} className="checkbox">
                <input type="checkbox" checked={sectionIds.includes(s.id)} onChange={() => setSectionIds((l) => toggle(l, s.id))} />{' '}
                {s.name}
              </label>
            ))}
          </div>
        )}
        {fieldErrors.sections && <p className="field-error">{fieldErrors.sections.join(' ')}</p>}
      </fieldset>
      {branches.length > 1 && (
        <fieldset className={`scope-box ${fieldErrors.branches ? 'has-error' : ''}`}>
          <legend>Branches</legend>
          <label className="checkbox">
            <input type="checkbox" checked={allBranches} onChange={(e) => setAllBranches(e.target.checked)} /> All branches
          </label>
          {!allBranches && (
            <div className="scope-options">
              {branches.map((b) => (
                <label key={b.id} className="checkbox">
                  <input type="checkbox" checked={branchIds.includes(b.id)} onChange={() => setBranchIds((l) => toggle(l, b.id))} />{' '}
                  {b.name}
                </label>
              ))}
            </div>
          )}
          {fieldErrors.branches && <p className="field-error">{fieldErrors.branches.join(' ')}</p>}
        </fieldset>
      )}

      {!member && (
        <fieldset className="scope-box">
          <legend>Password</legend>
          <label className="checkbox">
            <input type="radio" name="pw" checked={!ownPassword} onChange={() => setOwnPassword(false)} /> Create a temporary password for
            me to give them
          </label>
          <label className="checkbox">
            <input type="radio" name="pw" checked={ownPassword} onChange={() => setOwnPassword(true)} /> I will type one now
          </label>
          {ownPassword && (
            <TextField
              label="Password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              error={fieldErrors.password}
              hint="At least 8 characters, not a common password, not only numbers."
            />
          )}
        </fieldset>
      )}

      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : member ? 'Save changes' : 'Add staff member'}
        </button>
      </div>
    </Dialog>
  )
}

const AREA_LABELS: [string, string][] = [
  ['sales.', 'Sales'],
  ['orders.', 'Orders'],
  ['customers.', 'Customers'],
  ['catalog.', 'Products'],
  ['inventory.', 'Stock'],
  ['purchases.', 'Purchases'],
  ['payables.', 'Supplier payments'],
  ['expenses.', 'Expenses'],
  ['reports.', 'Reports'],
  ['staff.', 'Staff'],
  ['audit.', 'Activity log'],
]

function RoleSummary({ role }: { role: Role }) {
  const areas = AREA_LABELS.filter(([prefix]) => role.permissions.some((p) => p.startsWith(prefix))).map(([, label]) => label)
  const costs = role.permissions.includes('inventory.costs')
  return (
    <p className="field-hint role-summary">
      Can use: <b>{areas.join(', ') || 'nothing yet'}</b>. {costs ? 'Sees costs and profit.' : 'Does not see costs or profit.'}
    </p>
  )
}

function ConfirmAction({
  kind,
  member,
  onClose,
  onDone,
}: {
  kind: 'deactivate' | 'reset'
  member: StaffMember
  onClose: () => void
  onDone: (member: StaffMember, temporaryPassword?: string) => void
}) {
  const [reason, setReason] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      if (kind === 'deactivate') {
        onDone(await api.post<StaffMember>(`/staff/${member.id}/deactivate/`, { reason: reason.trim() }))
      } else {
        const result = await api.post<StaffMember & { temporary_password: string }>(`/staff/${member.id}/reset-password/`)
        onDone(result, result.temporary_password)
      }
    } catch (err) {
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog
      title={kind === 'deactivate' ? `Deactivate ${member.name}?` : `Reset ${member.name}'s password?`}
      onClose={onClose}
      onSubmit={submit}
    >
      <ErrorBanner error={error} />
      {kind === 'deactivate' ? (
        <>
          <p className="dialog-lead">
            They will be signed out and unable to sign in. Everything they recorded stays in the books under their name. You can reactivate
            them later.
          </p>
          <TextField
            label="Reason (optional)"
            autoFocus
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="e.g. Left the business"
          />
        </>
      ) : (
        <p className="dialog-lead">
          A new temporary password will be created and shown to you once. They will be signed out on every device until they use it.
        </p>
      )}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className={`button ${kind === 'deactivate' ? 'button-danger' : 'button-primary'}`} disabled={saving}>
          {saving ? 'Working…' : kind === 'deactivate' ? 'Deactivate' : 'Reset password'}
        </button>
      </div>
    </Dialog>
  )
}

function TemporaryPassword({ member, value, onClose }: { member: StaffMember; value: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }
  return (
    <Dialog title={`Password for ${member.name}`} onClose={onClose}>
      <p className="dialog-lead">
        Give these details to {member.first_name || member.name} in person. The password is shown only now. Ask them to change it after
        signing in (their name → Change password).
      </p>
      <dl className="credentials">
        <div>
          <dt>Username</dt>
          <dd>{member.username}</dd>
        </div>
        <div>
          <dt>Temporary password</dt>
          <dd className="mono">{value}</dd>
        </div>
      </dl>
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={() => void copy()}>
          {copied ? 'Copied ✓' : 'Copy password'}
        </button>
        <button type="button" className="button button-primary" onClick={onClose}>
          Done
        </button>
      </div>
    </Dialog>
  )
}
