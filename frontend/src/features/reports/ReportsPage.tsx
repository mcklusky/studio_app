import '../dashboard/dashboard.css'
import './reports.css'
import { useEffect, useState, type ReactNode } from 'react'
import { EmptyState, ErrorBanner } from '../../components/Form'
import { api } from '../../lib/api'
import { formatMoney, formatQuantity } from '../../lib/format'
import { useDisplayCurrency } from '../currencies/DisplayCurrency'
import { CurrencySplit } from '../dashboard/Dashboard'
import { useAuth } from '../identity/AuthContext'
import { filterParams, periodLabel, ReportFilterBar, useReportFilter } from './ReportFilters'
import type { Debts, Figures, ReportMeta, SummaryData } from './types'

type Tab = 'summary' | 'products' | 'customers' | 'debts' | 'stock'

interface ProductRow {
  product: string
  label: string
  quantity: string
  revenue_base: string
  cost_base?: string
  profit_base?: string
}
interface CustomerRow {
  id: string
  name: string
  revenue_base: string
  transactions: number
}
interface StockRow {
  section: string
  category: string
  quantity: string
  value_base: string
}
type Rows<T> = ReportMeta & { rows: T[] }

const TAB_ICON: Record<Tab, string> = { summary: '◎', products: '★', customers: '♥', debts: '⇄', stock: '▦' }

export function ReportsPage({ notify }: { notify: (message: string) => void }) {
  const { can } = useAuth()
  const [filter, setFilter] = useReportFilter('month')
  const [tab, setTab] = useState<Tab>('summary')
  const [data, setData] = useState<{ tab: Tab; body: unknown } | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [generatedAt, setGeneratedAt] = useState('')
  const [downloading, setDownloading] = useState<'xlsx' | 'pdf' | null>(null)

  async function exportAs(file: 'xlsx' | 'pdf') {
    setDownloading(file)
    setError(null)
    try {
      const name = await api.download(`/reports/${tab}/export/`, { file, ...filterParams(filter) })
      notify(`Downloaded ${name}.`)
    } catch (err) {
      setError(err)
    } finally {
      setDownloading(null)
    }
  }

  const tabs: [Tab, string][] = [
    ['summary', 'Profit & loss'],
    ['products', 'Best sellers'],
    ['customers', 'Best customers'],
    ['debts', 'Debts'],
    ...(can('inventory.costs') ? [['stock', 'Stock value'] as [Tab, string]] : []),
  ]
  const tabLabel = tabs.find(([v]) => v === tab)?.[1] ?? 'Report'

  useEffect(() => {
    let live = true
    api
      .get<unknown>(`/reports/${tab}/`, filterParams(filter))
      .then((body) => {
        if (!live) return
        setData({ tab, body })
        setError(null)
        setGeneratedAt(new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date()))
      })
      .catch((err) => {
        if (live) setError(err)
      })
    return () => {
      live = false
    }
  }, [tab, filter])

  const meta = data?.body as ReportMeta | undefined
  const current = data?.tab === tab ? data.body : null
  const asOfNow = tab === 'debts' || tab === 'stock'

  return (
    <div className="page report-page">
      <section className="dash-hero report-hero">
        <div className="hero-greeting">
          <p className="hero-label">Reports</p>
          <h1>{tabLabel}</h1>
          <p>
            {meta
              ? asOfNow
                ? `As of now · ${meta.section?.name ?? 'All sections'}${meta.branch ? ` · ${meta.branch.name}` : ''}`
                : `${periodLabel(meta.period.from, meta.period.to)} · ${meta.section?.name ?? 'All sections'}${meta.branch ? ` · ${meta.branch.name}` : ''}`
              : 'Loading…'}
          </p>
        </div>
        <div className="hero-actions no-print" role="group" aria-label="Download this report">
          <button className="button hero-button" disabled={!!downloading} onClick={() => void exportAs('xlsx')}>
            {downloading === 'xlsx' ? 'Preparing…' : '⇣ Excel'}
          </button>
          <button className="button hero-button" disabled={!!downloading} onClick={() => void exportAs('pdf')}>
            {downloading === 'pdf' ? 'Preparing…' : '⇣ PDF'}
          </button>
          <button className="button hero-button hero-button-quiet" onClick={() => window.print()}>
            Print
          </button>
        </div>
      </section>

      <div className="no-print">
        <ReportFilterBar filter={filter} onChange={setFilter} />
      </div>
      <div className="report-tabs no-print" role="tablist" aria-label="Report">
        {tabs.map(([value, label]) => (
          <button
            key={value}
            role="tab"
            aria-selected={tab === value}
            className={`report-tab${tab === value ? ' active' : ''}`}
            onClick={() => setTab(value)}
          >
            <span className="report-tab-icon" aria-hidden="true">
              {TAB_ICON[value]}
            </span>
            {label}
          </button>
        ))}
      </div>
      <ErrorBanner error={error} />
      {meta && (
        <p className="print-only report-stamp">
          {tabLabel} · Generated {generatedAt}
        </p>
      )}

      {current !== null && tab === 'summary' && <ProfitAndLoss data={current as SummaryData} />}
      {current !== null && tab === 'products' && <ProductsReport data={current as Rows<ProductRow>} />}
      {current !== null && tab === 'customers' && <CustomersReport data={current as Rows<CustomerRow>} />}
      {current !== null && tab === 'debts' && <DebtsReport data={current as ReportMeta & { receivables?: Debts; payables?: Debts }} />}
      {current !== null && tab === 'stock' && <StockReport data={current as Rows<StockRow> & { value_base?: string }} />}
      {meta && (
        <details className="basis-note">
          <summary>How these figures are worked out</summary>
          <p>
            {meta.basis} Generated {generatedAt}.
          </p>
        </details>
      )}
    </div>
  )
}

