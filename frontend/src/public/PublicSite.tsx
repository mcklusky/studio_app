import {
  ArrowRight,
  Camera,
  CheckCircle2,
  Clock3,
  Mail,
  MapPin,
  Menu,
  MessageCircle,
  Phone,
  Printer,
  Search,
  Send,
  Shirt,
  Smartphone,
  Sparkles,
  X,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useInstallPrompt } from '../lib/install'

/** Public website for customers. Talks only to /api/public/v1 (no sign-in, no staff data). */

const API = '/api/public/v1'
const YEAR = new Date().getFullYear()

interface Site {
  name: string
  headline: string
  about: string
  phone: string
  whatsapp: string
  email: string
  address: string
  hours: string
  map_url: string
  departments: { code: string; name: string }[]
  request_kinds: { value: string; label: string }[]
  form_token: string
}

interface Item {
  id: string
  name: string
  kind: 'product' | 'service'
  section: { code: string; name: string }
  description: string
  price_usd: string
  price_lrd: string | null
  image_url: string | null
}

interface Tracked {
  type: 'order' | 'sale'
  number: string
  title: string
  kind: string
  status_label: string
  cancelled: boolean
  steps: { label: string; done: boolean; current: boolean }[]
  due_date: string | null
  currency: string
  total: string
  paid: string
  balance_due: string
}

type Errors = Record<string, string[]>

class PublicError extends Error {
  fields: Errors
  constructor(message: string, fields: Errors = {}) {
    super(message)
    this.fields = fields
  }
}

async function call<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    method: body ? 'POST' : 'GET',
    headers: body ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    if (response.status === 429) throw new PublicError('Too many tries. Please wait a little and try again.')
    const error = (data as { error?: { message?: string; field_errors?: Errors } }).error
    throw new PublicError(error?.message ?? 'Something went wrong. Please try again.', error?.field_errors ?? {})
  }
  return data as T
}

const DEPARTMENT: Record<string, { icon: LucideIcon; blurb: string; tone: string }> = {
  printing: { icon: Printer, blurb: 'Flyers, banners, cards, programmes and branded print, done fast and in full colour.', tone: 'bronze' },
  photography: { icon: Camera, blurb: 'Weddings, events, portraits and video, with edited photos delivered on time.', tone: 'orange' },
  clothing: { icon: Shirt, blurb: 'Custom T-shirts, jerseys and uniforms with your names, numbers and logo.', tone: 'rust' },
}

function money(value: string, currency: string) {
  const amount = Number(value)
  return `${currency} ${amount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function whatsappHref(number: string, text = '') {
  let digits = number.replace(/\D/g, '')
  if (digits.startsWith('0')) digits = `231${digits.slice(1)}`
  return `https://wa.me/${digits}${text ? `?text=${encodeURIComponent(text)}` : ''}`
}

