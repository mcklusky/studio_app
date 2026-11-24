export type OrderKind = 'photography' | 'printing' | 'clothing'

export const KIND_LABEL: Record<OrderKind, string> = {
  photography: 'Photography',
  printing: 'Printing',
  clothing: 'Clothing',
}

export interface OrderSummary {
  id: string
  number: string
  kind: OrderKind
  kind_label: string
  section: string
  section_name: string
  customer: string
  customer_name: string
  customer_phone: string
  title: string
  status: string
  status_label: string
  step: { index: number | null; count: number; next: { code: string; label: string } | null }
  currency: string
  fx_units_per_usd: string
  total: string
  base_total: string
  paid_amount: string
  balance_due: string
  due_date: string
  overdue: boolean
  shoot_at: string | null
  assigned_to: number | null
  assigned_to_name: string | null
  created_at: string
  delivered_at: string | null
}

export interface ClothingLine {
  size: string
  custom_name: string
  custom_number: string
  quantity: number
}

export interface OrderPayment {
  id: string
  number: string
  status: 'posted' | 'reversed'
  method_label: string
  reference: string
  amount: string
  received_at: string
  created_by_name: string
  reversal_reason: string
}

export interface OrderMaterial {
  id: string
  variant: string
  description: string
  quantity: string
  unit_cost_base?: string
  note: string
  created_by_name: string
  created_at: string
  returned: boolean
  reversal_reason: string
}

export interface OrderDetail extends OrderSummary {
  branch: string
  production_cost: string | null
  notes: string
  created_by_name: string
  cancelled_at: string | null
  cancel_reason: string
  detail: Record<string, string | number | null>
  items: ClothingLine[]
  history: { from: string; to: string; to_label: string; note: string; correction: boolean; actor: string; at: string }[]
  payments: OrderPayment[]
  materials: OrderMaterial[]
  material_cost_base?: string
  flow: { code: string; label: string }[]
}

export interface OrderPage {
  count: number
  next: string | null
  previous: string | null
  results: OrderSummary[]
  counts: { active: number; due_soon: number; overdue: number }
}
