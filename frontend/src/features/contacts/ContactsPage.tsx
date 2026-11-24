import { initials } from '../../lib/format'
import { Lead, TableSkeleton } from '../../components/Feedback'
import { FileText, Pencil, Users } from 'lucide-react'
import { ActionsHeader, actionColumns, RowActions } from '../../components/RowActions'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { EmptyState, ErrorBanner, SelectField, TextAreaField, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { useAuth } from '../identity/AuthContext'
import { BalanceText, StatementDialog } from './Statement'
import type { Focus } from '../../app/focus'

/** Customers and suppliers share one directory screen; only a few fields differ. */
export interface Contact {
  id: string
  name: string
  phone: string
  email: string
  notes: string
  active: boolean
  address?: string
  customer_type?: 'individual' | 'business'
  location?: string
  /** Present only for roles allowed to see money owed. */
  balances?: Record<string, string>
}

interface MoneyConfig {
  statementPermission: string
  payPermission: string
  reversePermission: string
  paymentEndpoint: string
  ownerField: 'customer' | 'supplier'
  documentLabel: string
  documentPlural: string
  payLabel: string
}

export interface ContactKind {
  endpoint: string
  singular: string
  plural: string
  permission: { create: string; manage: string }
  /** 'address' + type for customers, 'location' for suppliers. */
  placeField: 'address' | 'location'
  placeLabel: string
  hasType: boolean
  money?: MoneyConfig
}

export const CUSTOMERS: ContactKind = {
  endpoint: '/customers/',
  singular: 'customer',
  plural: 'Customers',
  permission: { create: 'customers.create', manage: 'customers.manage' },
  placeField: 'address',
  placeLabel: 'Address',
  hasType: true,
  money: {
    statementPermission: 'sales.view',
    payPermission: 'sales.create',
    reversePermission: 'sales.reverse',
    paymentEndpoint: '/customer-payments/',
    ownerField: 'customer',
    documentLabel: 'Invoice',
    documentPlural: 'invoices',
    payLabel: 'Record payment',
  },
}

export const SUPPLIERS: ContactKind = {
  endpoint: '/suppliers/',
  singular: 'supplier',
  plural: 'Suppliers',
  permission: { create: 'suppliers.create', manage: 'suppliers.manage' },
  placeField: 'location',
  placeLabel: 'Location',
  hasType: false,
  money: {
    statementPermission: 'purchases.view',
    payPermission: 'payables.pay',
    reversePermission: 'payables.pay',
    paymentEndpoint: '/supplier-payments/',
    ownerField: 'supplier',
    documentLabel: 'Purchase',
    documentPlural: 'purchases',
    payLabel: 'Pay supplier',
  },
}

export function ContactsPage({ kind, notify, focus }: { kind: ContactKind; notify: (message: string) => void; focus?: Focus }) {
  const { can } = useAuth()
  const [query, setQuery] = useState(focus?.query ?? '')
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Page<Contact> | null>(null)
  const [loadError, setLoadError] = useState<unknown>(null)
  const [editing, setEditing] = useState<Contact | 'new' | null>(null)
  const [owingOnly, setOwingOnly] = useState(false)
  const [statementFor, setStatementFor] = useState<Contact | null>(null)
  const showMoney = !!kind.money && can(kind.money.statementPermission)

  const load = useCallback(async () => {
    setLoadError(null)
    try {
      setData(await api.get<Page<Contact>>(kind.endpoint, { search: query, page, has_balance: owingOnly ? 'true' : undefined }))
    } catch (err) {
      setLoadError(err)
    }
  }, [kind.endpoint, query, page, owingOnly])

  useEffect(() => {
    const timer = window.setTimeout(load, query ? 250 : 0)
    return () => window.clearTimeout(timer)
  }, [load, query])

  const canCreate = can(kind.permission.create)
  const canManage = can(kind.permission.manage)
  const actionCols = actionColumns(showMoney && 'Statement', canManage && 'Edit')
  const noun = (n: number) => `${n} ${n === 1 ? kind.singular : `${kind.singular}s`}`

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <p className="eyebrow">MANAGE</p>
          <h1>{kind.plural}</h1>
          <p className="subheading">{data ? noun(data.count) : 'Loading…'}</p>
        </div>
        {canCreate && (
          <button className="button button-primary" onClick={() => setEditing('new')}>
            ＋ Add {kind.singular}
          </button>
        )}
      </div>

      {showMoney && (
        <div className="segmented-tabs" role="tablist" aria-label="Filter">
          <button
            role="tab"
            aria-selected={!owingOnly}
            className={!owingOnly ? 'active' : ''}
            onClick={() => {
              setOwingOnly(false)
              setPage(1)
            }}
          >
            All
          </button>
          <button
            role="tab"
            aria-selected={owingOnly}
            className={owingOnly ? 'active' : ''}
            onClick={() => {
              setOwingOnly(true)
              setPage(1)
            }}
          >
            {kind.singular === 'customer' ? 'Owing money' : 'We owe'}
          </button>
        </div>
      )}
      <div className="toolbar">
        <input
          type="search"
          className="search-input"
          placeholder="Search name, phone or email"
          aria-label={`Search ${kind.plural.toLowerCase()}`}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setPage(1)
          }}
        />
      </div>

      <ErrorBanner error={loadError} />

      {data && data.results.length === 0 ? (
        <EmptyState
          icon={Users}
          title={
            owingOnly
              ? 'No outstanding balances'
              : query
                ? `No ${kind.plural.toLowerCase()} match your search`
                : `No ${kind.plural.toLowerCase()} yet`
          }
        >
          {!query && canCreate && (
            <button className="button button-secondary" onClick={() => setEditing('new')}>
              Add your first {kind.singular}
            </button>
          )}
        </EmptyState>
      ) : !data ? (
        !loadError && <TableSkeleton columns={5} />
      ) : (
        <div className="panel table-panel">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Phone</th>
                <th scope="col" className="hide-mobile">
                  Email
                </th>
                <th scope="col" className="hide-mobile">
                  {kind.hasType ? 'Type' : kind.placeLabel}
                </th>
                {showMoney && (
                  <th scope="col" className="num">
                    Balance
                  </th>
                )}
                <ActionsHeader />
              </tr>
            </thead>
            <tbody>
              {data.results.map((contact) => (
                <tr key={contact.id} className={contact.active ? '' : 'is-inactive'}>
                  <td>
                    <Lead initials={initials(contact.name)}>
                      <b>{contact.name}</b>
                      {!contact.active && <span className="badge">Inactive</span>}
                    </Lead>
                  </td>
                  <td>{contact.phone || '—'}</td>
                  <td className="hide-mobile">{contact.email || '—'}</td>
                  <td className="hide-mobile">
                    {kind.hasType ? (contact.customer_type === 'business' ? 'Business' : 'Individual') : contact[kind.placeField] || '—'}
                  </td>
                  {showMoney && (
                    <td className="num">
                      <BalanceText balances={contact.balances} />
                    </td>
                  )}
                  <RowActions
                    label={`Actions for ${contact.name}`}
                    columns={actionCols}
                    actions={{
                      Statement: { label: 'Open statement', icon: FileText, tone: 'blue', onClick: () => setStatementFor(contact) },
                      Edit: { label: 'Edit details', icon: Pencil, tone: 'violet', onClick: () => setEditing(contact) },
                    }}
                  />
                </tr>
              ))}
            </tbody>
          </table>
          {(data.next || data.previous) && (
            <div className="pager">
              <button className="button button-ghost" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>
                ← Previous
              </button>
              <span>Page {page}</span>
              <button className="button button-ghost" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>
                Next →
              </button>
            </div>
          )}
        </div>
      )}

      {statementFor && (
        <StatementDialog
          kind={kind}
          contact={statementFor}
          onClose={() => setStatementFor(null)}
          onChanged={(message) => {
            notify(message)
            void load()
          }}
        />
      )}
      {editing && (
        <ContactDialog
          kind={kind}
          contact={editing === 'new' ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={(saved, created) => {
            setEditing(null)
            notify(created ? `Added ${saved.name}.` : `Saved ${saved.name}.`)
            void load()
          }}
        />
      )}
    </div>
  )
}

