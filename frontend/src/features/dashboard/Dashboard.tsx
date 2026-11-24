import './dashboard.css'
import './overview.css'
import {
  ArrowRight,
  ArrowUpRight,
  Banknote,
  BarChart3,
  Boxes,
  ClipboardList,
  HandCoins,
  PiggyBank,
  Plus,
  ReceiptText,
  TrendingDown,
  TrendingUp,
  Truck,
  Wallet,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useId, useState, type ReactNode } from 'react'
import type { PageKey } from '../../app/AppShell'
import { ErrorBanner } from '../../components/Form'
import { api } from '../../lib/api'
import { formatMoney, initials } from '../../lib/format'
import { useDisplayCurrency } from '../currencies/DisplayCurrency'
import { useAuth } from '../identity/AuthContext'
import { filterParams, periodLabel, ReportFilterBar, useReportFilter } from '../reports/ReportFilters'
import type { ActivityItem, ByCurrency, DashboardData, DayPoint, SectionRow } from '../reports/types'

function greeting() {
  const hour = new Date().getHours()
  return hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
}

/** "LRD 4,000.00 · USD 55.00": what actually changed hands, never added together. */
export function CurrencySplit({ values }: { values?: ByCurrency }) {
  const entries = Object.entries(values ?? {})
  if (entries.length < 2 && !(entries.length === 1 && entries[0][0] !== 'USD')) return null
  return <small className="currency-split">{entries.map(([c, v]) => formatMoney(v, c)).join(' · ')}</small>
}

function Change({ current, previous }: { current: string; previous: string }) {
  const now = Number(current)
  const before = Number(previous)
  if (!before) return <span className="ov-change is-flat">{now ? 'New this period' : 'No change'}</span>
  const pct = ((now - before) / before) * 100
  const up = pct >= 0
  const Icon = up ? TrendingUp : TrendingDown
  return (
    <span className={`ov-change ${up ? 'is-up' : 'is-down'}`}>
      <Icon size={14} aria-hidden="true" />
      {Math.abs(pct).toFixed(pct > -10 && pct < 10 ? 1 : 0)}%<span className="visually-hidden"> {up ? 'up' : 'down'}</span>
      <small>vs previous</small>
    </span>
  )
}

/** LRD/USD amounts as small chips (what actually changed hands, never added together). */
function CurrencyChips({ values }: { values?: ByCurrency }) {
  const entries = Object.entries(values ?? {})
  if (entries.length < 2 && !(entries.length === 1 && entries[0][0] !== 'USD')) return null
  return (
    <span className="ov-chips">
      {entries.map(([c, v]) => (
        <span key={c} className="ov-chip">
          {formatMoney(v, c)}
        </span>
      ))}
    </span>
  )
}

function StatCard({
  label,
  icon: Icon,
  tone,
  value,
  feature,
  bad,
  children,
  onOpen,
}: {
  label: string
  icon: LucideIcon
  tone: string
  value: ReactNode
  feature?: boolean
  bad?: boolean
  children?: ReactNode
  onOpen?: () => void
}) {
  const body = (
    <>
      <span className="ov-card-head">
        <span className={`ov-card-icon tone-${tone}`} aria-hidden="true">
          <Icon size={20} strokeWidth={2} />
        </span>
        <span className="ov-card-label">{label}</span>
        {onOpen && <ArrowUpRight size={18} className="ov-card-go" aria-hidden="true" />}
      </span>
      <strong className={`ov-card-value ${bad ? 'is-bad' : ''}`}>{value}</strong>
      {children && <span className="ov-card-extra">{children}</span>}
    </>
  )
  const className = `ov-card ov-card-${tone} ${feature ? 'is-feature' : ''}`
  return onOpen ? (
    <button type="button" className={`${className} is-link`} onClick={onOpen}>
      {body}
    </button>
  ) : (
    <div className={className}>{body}</div>
  )
}