function todayIso() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function PublicSite() {
  const [site, setSite] = useState<Site | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  const [items, setItems] = useState<Item[]>([])
  const [menuOpen, setMenuOpen] = useState(false)
  const [prefill, setPrefill] = useState<{ kind: string; message: string } | null>(null)

  useEffect(() => {
    call<Site>('/site/')
      .then((data) => {
        setSite(data)
        document.title = `${data.name} · Printing, Photography & Clothing`
      })
      .catch(() => setUnavailable(true))
    call<{ results: Item[] }>('/catalog/')
      .then((data) => setItems(data.results))
      .catch(() => setItems([]))
  }, [])

  if (unavailable)
    return (
      <main className="pub-unavailable">
        <img src="/brand/just-smile-on-dark.png" alt="Just Smile" width="160" height="160" />
        <h1>Our website is coming soon</h1>
        <p>Please visit us or call in the meantime.</p>
      </main>
    )
  if (!site)
    return (
      <main className="pub-unavailable" aria-busy="true">
        <img src="/brand/just-smile-on-dark.png" alt="Just Smile" width="120" height="120" className="pub-pulse" />
      </main>
    )

  const nav: [string, string][] = [
    ['#services', 'Services'],
    ['#prices', 'Prices'],
    ['#book', 'Book'],
    ['#track', 'Track order'],
    ['#contact', 'Contact'],
  ]
  const ask = (item: Item) => {
    setPrefill({
      kind: site.request_kinds.some((k) => k.value === item.section.code) ? item.section.code : 'other',
      message: `I'm interested in: ${item.name}.\n`,
    })
    document.getElementById('book')?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <>
      <header className="pub-header">
        <a className="pub-brand" href="#top" aria-label={`${site.name} home`}>
          <img src="/brand/just-smile-on-dark.png" alt="" width="44" height="44" />
          <span>
            Just Smile<small>EMPIRE</small>
          </span>
        </a>
        <nav className={`pub-nav ${menuOpen ? 'is-open' : ''}`} aria-label="Main">
          {nav.map(([href, label]) => (
            <a key={href} href={href} onClick={() => setMenuOpen(false)}>
              {label}
            </a>
          ))}
          {site.whatsapp && (
            <a className="pub-nav-cta" href={whatsappHref(site.whatsapp)} target="_blank" rel="noreferrer">
              <MessageCircle size={16} aria-hidden="true" /> WhatsApp us
            </a>
          )}
        </nav>
        <button
          type="button"
          className="pub-menu"
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((o) => !o)}
        >
          {menuOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </header>

      <main id="top">
        <section className="pub-hero">
          <svg className="pub-hero-art" viewBox="0 0 600 400" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
            <circle cx="470" cy="120" r="210" />
            <circle cx="470" cy="120" r="150" />
            <path d="M 330 250 Q 470 360 610 250" />
          </svg>
          <div className="pub-hero-inner">
            <p className="pub-eyebrow">
              <Sparkles size={15} aria-hidden="true" /> Printing press · Photography &amp; video · Clothing
            </p>
            <h1>{site.headline || 'Print it, shoot it, wear it, all with a smile.'}</h1>
            <p className="pub-hero-sub">
              {site.about ? site.about.split('\n')[0] : 'One team for your prints, photos and custom clothing, right here in Liberia.'}
            </p>
            <div className="pub-hero-actions">
              <a className="pub-btn pub-btn-primary" href="#book">
                Book or get a quote <ArrowRight size={18} aria-hidden="true" />
              </a>
              <a className="pub-btn pub-btn-ghost" href="#track">
                <Search size={17} aria-hidden="true" /> Track my order
              </a>
            </div>
          </div>
        </section>

        <section id="services" className="pub-section">
          <div className="pub-section-head">
            <p className="pub-kicker">What we do</p>
            <h2>Three studios, one smile</h2>
          </div>
          <div className="pub-departments">
            {(site.departments.length ? site.departments : Object.keys(DEPARTMENT).map((code) => ({ code, name: code }))).map((d) => {
              const info = DEPARTMENT[d.code] ?? { icon: Sparkles, blurb: '', tone: 'rust' }
              const Icon = info.icon
              return (
                <article key={d.code} className={`pub-dept tone-${info.tone}`}>
                  <span className="pub-dept-icon" aria-hidden="true">
                    <Icon size={26} />
                  </span>
                  <h3>{d.name}</h3>
                  <p>{info.blurb}</p>
                  <a href="#book" onClick={() => setPrefill({ kind: d.code, message: '' })}>
                    Request a quote <ArrowRight size={16} aria-hidden="true" />
                  </a>
                </article>
              )
            })}
          </div>
        </section>

        {items.length > 0 && <PriceList items={items} onAsk={ask} />}

        <section id="book" className="pub-section pub-split">
          <div className="pub-section-head">
            <p className="pub-kicker">Book or ask for a quote</p>
            <h2>Tell us what you need</h2>
            <p>Send your request and our team will call or WhatsApp you to confirm the details and price. Nothing is charged online.</p>
            <ul className="pub-promises">
              <li>
                <CheckCircle2 size={18} aria-hidden="true" /> We reply during opening hours
              </li>
              <li>
                <CheckCircle2 size={18} aria-hidden="true" /> No payment until you agree the price
              </li>
              <li>
                <CheckCircle2 size={18} aria-hidden="true" /> Your details are only used for your order
              </li>
            </ul>
          </div>
          <BookingForm site={site} prefill={prefill} key={prefill ? `${prefill.kind}-${prefill.message}` : 'blank'} />
        </section>

        <section id="track" className="pub-section pub-track-section">
          <TrackOrder />
        </section>

        <section id="contact" className="pub-section">
          <div className="pub-section-head">
            <p className="pub-kicker">Visit or call</p>
            <h2>Find us</h2>
            {site.about && <p className="pub-about">{site.about}</p>}
          </div>
          <div className="pub-contact">
            {site.phone && <ContactCard icon={Phone} label="Call us" value={site.phone} href={`tel:${site.phone}`} />}
            {site.whatsapp && (
              <ContactCard icon={MessageCircle} label="WhatsApp" value={site.whatsapp} href={whatsappHref(site.whatsapp)} external />
            )}
            {site.email && <ContactCard icon={Mail} label="Email" value={site.email} href={`mailto:${site.email}`} />}
            {site.address && (
              <ContactCard icon={MapPin} label="Address" value={site.address} href={site.map_url || undefined} external={!!site.map_url} />
            )}
            {site.hours && <ContactCard icon={Clock3} label="Opening hours" value={site.hours} />}
          </div>
        </section>
      </main>

      <footer className="pub-footer">
        <InstallButton />
        <img src="/brand/just-smile-on-dark.png" alt="" width="56" height="56" />
        <p>
          © {YEAR} {site.name}. Printing Press · Photography &amp; Videography · Clothing
        </p>
      </footer>
      {site.whatsapp && (
        <a className="pub-float" href={whatsappHref(site.whatsapp)} target="_blank" rel="noreferrer" aria-label="Chat with us on WhatsApp">
          <MessageCircle size={26} aria-hidden="true" />
        </a>
      )}
    </>
  )
}

