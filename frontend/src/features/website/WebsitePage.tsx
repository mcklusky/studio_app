import './website.css'
import { Ban, ClipboardPlus, ExternalLink, Globe, Inbox, MessageCircle, Phone, QrCode } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import type { Focus } from '../../app/focus'
import { Dialog } from '../../components/Dialog'
import { QrDialog } from '../../components/QrCode'
import { Lead, TableSkeleton } from '../../components/Feedback'
import { EmptyState, ErrorBanner, TextAreaField, TextField } from '../../components/Form'
import { ActionsHeader, actionColumns, RowActions } from '../../components/RowActions'
import { api, ApiError, type FieldErrors } from '../../lib/api'
import { formatDate, formatDateTime, initials } from '../../lib/format'
import type { Contact } from '../contacts/ContactsPage'
import { useAuth } from '../identity/AuthContext'
import { OrderFormDialog } from '../orders/OrderForm'
import type { OrderKind } from '../orders/types'

export const SITE_PATH = '/site/'

interface WebsiteRequest {
  id: string
  number: string
  kind: 'photography' | 'printing' | 'clothing' | 'other'
  kind_label: string
  section: string | null
  name: string
  phone: string
  email: string
  message: string
  preferred_date: string | null
  status: 'new' | 'accepted' | 'declined'
  status_label: string
  decline_reason: string
  order: string | null
  order_number: string | null
  handled_by: string | null
  handled_at: string | null
  created_at: string
}

interface Profile {
  enabled: boolean
  headline: string
  about: string
  phone: string
  whatsapp: string
  email: string
  address: string
  hours: string
  map_url: string
}

type Tab = 'new' | 'accepted' | 'declined' | 'settings'

/** WhatsApp link for a Liberian number written locally (0777…) or internationally (+231…). */
export function whatsappLink(phone: string, text = '') {
  let digits = phone.replace(/\D/g, '')
  if (digits.startsWith('0')) digits = `231${digits.slice(1)}`
  return `https://wa.me/${digits}${text ? `?text=${encodeURIComponent(text)}` : ''}`
}