export function Dashboard({ userName, onNavigate }: { userName: string; onNavigate: (key: PageKey) => void }) {
  const { can } = useAuth()
  const { base, currency } = useDisplayCurrency()
  const [filter, setFilter] = useReportFilter('today')
  const [loaded, setLoaded] = useState<{ filter: typeof filter; data: DashboardData } | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [today] = useState(() => new Intl.DateTimeFormat('en', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date()))
  const data = loaded?.data ?? null
  const loading = loaded?.filter !== filter && !error

  useEffect(() => {
    let live = true
    api
      .get<DashboardData>('/reports/dashboard/', filterParams(filter))
      .then((result) => {
        if (live) {
          setLoaded({ filter, data: result })
          setError(null)
        }
      })
      .catch((err) => {
        if (live) setError(err)
      })
    return () => {
      live = false
    }
  }, [filter])

  const f = data?.figures
  const net = f?.net_profit_base
  const scopeText = data
    ? `${periodLabel(data.period.from, data.period.to)} · ${data.section?.name ?? 'All sections'}${data.branch ? ` · ${data.branch.name}` : ''}`
    : ''
  const hasPeriod = Boolean(f?.cash_collected || f?.expenses || net !== undefined)
  const hasNow = Boolean(data?.receivables || data?.payables || data?.orders || data?.stock)
  const showChart = Boolean(data?.series && data.series.length > 1)
  const showSections = Boolean(data?.by_section && data.by_section.length > 1 && !data.section)

  return (
    <div className={`dashboard ov ${loading && data ? 'is-updating' : ''}`}>
      <section className="ov-hero" aria-label="Summary">
        <svg className="ov-hero-art" viewBox="0 0 400 240" aria-hidden="true" preserveAspectRatio="xMaxYMid slice">
          <circle cx="330" cy="40" r="150" />
          <circle cx="330" cy="40" r="105" />
          <path d="M 250 150 Q 330 215 410 150" />
        </svg>
        <div className="ov-hero-main">
          <p className="ov-eyebrow">{today}</p>
          <h1>
            {greeting()}, <span>{userName.split(' ')[0]}</span>
          </h1>
          <p className="ov-scope">
            {scopeText || 'Loading your numbers…'}
            {loading && data && <span className="loading-dot" aria-label="Updating" />}
          </p>
          <div className="ov-actions">
            {can('sales.create') && (
              <button type="button" className="ov-action is-primary" onClick={() => onNavigate('sales')}>
                <Plus size={16} aria-hidden="true" /> New sale
              </button>
            )}
            {can('orders.create') && (
              <button type="button" className="ov-action" onClick={() => onNavigate('orders')}>
                <ClipboardList size={16} aria-hidden="true" /> New order
              </button>
            )}
            {can('reports.view') && (
              <button type="button" className="ov-action" onClick={() => onNavigate('reports')}>
                <BarChart3 size={16} aria-hidden="true" /> Reports
              </button>
            )}
          </div>
        </div>
        {f?.revenue_base !== undefined && (
          <button type="button" className="ov-revenue" onClick={() => onNavigate('sales')}>
            <span className="ov-revenue-label">Revenue</span>
            <strong>{base(f.revenue_base)}</strong>
            {data?.previous && <Change current={f.revenue_base} previous={data.previous.revenue_base} />}
            <span className="ov-revenue-stats">
              <span>
                <b>{f.sales?.count ?? 0}</b> sale{f.sales?.count === 1 ? '' : 's'}
              </span>
              {f.orders_delivered !== undefined && (
                <span>
                  <b>{f.orders_delivered.count}</b> delivered
                </span>
              )}
              {f.cash_collected && (
                <span>
                  <b>{base(f.cash_collected.base)}</b> cash in
                </span>
              )}
            </span>
          </button>
        )}
      </section>

      <div className="ov-filter">
        <ReportFilterBar filter={filter} onChange={setFilter} compact />
      </div>
      <ErrorBanner error={error} />

      {!data && !error && <OverviewSkeleton />}

      {data && (
        <>
          {hasPeriod && (
            <section className="ov-band" aria-labelledby="band-period">
              <h2 id="band-period" className="ov-band-title">
                This period
              </h2>
              <div className="ov-grid ov-grid-3">
                {f?.cash_collected && (
                  <StatCard
                    label="Cash collected"
                    icon={Banknote}
                    tone="green"
                    value={base(f.cash_collected.base)}
                    onOpen={() => onNavigate('customers')}
                  >
                    <CurrencyChips values={f.cash_collected.by_currency} />
                    <small>Payments and deposits received</small>
                  </StatCard>
                )}
                {f?.expenses && (
                  <StatCard label="Expenses" icon={Wallet} tone="red" value={base(f.expenses.base)} onOpen={() => onNavigate('expenses')}>
                    <CurrencyChips values={f.expenses.by_currency} />
                    <small>{f.expenses.count} recorded</small>
                  </StatCard>
                )}
                {net !== undefined && (
                  <StatCard
                    label="Net profit"
                    icon={PiggyBank}
                    tone="brand"
                    feature
                    value={base(net)}
                    bad={Number(net) < 0}
                    onOpen={can('reports.view') ? () => onNavigate('reports') : undefined}
                  >
                    <small>Gross profit {base(f?.gross_profit_base)} minus expenses</small>
                  </StatCard>
                )}
              </div>
            </section>
          )}

          {hasNow && (
            <section className="ov-band" aria-labelledby="band-now">
              <h2 id="band-now" className="ov-band-title">
                Right now
              </h2>
              <div className="ov-grid ov-grid-4">
                {data.receivables && (
                  <StatCard
                    label="Customers owe you"
                    icon={HandCoins}
                    tone="blue"
                    value={base(data.receivables.base)}
                    onOpen={() => onNavigate('customers')}
                  >
                    <CurrencyChips values={data.receivables.by_currency} />
                    <small>
                      {data.receivables.count} customer{data.receivables.count === 1 ? '' : 's'}
                    </small>
                  </StatCard>
                )}
                {data.payables && (
                  <StatCard
                    label="You owe suppliers"
                    icon={Truck}
                    tone="amber"
                    value={base(data.payables.base)}
                    onOpen={() => onNavigate('suppliers')}
                  >
                    <CurrencyChips values={data.payables.by_currency} />
                    <small>
                      {data.payables.count} supplier{data.payables.count === 1 ? '' : 's'}
                    </small>
                  </StatCard>
                )}
                {data.orders && (
                  <StatCard
                    label="Orders in progress"
                    icon={ClipboardList}
                    tone="violet"
                    value={data.orders.active}
                    onOpen={() => onNavigate('orders')}
                  >
                    <span className="ov-chips">
                      {data.orders.overdue > 0 && <span className="ov-chip is-bad">{data.orders.overdue} overdue</span>}
                      <span className="ov-chip">{data.orders.due_today} due today</span>
                      <span className="ov-chip">{data.orders.due_soon} next 3 days</span>
                    </span>
                  </StatCard>
                )}
                {data.stock && (
                  <StatCard
                    label={data.stock.value_base !== undefined ? 'Stock value' : 'Stock alerts'}
                    icon={Boxes}
                    tone="teal"
                    value={data.stock.value_base !== undefined ? base(data.stock.value_base) : data.stock.low_count + data.stock.out_count}
                    onOpen={() => onNavigate('inventory')}
                  >
                    <span className="ov-chips">
                      {data.stock.out_count > 0 && <span className="ov-chip is-bad">{data.stock.out_count} out of stock</span>}
                      <span className={`ov-chip ${data.stock.low_count ? 'is-warn' : ''}`}>{data.stock.low_count} running low</span>
                    </span>
                  </StatCard>
                )}
              </div>
            </section>
          )}

          {(showChart || showSections) && (
            <div className={`ov-row ${showChart && showSections ? 'ov-row-chart' : ''}`}>
              {showChart && (
                <section className="ov-panel">
                  <div className="ov-panel-head">
                    <div>
                      <h2>Revenue per day</h2>
                      <small>{periodLabel(data.period.from, data.period.to)}</small>
                    </div>
                    <span className="ov-pill">{currency}</span>
                  </div>
                  <AreaChart points={data.series!} />
                </section>
              )}
              {showSections && (
                <section className="ov-panel">
                  <div className="ov-panel-head">
                    <div>
                      <h2>Revenue by section</h2>
                      <small>Share of this period's revenue</small>
                    </div>
                    <span className="ov-pill">{currency}</span>
                  </div>
                  <SectionDonut rows={data.by_section!} wide={!showChart} />
                </section>
              )}
            </div>
          )}

          {(data.recent || (data.receivables && data.receivables.top.length > 0)) && (
            <div className="ov-row ov-row-split">
              {data.recent && (
                <section className="ov-panel">
                  <div className="ov-panel-head">
                    <div>
                      <h2>Recent activity</h2>
                      <small>Latest sales, payments and orders</small>
                    </div>
                    {can('sales.view') && (
                      <button type="button" className="ov-link" onClick={() => onNavigate('sales')}>
                        All sales <ArrowRight size={15} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                  <ActivityTimeline items={data.recent} />
                </section>
              )}
              {data.receivables && data.receivables.top.length > 0 && (
                <section className="ov-panel">
                  <div className="ov-panel-head">
                    <div>
                      <h2>Who owes the most</h2>
                      <small>Unpaid balances by customer</small>
                    </div>
                    <button type="button" className="ov-link" onClick={() => onNavigate('customers')}>
                      All customers <ArrowRight size={15} aria-hidden="true" />
                    </button>
                  </div>
                  <OwedList rows={data.receivables.top} />
                </section>
              )}
            </div>
          )}

          {!hasPeriod && !hasNow && (
            <p className="subheading">Your role has no dashboard figures yet. Ask an administrator if you need access.</p>
          )}
          {(hasPeriod || f?.revenue_base !== undefined) && (
            <details className="basis-note">
              <summary>How these figures are worked out</summary>
              <p>
                {data.basis}
                {f?.gross_profit_base !== undefined &&
                  ' Profit uses weighted-average stock cost; order deposits count as cash, and orders count as revenue when delivered (provisional, pending accountant approval).'}
              </p>
            </details>
          )}
        </>
      )}
    </div>
  )
}

function OverviewSkeleton() {
  return (
    <div className="ov-skeleton" aria-busy="true">
      <span className="visually-hidden">Loading…</span>
      {Array.from({ length: 3 }, (_, i) => (
        <span key={i} className="ov-skeleton-card" aria-hidden="true" />
      ))}
    </div>
  )
}

/** Single-series area chart: one hue, 2px line, soft fill, crosshair and tooltip on hover. */
function AreaChart({ points }: { points: DayPoint[] }) {
  const { base } = useDisplayCurrency()
  const gradient = useId()
  const [hover, setHover] = useState<number | null>(null)
  const values = points.map((p) => Number(p.revenue_base))
  const max = Math.max(...values, 0)
  const label = (iso: string) => new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' }).format(new Date(`${iso}T12:00:00`))
  if (max === 0) return <p className="field-hint chart-empty">No revenue recorded in this period.</p>

  const W = 100
  const H = 40
  const x = (i: number) => (points.length === 1 ? W / 2 : (i / (points.length - 1)) * W)
  const y = (v: number) => H - (v / max) * (H - 3) - 0.5
  const line = values.map((v, i) => `${i ? 'L' : 'M'} ${x(i).toFixed(2)} ${y(v).toFixed(2)}`).join(' ')
  const area = `${line} L ${W} ${H} L 0 ${H} Z`
  const ticks = points.length <= 7 ? points.map((_, i) => i) : [0, Math.floor((points.length - 1) / 2), points.length - 1]
  const point = hover !== null ? points[hover] : null

  return (
    <div className="ov-chart" onMouseLeave={() => setHover(null)}>
      <span className="ov-chart-max">{base(max)}</span>
      <div className="ov-chart-plot">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`Revenue per day, highest ${base(max)}`}>
          <defs>
            <linearGradient id={gradient} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#fbbe25" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#fbbe25" stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <line x1="0" x2={W} y1={H / 2} y2={H / 2} className="ov-chart-grid" vectorEffect="non-scaling-stroke" />
          <line x1="0" x2={W} y1={H} y2={H} className="ov-chart-axis" vectorEffect="non-scaling-stroke" />
          <path d={area} fill={`url(#${gradient})`} />
          <path d={line} className="ov-chart-line" vectorEffect="non-scaling-stroke" />
          {hover !== null && (
            <line x1={x(hover)} x2={x(hover)} y1="0" y2={H} className="ov-chart-cross" vectorEffect="non-scaling-stroke" />
          )}
          {points.map((p, i) => (
            <rect
              key={p.date}
              x={x(i) - W / points.length / 2}
              y="0"
              width={W / points.length}
              height={H}
              fill="transparent"
              onMouseEnter={() => setHover(i)}
            />
          ))}
        </svg>
        {hover !== null && (
          <span className="ov-chart-dot" style={{ left: `${x(hover)}%`, top: `${(y(values[hover]) / H) * 100}%` }} aria-hidden="true" />
        )}
      </div>
      <div className="ov-chart-ticks">
        {ticks.map((i) => (
          <span key={i} style={{ left: `${x(i)}%` }}>
            {label(points[i].date)}
          </span>
        ))}
      </div>
      {point && (
        <div className="ov-chart-tip" style={{ left: `${Math.min(Math.max(x(hover!), 14), 86)}%` }} role="status">
          <b>{label(point.date)}</b>
          <span>Revenue {base(point.revenue_base)}</span>
          <span>Cash in {base(point.cash_base)}</span>
        </div>
      )}
    </div>
  )
}

// Section colours from the brand palette, validated all-pairs with dataviz validate_palette.js (legend labels give the required relief for the orange).
const SECTION_COLOR: Record<string, string> = { clothing: '#873307', photography: '#F58F04', printing: '#AF6603' }
const SECTION_FALLBACK = ['#873307', '#F58F04', '#AF6603']

function SectionDonut({ rows, wide }: { rows: SectionRow[]; wide: boolean }) {
  const { base } = useDisplayCurrency()
  const total = rows.reduce((sum, r) => sum + Number(r.revenue_base), 0)
  const sorted = [...rows].sort((a, b) => Number(b.revenue_base) - Number(a.revenue_base))
  const colour = (row: SectionRow, i: number) => SECTION_COLOR[row.code] ?? SECTION_FALLBACK[i % SECTION_FALLBACK.length]
  const R = 42
  const C = 2 * Math.PI * R
  const gap = sorted.filter((r) => Number(r.revenue_base) > 0).length > 1 ? 1.2 : 0
  // Where each segment starts along the ring.
  const starts = sorted.map((_, i) =>
    sorted.slice(0, i).reduce((sum, r) => sum + (total > 0 ? (Number(r.revenue_base) / total) * C : 0), 0),
  )
  return (
    <div className={`ov-donut-wrap ${wide ? 'is-wide' : ''}`}>
      <div className="ov-donut">
        <svg viewBox="0 0 100 100" role="img" aria-label={`Revenue by section, total ${base(String(total))}`}>
          <circle cx="50" cy="50" r={R} className="ov-donut-track" />
          {total > 0 &&
            sorted.map((row, i) => {
              const share = Number(row.revenue_base) / total
              if (share <= 0) return null
              const length = Math.max(share * C - gap, 0.5)
              const dash = `${length} ${C - length}`
              return (
                <circle
                  key={row.id}
                  cx="50"
                  cy="50"
                  r={R}
                  stroke={colour(row, i)}
                  strokeDasharray={dash}
                  strokeDashoffset={-starts[i]}
                  className="ov-donut-seg"
                />
              )
            })}
        </svg>
        <span className="ov-donut-centre">
          <small>Total</small>
          <b>{base(String(total))}</b>
        </span>
      </div>
      <ul className="ov-legend">
        {sorted.map((row, i) => {
          const pct = total > 0 ? (Number(row.revenue_base) / total) * 100 : 0
          return (
            <li key={row.id}>
              <span className="ov-legend-swatch" style={{ background: colour(row, i) }} aria-hidden="true" />
              <span className="ov-legend-name">{row.name}</span>
              <b>{base(row.revenue_base)}</b>
              <small>{pct.toFixed(0)}%</small>
              <span className="ov-legend-bar" aria-hidden="true">
                <span style={{ width: `${pct}%`, background: colour(row, i) }} />
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** "11:26 AM" for today, "Yesterday", otherwise "21 Nov". */
function shortWhen(iso: string) {
  const at = new Date(iso)
  const now = new Date()
  const day = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
  const diff = Math.round((day(now) - day(at)) / 86_400_000)
  if (diff === 0) return at.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
  if (diff === 1) return 'Yesterday'
  return at.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

const ACTIVITY: Record<ActivityItem['kind'], { icon: LucideIcon; tone: string; label: string }> = {
  sale: { icon: ReceiptText, tone: 'blue', label: 'Sale' },
  payment: { icon: Banknote, tone: 'green', label: 'Payment' },
  order: { icon: ClipboardList, tone: 'violet', label: 'New order' },
}

function ActivityTimeline({ items }: { items: ActivityItem[] }) {
  if (!items.length) return <p className="field-hint">Nothing recorded yet.</p>
  return (
    <ol className="ov-timeline">
      {items.map((item) => {
        const kind = ACTIVITY[item.kind]
        const Icon = kind.icon
        return (
          <li
            key={`${item.kind}-${item.id}-${item.number}`}
            className={item.status === 'reversed' || item.status === 'cancelled' ? 'is-reversed' : ''}
          >
            <span className={`ov-timeline-icon tone-${kind.tone}`} aria-hidden="true">
              <Icon size={16} strokeWidth={2.2} />
            </span>
            <span className="ov-timeline-main">
              <b>
                {item.number} <span>· {item.who}</span>
              </b>
              <small>
                {kind.label}
                {item.detail && ` · ${item.detail}`} · {item.section}
              </small>
            </span>
            <span className="ov-timeline-amount">
              <b>{formatMoney(item.amount, item.currency)}</b>
              <small>{shortWhen(item.at)}</small>
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function OwedList({ rows }: { rows: { id: string; name: string; base: string; by_currency?: ByCurrency }[] }) {
  const { base } = useDisplayCurrency()
  const max = Math.max(...rows.map((r) => Number(r.base)), 0)
  return (
    <ol className="ov-owed">
      {rows.map((c, i) => (
        <li key={c.id}>
          <span className={`ov-owed-avatar ${i === 0 ? 'is-top' : ''}`} aria-hidden="true">
            {initials(c.name)}
          </span>
          <span className="ov-owed-main">
            <span className="ov-owed-top">
              <b>{c.name}</b>
              <b className="ov-owed-amount">{base(c.base)}</b>
            </span>
            <span className="ov-owed-bar" aria-hidden="true">
              <span style={{ width: `${max ? (Number(c.base) / max) * 100 : 0}%` }} />
            </span>
            <CurrencyChips values={c.by_currency} />
          </span>
        </li>
      ))}
    </ol>
  )
}