/** Shown only when the phone's browser offers installing the website as an app. */
function InstallButton() {
  const { canInstall, installed, install } = useInstallPrompt()
  if (!canInstall || installed) return null
  return (
    <button type="button" className="pub-btn pub-btn-primary pub-install" onClick={() => void install()}>
      <Smartphone size={18} aria-hidden="true" /> Add Just Smile to your phone
    </button>
  )
}

function ContactCard({
  icon: Icon,
  label,
  value,
  href,
  external,
}: {
  icon: LucideIcon
  label: string
  value: string
  href?: string
  external?: boolean
}) {
  const body = (
    <>
      <span className="pub-contact-icon" aria-hidden="true">
        <Icon size={20} />
      </span>
      <span>
        <small>{label}</small>
        <b>{value}</b>
      </span>
    </>
  )
  return href ? (
    <a className="pub-contact-card" href={href} {...(external ? { target: '_blank', rel: 'noreferrer' } : {})}>
      {body}
    </a>
  ) : (
    <div className="pub-contact-card">{body}</div>
  )
}

function PriceList({ items, onAsk }: { items: Item[]; onAsk: (item: Item) => void }) {
  const sections = useMemo(() => [...new Map(items.map((i) => [i.section.code, i.section])).values()], [items])
  const [filter, setFilter] = useState('')
  const shown = filter ? items.filter((i) => i.section.code === filter) : items
  return (
    <section id="prices" className="pub-section">
      <div className="pub-section-head">
        <p className="pub-kicker">Prices</p>
        <h2>Popular items &amp; packages</h2>
        <p>Prices are a guide. Final prices depend on quantity and details, and we confirm before you pay.</p>
      </div>
      {sections.length > 1 && (
        <div className="pub-chips" role="group" aria-label="Filter by department">
          <button type="button" className={!filter ? 'is-active' : ''} onClick={() => setFilter('')}>
            All
          </button>
          {sections.map((s) => (
            <button key={s.code} type="button" className={filter === s.code ? 'is-active' : ''} onClick={() => setFilter(s.code)}>
              {s.name}
            </button>
          ))}
        </div>
      )}
      <div className="pub-items">
        {shown.map((item) => {
          const Icon = DEPARTMENT[item.section.code]?.icon ?? Sparkles
          return (
            <article key={item.id} className="pub-item">
              <div className={`pub-item-media tone-${DEPARTMENT[item.section.code]?.tone ?? 'rust'}`}>
                {item.image_url ? <img src={item.image_url} alt="" loading="lazy" /> : <Icon size={36} aria-hidden="true" />}
                <span className="pub-item-tag">{item.section.name}</span>
              </div>
              <div className="pub-item-body">
                <h3>{item.name}</h3>
                {item.description && <p>{item.description}</p>}
                <div className="pub-item-foot">
                  <span className="pub-price">
                    <b>{money(item.price_usd, 'USD')}</b>
                    {item.price_lrd && <small>≈ {money(item.price_lrd, 'LRD')}</small>}
                  </span>
                  <button type="button" className="pub-btn pub-btn-small" onClick={() => onAsk(item)}>
                    Ask about this
                  </button>
                </div>
              </div>
            </article>
          )
        })}
      </div>
    </section>
  )
}