export function WebsitePage({ notify, focus }: { notify: (message: string) => void; focus?: Focus }) {
  const { can } = useAuth()
  const [tab, setTab] = useState<Tab>('new')
  const [rows, setRows] = useState<WebsiteRequest[] | null>(null)
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [loadError, setLoadError] = useState<unknown>(null)
  const [open, setOpen] = useState<WebsiteRequest | null>(null)
  const [ordering, setOrdering] = useState<{ request: WebsiteRequest; customer: Contact } | null>(null)
  const [declining, setDeclining] = useState<WebsiteRequest | null>(null)
  const [showQr, setShowQr] = useState(false)
  const focusUsed = useRef(false)
  const focusId = focus?.id

  const load = useCallback(() => {
    if (tab === 'settings') return
    api
      .get<{ counts: Record<string, number>; results: WebsiteRequest[] }>('/website/requests/', { status: tab })
      .then((data) => {
        setRows(data.results)
        setCounts(data.counts)
        setLoadError(null)
        // Opened from an alert: show that request once.
        const hit = !focusUsed.current && focusId ? data.results.find((r) => r.id === focusId) : undefined
        if (hit) {
          focusUsed.current = true
          setOpen(hit)
        }
      })
      .catch(setLoadError)
  }, [tab, focusId])

  useEffect(load, [load])

  async function startOrder(request: WebsiteRequest) {
    try {
      const customer = await api.post<Contact>(`/website/requests/${request.id}/customer/`)
      setOpen(null)
      setOrdering({ request, customer })
    } catch (err) {
      notify(err instanceof ApiError ? err.message : 'Could not prepare the order. Try again.')
    }
  }

  const actionCols = actionColumns('Order', 'Call', 'WhatsApp', 'Decline')
  const tabs: [Tab, string][] = [
    ['new', 'New'],
    ['accepted', 'Accepted'],
    ['declined', 'Declined'],
    ['settings', 'Site details'],
  ]

  return (
    <section>
      <header className="page-header">
        <div>
          <p className="eyebrow">MANAGE</p>
          <h1>Website</h1>
          <p className="subheading">Booking and quote requests from your public website, and what the site says.</p>
        </div>
        <div className="website-head-actions">
          <button type="button" className="button button-secondary website-open" onClick={() => setShowQr(true)}>
            <QrCode size={16} aria-hidden="true" /> Website QR code
          </button>
          <a className="button button-secondary website-open" href={SITE_PATH} target="_blank" rel="noreferrer">
            <Globe size={16} aria-hidden="true" /> Open website <ExternalLink size={14} aria-hidden="true" />
          </a>
        </div>
      </header>

      <div className="segmented-tabs" role="tablist" aria-label="Website">
        {tabs.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            className={tab === value ? 'active' : ''}
            onClick={() => {
              setRows(null)
              setTab(value)
            }}
          >
            {label}
            {value !== 'settings' && counts[value] ? <span className="tab-count">{counts[value]}</span> : null}
          </button>
        ))}
      </div>

      {tab === 'settings' ? (
        <SiteSettings notify={notify} />
      ) : (
        <>
          <ErrorBanner error={loadError} />
          {rows && rows.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title={tab === 'new' ? 'No new requests' : `No ${tab} requests`}
              description={
                tab === 'new'
                  ? 'When customers ask for a booking or a quote on the website, it shows up here and in your alerts.'
                  : undefined
              }
            />
          ) : !rows ? (
            !loadError && <TableSkeleton columns={5} />
          ) : (
            <div className="panel table-panel">
              <table className="data-table clickable-rows">
                <thead>
                  <tr>
                    <th scope="col">From</th>
                    <th scope="col">Wants</th>
                    <th scope="col" className="hide-mobile">
                      Preferred date
                    </th>
                    <th scope="col" className="hide-mobile">
                      {tab === 'new' ? 'Received' : tab === 'accepted' ? 'Order' : 'Reason'}
                    </th>
                    <ActionsHeader />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.id} onClick={() => setOpen(r)}>
                      <td>
                        <Lead initials={initials(r.name)}>
                          <b>{r.name}</b>
                          <small className="cell-sub">
                            {r.number} · {r.phone}
                          </small>
                        </Lead>
                      </td>
                      <td>
                        <span className={`kind-pill kind-pill-${r.kind}`}>{r.kind_label}</span>
                        <small className="cell-sub request-preview">{r.message}</small>
                      </td>
                      <td className="hide-mobile">{r.preferred_date ? formatDate(r.preferred_date, true) : '—'}</td>
                      <td className="hide-mobile">
                        {tab === 'new' ? formatDateTime(r.created_at) : tab === 'accepted' ? (r.order_number ?? '—') : r.decline_reason}
                      </td>
                      <RowActions
                        label={`Actions for ${r.number}`}
                        columns={actionCols}
                        actions={{
                          Order: r.status === 'new' &&
                            r.kind !== 'other' &&
                            can('orders.create') && {
                              label: 'Create order',
                              icon: ClipboardPlus,
                              tone: 'brand',
                              onClick: () => void startOrder(r),
                            },
                          Call: { label: 'Call', icon: Phone, tone: 'blue', onClick: () => window.open(`tel:${r.phone}`) },
                          WhatsApp: {
                            label: 'WhatsApp',
                            icon: MessageCircle,
                            tone: 'green',
                            onClick: () =>
                              window.open(whatsappLink(r.phone, `Hello ${r.name}, this is Just Smile about your request ${r.number}.`)),
                          },
                          Decline: r.status === 'new' && { label: 'Decline', icon: Ban, tone: 'red', onClick: () => setDeclining(r) },
                        }}
                      />
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {open && (
        <RequestDialog
          request={open}
          canOrder={open.status === 'new' && open.kind !== 'other' && can('orders.create')}
          onClose={() => setOpen(null)}
          onOrder={() => void startOrder(open)}
          onDecline={() => {
            setDeclining(open)
            setOpen(null)
          }}
        />
      )}
      {showQr && (
        <QrDialog
          title="Website QR code"
          url={`${location.origin}${SITE_PATH}`}
          fileName="just-smile-website-qr.png"
          posterHeadline="Book, get a quote or track your order"
          posterSubline="Scan with your phone camera to open the Just Smile website."
          onClose={() => setShowQr(false)}
        >
          <p className="field-hint">
            Put this on receipts, flyers, banners and the shop counter. Customers scan it to see prices, send a booking or quote request,
            and track their order. On their phone they can also add the website to their home screen.
          </p>
        </QrDialog>
      )}
      {declining && (
        <DeclineDialog
          request={declining}
          onClose={() => setDeclining(null)}
          onDone={() => {
            setDeclining(null)
            notify(`${declining.number} declined.`)
            load()
          }}
        />
      )}
      {ordering && (
        <OrderFormDialog
          defaultKind={ordering.request.kind as OrderKind}
          prefill={{
            customer: ordering.customer,
            title: ordering.request.message.split('\n')[0].slice(0, 80),
            notes: `From website request ${ordering.request.number}:\n${ordering.request.message}`,
            dueDate: ordering.request.preferred_date ?? undefined,
          }}
          onClose={() => setOrdering(null)}
          onSaved={async (order) => {
            const request = ordering.request
            setOrdering(null)
            try {
              await api.post(`/website/requests/${request.id}/accept/`, { order: order.id })
              notify(`${order.number} created from ${request.number}.`)
            } catch {
              notify(`${order.number} was created, but ${request.number} could not be marked accepted. Try again from the list.`)
            }
            load()
          }}
        />
      )}
    </section>
  )
}