// ---------- shared bits ----------

/** "▲ 12%" pill comparing with the previous period. For costs, a rise is shown as bad. */
function Delta({ now, before, costs }: { now?: string; before?: string; costs?: boolean }) {
  const a = Number(now ?? 0)
  const b = Number(before ?? 0)
  if (!b) return <span className="trend trend-flat">{a ? 'New' : '—'}</span>
  const pct = ((a - b) / Math.abs(b)) * 100
  if (Math.abs(pct) < 0.05) return <span className="trend trend-flat">No change</span>
  const up = pct > 0
  const good = costs ? !up : up
  return (
    <span className={`trend ${good ? 'trend-good' : 'trend-bad'}`}>
      {up ? '▲' : '▼'} {Math.abs(pct).toFixed(Math.abs(pct) < 10 ? 1 : 0)}%
    </span>
  )
}

/** Horizontal share bar (value relative to the largest in the list). */
function ShareBar({ value, max, tone = 'olive' }: { value: string | number; max: number; tone?: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (Number(value) / max) * 100)) : 0
  return (
    <span className={`share-bar share-${tone}`} aria-hidden="true">
      <span style={{ width: `${pct}%` }} />
    </span>
  )
}

function Rank({ n }: { n: number }) {
  return <span className={`rank-badge${n <= 3 ? ` rank-${n}` : ''}`}>{n}</span>
}

function Card({
  label,
  icon,
  accent,
  value,
  tone,
  children,
}: {
  label: string
  icon: string
  accent: string
  value: ReactNode
  tone?: 'good' | 'bad'
  children?: ReactNode
}) {
  return (
    <div className={`kpi-tile tile-${accent}`}>
      <span className="tile-head">
        <span className={`tile-icon accent-${accent}`} aria-hidden="true">
          {icon}
        </span>
        <span className="tile-label">{label}</span>
      </span>
      <strong className={`tile-value${tone ? ` tone-${tone}` : ''}`}>{value}</strong>
      {children && <span className="tile-extra">{children}</span>}
    </div>
  )
}