function BookingForm({ site, prefill }: { site: Site; prefill: { kind: string; message: string } | null }) {
  const [kind, setKind] = useState(prefill?.kind ?? site.request_kinds[0]?.value ?? 'other')
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [email, setEmail] = useState('')
  const [date, setDate] = useState('')
  const [message, setMessage] = useState(prefill?.message ?? '')
  const [trap, setTrap] = useState('')
  const [errors, setErrors] = useState<Errors>({})
  const [error, setError] = useState('')
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState<string | null>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setSending(true)
    setError('')
    setErrors({})
    try {
      const result = await call<{ number: string }>('/requests/', {
        kind,
        name,
        phone,
        email,
        preferred_date: date || null,
        message,
        website: trap,
        token: site.form_token,
      })
      setSent(result.number)
    } catch (err) {
      if (err instanceof PublicError) {
        setErrors(err.fields)
        setError(Object.keys(err.fields).length ? 'Please check the highlighted fields.' : err.message)
      } else setError('Your request could not be sent. Please check your connection and try again.')
    } finally {
      setSending(false)
    }
  }

  if (sent)
    return (
      <div className="pub-card pub-sent" role="status">
        <CheckCircle2 size={44} aria-hidden="true" />
        <h3>Thank you, {name.split(' ')[0]}!</h3>
        <p>
          Your request number is <b>{sent}</b>. We will call or WhatsApp you on {phone} soon.
        </p>
        {site.whatsapp && (
          <a
            className="pub-btn pub-btn-primary"
            href={whatsappHref(site.whatsapp, `Hello, I just sent request ${sent} on your website.`)}
            target="_blank"
            rel="noreferrer"
          >
            <MessageCircle size={18} aria-hidden="true" /> Chat now on WhatsApp
          </a>
        )}
      </div>
    )

  const err = (key: string) =>
    errors[key] ? (
      <span className="pub-field-error" id={`${key}-error`}>
        {errors[key].join(' ')}
      </span>
    ) : null
  return (
    <form className="pub-card pub-form" onSubmit={submit} noValidate>
      <fieldset className="pub-kinds">
        <legend>What do you need?</legend>
        {site.request_kinds.map((k) => (
          <label key={k.value} className={kind === k.value ? 'is-checked' : ''}>
            <input type="radio" name="kind" value={k.value} checked={kind === k.value} onChange={() => setKind(k.value)} />
            {k.label}
          </label>
        ))}
        {err('kind')}
      </fieldset>
      <div className="pub-row">
        <label className="pub-field">
          <span>Your name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            required
            aria-invalid={!!errors.name}
            aria-describedby={errors.name ? 'name-error' : undefined}
          />
          {err('name')}
        </label>
        <label className="pub-field">
          <span>Phone or WhatsApp</span>
          <input
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            placeholder="0777 000 000"
            required
            aria-invalid={!!errors.phone}
            aria-describedby={errors.phone ? 'phone-error' : undefined}
          />
          {err('phone')}
        </label>
      </div>
      <div className="pub-row">
        <label className="pub-field">
          <span>
            Email <em>(optional)</em>
          </span>
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            type="email"
            autoComplete="email"
            aria-invalid={!!errors.email}
            aria-describedby={errors.email ? 'email-error' : undefined}
          />
          {err('email')}
        </label>
        <label className="pub-field">
          <span>
            Date you need it <em>(optional)</em>
          </span>
          <input
            value={date}
            onChange={(e) => setDate(e.target.value)}
            type="date"
            min={todayIso()}
            aria-invalid={!!errors.preferred_date}
            aria-describedby={errors.preferred_date ? 'preferred_date-error' : undefined}
          />
          {err('preferred_date')}
        </label>
      </div>
      <label className="pub-field">
        <span>Details</span>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={4}
          maxLength={2000}
          placeholder="e.g. 200 A5 flyers in full colour, or a wedding shoot on 12 December at Paynesville"
          required
          aria-invalid={!!errors.message}
          aria-describedby={errors.message ? 'message-error' : undefined}
        />
        {err('message')}
      </label>
      {/* Hidden from people; bots fill it in. */}
      <label className="pub-trap" aria-hidden="true">
        Website
        <input tabIndex={-1} autoComplete="off" value={trap} onChange={(e) => setTrap(e.target.value)} />
      </label>
      {error && (
        <p className="pub-form-error" role="alert">
          {error}
          {errors.form ? ` ${errors.form.join(' ')}` : ''}
        </p>
      )}
      <button type="submit" className="pub-btn pub-btn-primary pub-btn-block" disabled={sending}>
        {sending ? 'Sending…' : 'Send my request'} <Send size={17} aria-hidden="true" />
      </button>
    </form>
  )
}