function RequestDialog({
  request,
  canOrder,
  onClose,
  onOrder,
  onDecline,
}: {
  request: WebsiteRequest
  canOrder: boolean
  onClose: () => void
  onOrder: () => void
  onDecline: () => void
}) {
  return (
    <Dialog title={`${request.number} · ${request.kind_label}`} onClose={onClose}>
      <dl className="request-facts">
        <div>
          <dt>From</dt>
          <dd>{request.name}</dd>
        </div>
        <div>
          <dt>Phone</dt>
          <dd>
            <a href={`tel:${request.phone}`}>{request.phone}</a> ·{' '}
            <a href={whatsappLink(request.phone)} target="_blank" rel="noreferrer">
              WhatsApp
            </a>
          </dd>
        </div>
        {request.email && (
          <div>
            <dt>Email</dt>
            <dd>
              <a href={`mailto:${request.email}`}>{request.email}</a>
            </dd>
          </div>
        )}
        <div>
          <dt>Preferred date</dt>
          <dd>{request.preferred_date ? formatDate(request.preferred_date, true) : 'Not given'}</dd>
        </div>
        <div>
          <dt>Received</dt>
          <dd>{formatDateTime(request.created_at)}</dd>
        </div>
        {request.status !== 'new' && (
          <div>
            <dt>{request.status_label}</dt>
            <dd>
              {request.order_number ?? request.decline_reason}
              {request.handled_by && ` · by ${request.handled_by}`}
            </dd>
          </div>
        )}
      </dl>
      <p className="request-message">{request.message}</p>
      {request.kind === 'other' && request.status === 'new' && (
        <p className="field-hint">This is a general question: reply by phone or WhatsApp, then decline it to clear it from the list.</p>
      )}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Close
        </button>
        {request.status === 'new' && (
          <button type="button" className="button button-secondary text-danger" onClick={onDecline}>
            Decline
          </button>
        )}
        {canOrder && (
          <button type="button" className="button button-primary" onClick={onOrder}>
            Create order
          </button>
        )}
      </div>
    </Dialog>
  )
}

function DeclineDialog({ request, onClose, onDone }: { request: WebsiteRequest; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSaving(true)
    setError(null)
    try {
      await api.post(`/website/requests/${request.id}/decline/`, { reason })
      onDone()
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title={`Decline ${request.number}`} onClose={onClose} onSubmit={submit}>
      <ErrorBanner error={error} />
      <TextField
        label="Reason (for the team only)"
        autoFocus
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        error={fieldErrors.reason}
        hint="The customer is not told automatically. Call or WhatsApp them if they should know."
      />
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-danger" disabled={saving}>
          {saving ? 'Saving…' : 'Decline request'}
        </button>
      </div>
    </Dialog>
  )
}

function SiteSettings({ notify }: { notify: (message: string) => void }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get<Profile>('/website/profile/').then(setProfile).catch(setError)
  }, [])

  if (!profile) return error ? <ErrorBanner error={error} /> : <TableSkeleton rows={3} columns={3} />
  const set = <K extends keyof Profile>(key: K, value: Profile[K]) => setProfile((p) => (p ? { ...p, [key]: value } : p))

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!profile) return
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      setProfile(await api.put<Profile>('/website/profile/', profile))
      notify('Website details saved.')
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="panel website-settings" onSubmit={save}>
      <ErrorBanner error={error} />
      <label className={`website-switch ${profile.enabled ? 'is-on' : ''}`}>
        <input type="checkbox" checked={profile.enabled} onChange={(e) => set('enabled', e.target.checked)} />
        <span>
          <b>{profile.enabled ? 'Website is live' : 'Website is switched off'}</b>
          <small>
            {profile.enabled ? 'Anyone can visit it and send requests.' : 'Visitors see "not available" until you switch it on.'}
          </small>
        </span>
      </label>
      <div className="website-grid">
        <TextField
          label="Headline"
          maxLength={140}
          value={profile.headline}
          onChange={(e) => set('headline', e.target.value)}
          error={fieldErrors.headline}
          hint="The big line on the home page, e.g. “Printing, photos and custom clothing, done with a smile.”"
        />
        <TextAreaField
          label="About us"
          rows={4}
          maxLength={1200}
          value={profile.about}
          onChange={(e) => set('about', e.target.value)}
          error={fieldErrors.about}
        />
        <TextField label="Phone" value={profile.phone} onChange={(e) => set('phone', e.target.value)} error={fieldErrors.phone} />
        <TextField
          label="WhatsApp number"
          value={profile.whatsapp}
          onChange={(e) => set('whatsapp', e.target.value)}
          error={fieldErrors.whatsapp}
          hint="Shown as a “Chat on WhatsApp” button."
        />
        <TextField
          label="Email"
          type="email"
          value={profile.email}
          onChange={(e) => set('email', e.target.value)}
          error={fieldErrors.email}
        />
        <TextField label="Address" value={profile.address} onChange={(e) => set('address', e.target.value)} error={fieldErrors.address} />
        <TextField
          label="Opening hours"
          value={profile.hours}
          onChange={(e) => set('hours', e.target.value)}
          error={fieldErrors.hours}
          hint="e.g. Mon–Sat 8:00–18:00"
        />
        <TextField
          label="Map link (optional)"
          value={profile.map_url}
          onChange={(e) => set('map_url', e.target.value)}
          error={fieldErrors.map_url}
          hint="Paste a Google Maps share link."
        />
      </div>
      <p className="field-hint">
        Products and services appear on the website when you tick “Show this on the website” on the product. Costs, stock and customer
        details are never shown.
      </p>
      <div className="dialog-actions">
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save website details'}
        </button>
      </div>
    </form>
  )
}