export function ContactDialog({
  kind,
  contact,
  onClose,
  onSaved,
  initialName = '',
}: {
  kind: ContactKind
  contact: Contact | null
  onClose: () => void
  onSaved: (contact: Contact, created: boolean) => void
  initialName?: string
}) {
  const [draft, setDraft] = useState({
    name: contact?.name ?? initialName,
    phone: contact?.phone ?? '',
    email: contact?.email ?? '',
    place: (contact?.[kind.placeField] as string | undefined) ?? '',
    customer_type: contact?.customer_type ?? 'individual',
    notes: contact?.notes ?? '',
  })
  const [active, setActive] = useState(contact?.active ?? true)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  const set = (key: keyof typeof draft) => (event: { target: { value: string } }) => setDraft((d) => ({ ...d, [key]: event.target.value }))

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!draft.name.trim()) {
      setFieldErrors({ name: [`Enter the ${kind.singular} name.`] })
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    const body: Record<string, unknown> = {
      name: draft.name.trim(),
      phone: draft.phone,
      email: draft.email,
      notes: draft.notes,
      active,
      [kind.placeField]: draft.place,
    }
    if (kind.hasType) body.customer_type = draft.customer_type
    try {
      const saved = contact
        ? await api.patch<Contact>(`${kind.endpoint}${contact.id}/`, body)
        : await api.post<Contact>(kind.endpoint, body)
      onSaved(saved, !contact)
    } catch (err) {
      if (err instanceof ApiError) {
        const errors = { ...err.fieldErrors }
        if (errors[kind.placeField]) errors.place = errors[kind.placeField]
        setFieldErrors(errors)
      }
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title={contact ? `Edit ${kind.singular}` : `Add ${kind.singular}`} onClose={onClose} onSubmit={handleSubmit}>
      <ErrorBanner error={error} />
      <TextField label="Name" autoFocus value={draft.name} onChange={set('name')} error={fieldErrors.name} />
      <div className="field-row">
        <TextField label="Phone" type="tel" autoComplete="off" value={draft.phone} onChange={set('phone')} error={fieldErrors.phone} />
        {kind.hasType && (
          <SelectField label="Type" value={draft.customer_type} onChange={set('customer_type')} error={fieldErrors.customer_type}>
            <option value="individual">Individual</option>
            <option value="business">Business</option>
          </SelectField>
        )}
      </div>
      <TextField label="Email" type="email" autoComplete="off" value={draft.email} onChange={set('email')} error={fieldErrors.email} />
      <TextField label={kind.placeLabel} value={draft.place} onChange={set('place')} error={fieldErrors.place} />
      <TextAreaField label="Notes" rows={3} value={draft.notes} onChange={set('notes')} error={fieldErrors.notes} />
      {contact && (
        <label className="checkbox">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} /> Active {kind.singular}
        </label>
      )}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : `Save ${kind.singular}`}
        </button>
      </div>
    </Dialog>
  )
}