// ---------- profit & loss ----------

function Line({
  label,
  value,
  previous,
  strong,
  grand,
  sub,
  indent,
  negative,
  costs,
  children,
}: {
  label: string
  value?: string
  previous?: string
  strong?: boolean
  grand?: boolean
  sub?: ReactNode
  indent?: boolean
  negative?: boolean
  costs?: boolean
  children?: ReactNode
}) {
  const { base } = useDisplayCurrency()
  const show = (v?: string) => (v === undefined ? '—' : `${negative && Number(v) ? '− ' : ''}${base(v)}`)
  const tone = grand && value !== undefined ? (Number(value) < 0 ? ' pl-negative' : ' pl-positive') : ''
  return (
    <tr className={`${strong ? 'pl-total' : ''}${grand ? ' pl-grand' : ''}${indent ? ' pl-indent' : ''}${tone}`}>
      <th scope="row">
        {label}
        {sub && <small className="cell-sub">{sub}</small>}
        {children}
      </th>
      <td className="num pl-now">{show(value)}</td>
      <td className="num pl-prev hide-mobile">{show(previous)}</td>
      <td className="num pl-change">
        <Delta now={value} before={previous} costs={costs} />
      </td>
    </tr>
  )
}

function margin(part?: string, whole?: string) {
  const w = Number(whole ?? 0)
  return w ? `${((Number(part ?? 0) / w) * 100).toFixed(0)}% margin` : null
}

