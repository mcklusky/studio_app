export type ByCurrency = Record<string, string>

export interface Measure {
  base: string
  count?: number
  by_currency: ByCurrency
}

export interface Figures {
  sales?: Measure
  orders_delivered?: Measure
  revenue_base?: string
  cash_collected?: Measure
  purchases?: Measure
  expenses?: Measure
  cost_of_goods_sold_base?: string
  gross_profit_base?: string
  net_profit_base?: string
}

export interface ReportMeta {
  period: { from: string; to: string; days: number }
  section: { id: string; name: string } | null
  branch: { id: string; name: string } | null
  base_currency: string
  basis: string
}

export interface Debts {
  base: string
  by_currency: ByCurrency
  count: number
  top: { id: string; name: string; base: string; by_currency: ByCurrency }[]
}

export interface SectionRow {
  id: string
  name: string
  code: string
  revenue_base: string
  expenses_base?: string
}
export interface DayPoint {
  date: string
  revenue_base: string
  cash_base: string
}

export interface ActivityItem {
  kind: 'sale' | 'payment' | 'order'
  id: string
  number: string
  at: string
  who: string
  section: string
  detail?: string
  amount: string
  currency: string
  base: string
  status: string
}

export interface DashboardData extends ReportMeta {
  figures: Figures
  previous?: { period: { from: string; to: string }; revenue_base: string; cash_collected_base: string }
  series?: DayPoint[] | null
  by_section?: SectionRow[]
  receivables?: Debts
  payables?: Debts
  stock?: { low_count: number; out_count: number; value_base?: string; basis?: string }
  orders?: { active: number; due_today: number; due_soon: number; overdue: number }
  recent?: ActivityItem[]
}

export interface SummaryData extends ReportMeta {
  definitions: Record<string, string>
  figures: Figures
  previous: { from: string; to: string; figures: Figures }
  by_section: SectionRow[]
  expenses_by_category: { id: string; name: string; base: string }[]
  series: DayPoint[] | null
}