function TrackOrder() {
  const [number, setNumber] = useState('')
  const [phone, setPhone] = useState('')
  const [result, setResult] = useState<Tracked | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const resultRef = useRef<HTMLDivElement>(null)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError('')
    setResult(null)
    try {
      setResult(await call<Tracked>('/track/', { number, phone }))
      requestAnimationFrame(() => resultRef.current?.focus())
    } catch (err) {
      setError(err instanceof PublicError ? err.message : 'Please check your connection and try again.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="pub-track">
      <div className="pub-section-head pub-on-dark">
        <p className="pub-kicker">Track my order</p>
        <h2>Where is my order?</h2>
        <p>Enter the number on your receipt or order slip (like ORD-0012) and the phone number you gave us.</p>
      </div>
      <form className="pub-track-form" onSubmit={submit}>
        <label className="pub-field">
          <span>Order or receipt number</span>
          <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder="ORD-0012" autoCapitalize="characters" required />
        </label>
        <label className="pub-field">
          <span>Phone number</span>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} type="tel" inputMode="tel" placeholder="0777 000 000" required />
        </label>
        <button type="submit" className="pub-btn pub-btn-primary" disabled={busy}>
          {busy ? 'Checking…' : 'Check status'} <Search size={17} aria-hidden="true" />
        </button>
      </form>
      {error && (
        <p className="pub-track-error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="pub-card pub-track-result" ref={resultRef} tabIndex={-1} aria-live="polite">
          <div className="pub-track-top">
            <div>
              <small>
                {result.kind} · {result.number}
              </small>
              <h3>{result.title}</h3>
            </div>
            <span className={`pub-status ${result.cancelled ? 'is-off' : Number(result.balance_due) > 0 ? 'is-due' : 'is-ok'}`}>
              {result.status_label}
            </span>
          </div>
          {result.steps.length > 0 && !result.cancelled && (
            <ol className="pub-steps">
              {result.steps.map((step) => (
                <li key={step.label} className={`${step.done ? 'is-done' : ''} ${step.current ? 'is-current' : ''}`}>
                  <span className="pub-step-dot" aria-hidden="true">
                    {step.done ? <CheckCircle2 size={18} /> : null}
                  </span>
                  {step.label}
                  {step.current && <span className="visually-hidden"> (current step)</span>}
                </li>
              ))}
            </ol>
          )}
          <dl className="pub-track-money">
            {result.due_date && (
              <div>
                <dt>Ready by</dt>
                <dd>{new Date(`${result.due_date}T12:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}</dd>
              </div>
            )}
            <div>
              <dt>Total</dt>
              <dd>{money(result.total, result.currency)}</dd>
            </div>
            <div>
              <dt>Paid</dt>
              <dd>{money(result.paid, result.currency)}</dd>
            </div>
            <div>
              <dt>Still to pay</dt>
              <dd className={Number(result.balance_due) > 0 ? 'is-due' : ''}>{money(result.balance_due, result.currency)}</dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  )
}