function ProfitAndLoss({ data }: { data: SummaryData }) {
  const f: Figures = data.figures
  const p: Figures = data.previous.figures
  const { base } = useDisplayCurrency()
  const hasProfit = f.gross_profit_base !== undefined
  const net = Number(f.net_profit_base ?? 0)
  const maxSection = Math.max(0, ...data.by_section.map((s) => Number(s.revenue_base)))
  const totalSection = data.by_section.reduce((sum, s) => sum + Number(s.revenue_base), 0)
  const maxCategory = Math.max(0, ...data.expenses_by_category.map((c) => Number(c.base)))

  return (
    <>
      <div className="kpi-grid">
        {f.revenue_base !== undefined && (
          <Card label="Revenue" icon="↗" accent="yellow" value={base(f.revenue_base)}>
            <span className="status-chips">
              <Delta now={f.revenue_base} before={p.revenue_base} />
              <span className="chip">{(f.sales?.count ?? 0) + (f.orders_delivered?.count ?? 0)} sales &amp; orders</span>
            </span>
          </Card>
        )}
        {hasProfit && (
          <Card label="Gross profit" icon="◑" accent="olive" value={base(f.gross_profit_base)}>
            <span className="status-chips">
              <Delta now={f.gross_profit_base} before={p.gross_profit_base} />
              {margin(f.gross_profit_base, f.revenue_base) && <span className="chip">{margin(f.gross_profit_base, f.revenue_base)}</span>}
            </span>
          </Card>
        )}
        {f.expenses && (
          <Card label="Expenses" icon="↘" accent="red" value={base(f.expenses.base)}>
            <span className="status-chips">
              <Delta now={f.expenses.base} before={p.expenses?.base} costs />
              <span className="chip">{f.expenses.count} recorded</span>
            </span>
          </Card>
        )}
        {hasProfit ? (
          <Card
            label="Net profit"
            icon="◎"
            accent={net < 0 ? 'red' : 'green'}
            value={base(f.net_profit_base)}
            tone={net < 0 ? 'bad' : 'good'}
          >
            <span className="status-chips">
              <Delta now={f.net_profit_base} before={p.net_profit_base} />
              {margin(f.net_profit_base, f.revenue_base) && <span className="chip">{margin(f.net_profit_base, f.revenue_base)}</span>}
            </span>
          </Card>
        ) : (
          f.cash_collected && (
            <Card label="Cash collected" icon="$" accent="green" value={base(f.cash_collected.base)}>
              <Delta now={f.cash_collected.base} before={p.cash_collected?.base} />
            </Card>
          )
        )}
      </div>

      <section className="panel table-panel">
        <div className="report-panel-head">
          <h2>Statement</h2>
          <small>Compared with {periodLabel(data.previous.from, data.previous.to)}</small>
        </div>
        <table className="data-table pl-table">
          <thead>
            <tr>
              <th scope="col">Line</th>
              <th scope="col" className="num">
                This period
              </th>
              <th scope="col" className="num hide-mobile">
                Previous
              </th>
              <th scope="col" className="num">
                Change
              </th>
            </tr>
          </thead>
          <tbody>
            {f.sales && (
              <Line label="Sales" value={f.sales.base} previous={p.sales?.base} sub={`${f.sales.count} sales`}>
                <CurrencySplit values={f.sales.by_currency} />
              </Line>
            )}
            {f.orders_delivered && (
              <Line
                label="Orders delivered"
                value={f.orders_delivered.base}
                previous={p.orders_delivered?.base}
                sub={`${f.orders_delivered.count} orders`}
              >
                <CurrencySplit values={f.orders_delivered.by_currency} />
              </Line>
            )}
            {f.revenue_base !== undefined && <Line label="Revenue" value={f.revenue_base} previous={p.revenue_base} strong />}
            {hasProfit && (
              <Line
                label="Cost of goods sold"
                value={f.cost_of_goods_sold_base}
                previous={p.cost_of_goods_sold_base}
                negative
                indent
                costs
                sub="Weighted-average cost of stock sold or used"
              />
            )}
            {hasProfit && <Line label="Gross profit" value={f.gross_profit_base} previous={p.gross_profit_base} strong />}
            {f.expenses && (
              <Line label="Expenses" value={f.expenses.base} previous={p.expenses?.base} negative indent costs>
                <CurrencySplit values={f.expenses.by_currency} />
              </Line>
            )}
            {data.expenses_by_category.map((c) => (
              <tr key={c.id} className="pl-detail">
                <th scope="row">
                  {c.name}
                  <ShareBar value={c.base} max={maxCategory} tone="red" />
                </th>
                <td className="num">{base(c.base)}</td>
                <td className="hide-mobile" />
                <td />
              </tr>
            ))}
            {hasProfit && <Line label="Net profit" value={f.net_profit_base} previous={p.net_profit_base} strong grand />}
          </tbody>
          <tbody className="pl-memo">
            <tr>
              <th scope="rowgroup" colSpan={4}>
                For information · not part of profit
              </th>
            </tr>
            {f.cash_collected && (
              <Line
                label="Cash collected"
                value={f.cash_collected.base}
                previous={p.cash_collected?.base}
                sub="Payments and deposits received"
              >
                <CurrencySplit values={f.cash_collected.by_currency} />
              </Line>
            )}
            {f.purchases && (
              <Line
                label="Stock purchases"
                value={f.purchases.base}
                previous={p.purchases?.base}
                costs
                sub="Becomes cost when the goods are sold"
              >
                <CurrencySplit values={f.purchases.by_currency} />
              </Line>
            )}
          </tbody>
        </table>
      </section>

      {data.by_section.length > 1 && (
        <section className="panel table-panel">
          <div className="report-panel-head">
            <h2>By section</h2>
            <small>Share of revenue</small>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Section</th>
                <th scope="col" className="num">
                  Revenue
                </th>
                {data.by_section[0].expenses_base !== undefined && (
                  <th scope="col" className="num">
                    Expenses
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {data.by_section.map((s) => (
                <tr key={s.id}>
                  <th scope="row">
                    <span className="row-with-bar">
                      <span>
                        {s.name}
                        <small className="share-pct">
                          {totalSection ? `${((Number(s.revenue_base) / totalSection) * 100).toFixed(0)}%` : '0%'}
                        </small>
                      </span>
                      <ShareBar value={s.revenue_base} max={maxSection} />
                    </span>
                  </th>
                  <td className="num">{base(s.revenue_base)}</td>
                  {s.expenses_base !== undefined && <td className="num">{base(s.expenses_base)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      <details className="definitions-box">
        <summary>What each line means</summary>
        <dl className="definitions">
          {Object.entries(data.definitions).map(([key, text]) => (
            <div key={key}>
              <dt>{key.replace(/_/g, ' ')}</dt>
              <dd>{text}</dd>
            </div>
          ))}
        </dl>
      </details>
    </>
  )
}

// ---------- rankings ----------

function ProductsReport({ data }: { data: Rows<ProductRow> }) {
  const { base } = useDisplayCurrency()
  if (!data.rows.length) return <EmptyState title="No sales in this period" />
  const costs = data.rows[0].profit_base !== undefined
  const max = Math.max(...data.rows.map((r) => Number(r.revenue_base)))
  return (
    <section className="panel table-panel">
      <div className="report-panel-head">
        <h2>Top products</h2>
        <small>By revenue in the period</small>
      </div>
      <table className="data-table rank-table">
        <thead>
          <tr>
            <th scope="col" className="rank-col">
              #
            </th>
            <th scope="col">Product</th>
            <th scope="col" className="num">
              Qty sold
            </th>
            <th scope="col" className="num">
              Revenue
            </th>
            {costs && (
              <>
                <th scope="col" className="num hide-mobile">
                  Cost
                </th>
                <th scope="col" className="num">
                  Gross profit
                </th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r, i) => (
            <tr key={`${r.product}-${r.label}`}>
              <td className="rank-col">
                <Rank n={i + 1} />
              </td>
              <th scope="row">
                <span className="row-with-bar">
                  <span>{r.label}</span>
                  <ShareBar value={r.revenue_base} max={max} />
                </span>
              </th>
              <td className="num">{formatQuantity(r.quantity)}</td>
              <td className="num strong-num">{base(r.revenue_base)}</td>
              {costs && (
                <>
                  <td className="num hide-mobile muted-num">{base(r.cost_base)}</td>
                  <td className="num">
                    <span className={Number(r.profit_base) < 0 ? 'tone-bad' : 'tone-good'}>{base(r.profit_base)}</span>
                    {margin(r.profit_base, r.revenue_base) && <small className="cell-sub">{margin(r.profit_base, r.revenue_base)}</small>}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function CustomersReport({ data }: { data: Rows<CustomerRow> }) {
  const { base } = useDisplayCurrency()
  if (!data.rows.length) return <EmptyState title="No named-customer sales in this period" />
  const max = Math.max(...data.rows.map((r) => Number(r.revenue_base)))
  return (
    <section className="panel table-panel">
      <div className="report-panel-head">
        <h2>Top customers</h2>
        <small>Walk-in sales are not included. Orders count when delivered.</small>
      </div>
      <table className="data-table rank-table">
        <thead>
          <tr>
            <th scope="col" className="rank-col">
              #
            </th>
            <th scope="col">Customer</th>
            <th scope="col" className="num">
              Sales &amp; orders
            </th>
            <th scope="col" className="num">
              Revenue
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rows.map((r, i) => (
            <tr key={r.id}>
              <td className="rank-col">
                <Rank n={i + 1} />
              </td>
              <th scope="row">
                <span className="row-with-bar">
                  <span>{r.name}</span>
                  <ShareBar value={r.revenue_base} max={max} tone="blue" />
                </span>
              </th>
              <td className="num">{r.transactions}</td>
              <td className="num strong-num">{base(r.revenue_base)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

// ---------- debts & stock ----------

function DebtTable({ title, debts, empty, tone }: { title: string; debts: Debts; empty: string; tone: string }) {
  const { base } = useDisplayCurrency()
  const max = Math.max(0, ...debts.top.map((d) => Number(d.base)))
  return (
    <section className="panel table-panel">
      <div className="report-panel-head">
        <h2>{title}</h2>
        <small>
          {debts.count} {debts.count === 1 ? 'account' : 'accounts'}
        </small>
      </div>
      {debts.top.length === 0 ? (
        <p className="all-clear table-foot">✓ {empty}</p>
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col" className="num hide-mobile">
                Owed (original currency)
              </th>
              <th scope="col" className="num">
                USD equivalent
              </th>
            </tr>
          </thead>
          <tbody>
            {debts.top.map((d) => (
              <tr key={d.id}>
                <th scope="row">
                  <span className="row-with-bar">
                    <span>{d.name}</span>
                    <ShareBar value={d.base} max={max} tone={tone} />
                  </span>
                </th>
                <td className="num hide-mobile muted-num">
                  {Object.entries(d.by_currency)
                    .map(([c, v]) => formatMoney(v, c))
                    .join(' · ')}
                </td>
                <td className="num strong-num">{base(d.base)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}

function DebtsReport({ data }: { data: ReportMeta & { receivables?: Debts; payables?: Debts } }) {
  const { base } = useDisplayCurrency()
  return (
    <>
      <div className="kpi-grid kpi-grid-2">
        {data.receivables && (
          <Card label="Customers owe you" icon="⇲" accent="blue" value={base(data.receivables.base)}>
            <CurrencySplit values={data.receivables.by_currency} />
          </Card>
        )}
        {data.payables && (
          <Card label="You owe suppliers" icon="⇱" accent="orange" value={base(data.payables.base)}>
            <CurrencySplit values={data.payables.by_currency} />
          </Card>
        )}
      </div>
      <div className="debts-stack">
        {data.receivables && (
          <DebtTable title="Customers owe you" debts={data.receivables} empty="No customer owes anything." tone="blue" />
        )}
        {data.payables && <DebtTable title="You owe suppliers" debts={data.payables} empty="Nothing is owed to suppliers." tone="orange" />}
      </div>
      <p className="field-hint">Balances as of now; the period does not apply. USD equivalents use each invoice's own exchange rate.</p>
    </>
  )
}

function StockReport({ data }: { data: Rows<StockRow> & { value_base?: string } }) {
  const { base } = useDisplayCurrency()
  if (!data.rows.length) return <EmptyState title="No stock on hand" />
  const max = Math.max(...data.rows.map((r) => Number(r.value_base)))
  const units = data.rows.reduce((sum, r) => sum + Number(r.quantity), 0)
  return (
    <>
      <div className="kpi-grid kpi-grid-2">
        <Card label="Total stock value" icon="▦" accent="purple" value={base(data.value_base)}>
          <small className="tile-sub">At moving weighted-average cost, as of now</small>
        </Card>
        <Card label="Units on hand" icon="#" accent="grey" value={formatQuantity(String(units))}>
          <small className="tile-sub">
            Across {data.rows.length} {data.rows.length === 1 ? 'category' : 'categories'}
          </small>
        </Card>
      </div>
      <section className="panel table-panel">
        <div className="report-panel-head">
          <h2>By category</h2>
          <small>Share of stock value</small>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Category</th>
              <th scope="col" className="hide-mobile">
                Section
              </th>
              <th scope="col" className="num">
                Units
              </th>
              <th scope="col" className="num">
                Value
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={`${r.section}-${r.category}`}>
                <th scope="row">
                  <span className="row-with-bar">
                    <span>{r.category}</span>
                    <ShareBar value={r.value_base} max={max} tone="purple" />
                  </span>
                </th>
                <td className="hide-mobile">{r.section}</td>
                <td className="num">{formatQuantity(r.quantity)}</td>
                <td className="num strong-num">{base(r.value_base)}</td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="pl-total">
              <th scope="row" colSpan={3}>
                Total stock value
              </th>
              <td className="num">{base(data.value_base)}</td>
            </tr>
          </tfoot>
        </table>
      </section>
    </>
  )
}
