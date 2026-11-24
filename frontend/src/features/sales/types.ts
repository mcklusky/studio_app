export type PaymentMethod = 'cash' | 'mobile_money' | 'bank_transfer' | 'card' | 'other'

export const PAYMENT_METHODS: [PaymentMethod, string][] = [
  ['cash', 'Cash'],
  ['mobile_money', 'Mobile money'],
  ['bank_transfer', 'Bank transfer'],
  ['card', 'Card'],
  ['other', 'Other'],
]

export interface SalePayment {
  id: string
  number: string
  status: 'posted' | 'reversed'
  method: PaymentMethod
  method_label: string
  reference: string
  amount: string
  amount_tendered: string | null
  change: string | null
  received_at: string
  created_by_name: string
}

export interface SaleLine {
  id: string
  product: string
  variant: string | null
  description: string
  quantity: string
  unit_price: string
  discount: string
  line_total: string
  price_overridden: boolean
}

export interface SaleSummary {
  id: string
  number: string
  status: 'posted' | 'reversed'
  section: string
  section_name: string
  customer: string | null
  customer_name: string
  currency: string
  subtotal: string
  discount_total: string
  total: string
  base_total: string
  paid_amount: string
  balance_due: string
  created_by_name: string
  posted_at: string
}

export interface SaleDetail extends SaleSummary {
  organization_name: string
  customer_phone: string
  line_discount_total: string
  sale_discount: string
  fx_units_per_usd: string
  notes: string
  lines: SaleLine[]
  payments: SalePayment[]
  gross_profit_base?: string
  reversed_at: string | null
  reversed_by_name: string | null
  reversal_reason: string
}

export interface PreviewLine {
  product: string
  variant: string | null
  description: string
  quantity: string
  list_price: string
  unit_price: string
  discount: string
  line_total: string
  available_after: string | null
  stock_ok: boolean
}

export interface SalePreview {
  currency: string
  lines: PreviewLine[]
  subtotal: string
  discount_total: string
  total: string
  base_total: string
  stock_ok: boolean
}
