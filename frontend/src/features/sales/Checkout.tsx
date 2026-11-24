import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { ErrorBanner } from '../../components/Form'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { formatMoney, newIdempotencyKey } from '../../lib/format'
import type { Product } from '../catalog/ProductsPage'
import { ContactDialog, CUSTOMERS, type Contact } from '../contacts/ContactsPage'
import { useDisplayCurrency } from '../currencies/DisplayCurrency'
import { RateBanner } from '../currencies/ExchangeRate'
import { useAuth } from '../identity/AuthContext'
import { PAYMENT_METHODS, type PaymentMethod, type SaleDetail, type SalePreview } from './types'

interface CartLine {
  key: string
  product: string
  variant: string | null
  label: string
  quantity: string
  unitPrice: string | null // null = catalog price
  discount: string
}

function optionLabel(product: Product, variant: Product['variants'][number] | null) {
  if (!variant || variant.code === 'default') return product.name
  return `${product.name} · ${[variant.size, variant.color].filter(Boolean).join(' / ') || variant.code}`
}

export function Checkout({ onCancel, onComplete }: { onCancel: () => void; onComplete: (sale: SaleDetail) => void }) {
  const { sections, can } = useAuth()
  const { rates, reloadRates, lrdPerUsd } = useDisplayCurrency()
  const canOverride = can('sales.price_override')
  const [section, setSection] = useState(sections[0]?.id ?? '')
  const [currency, setCurrency] = useState<'USD' | 'LRD'>('USD')
  const [cart, setCart] = useState<CartLine[]>([])
  const [customer, setCustomer] = useState<Contact | null>(null)
  const [saleDiscount, setSaleDiscount] = useState('')
  const [method, setMethod] = useState<PaymentMethod>('cash')
  const [amount, setAmount] = useState<string | null>(null) // null = pay the full total
  const [tendered, setTendered] = useState('')
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')
  const [latestPreview, setPreview] = useState<SalePreview | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [idempotencyKey] = useState(newIdempotencyKey)

  const lrdMissing = currency === 'LRD' && !rates?.rates.LRD
  const items = useMemo(
    () =>
      cart.map((line) => ({
        product: line.product,
        variant: line.variant,
        quantity: line.quantity || '0',
        unit_price: line.unitPrice,
        discount: line.discount || '0',
      })),
    [cart],
  )

  // Server-side pricing preview: the server, not the browser, calculates every amount.
  useEffect(() => {
    if (!cart.length || !section || lrdMissing) return
    const timer = window.setTimeout(() => {
      api
        .post<SalePreview>('/sales/preview/', { section, currency, items, sale_discount: saleDiscount || '0' })
        .then((result) => {
          setPreview(result)
          setFieldErrors({})
          setError(null)
        })
        .catch((err) => {
          setPreview(null)
          if (err instanceof ApiError && Object.keys(err.fieldErrors).length) setFieldErrors(err.fieldErrors)
          else setError(err)
        })
    }, 300)
    return () => window.clearTimeout(timer)
  }, [cart.length, items, section, currency, saleDiscount, lrdMissing])

  // Only show a preview while there is something to price (avoids stale totals after clearing the cart).
  const preview = cart.length && !lrdMissing ? latestPreview : null
  const total = preview ? Number(preview.total) : 0
  const paying = amount === null ? total : Number(amount || 0)
  const balance = Math.max(0, total - paying)
  const change = method === 'cash' && tendered ? Number(tendered) - paying : 0

  function addItem(product: Product, variant: Product['variants'][number] | null) {
    setCart((lines) => {
      const existing = lines.find((l) => l.product === product.id && l.variant === (variant?.id ?? null))
      if (existing) return lines.map((l) => (l === existing ? { ...l, quantity: String(Number(l.quantity || 0) + 1) } : l))
      return [
        ...lines,
        {
          key: newIdempotencyKey(),
          product: product.id,
          variant: variant?.id ?? null,
          label: optionLabel(product, variant),
          quantity: '1',
          unitPrice: null,
          discount: '',
        },
      ]
    })
  }

  const updateLine = (key: string, patch: Partial<CartLine>) =>
    setCart((lines) => lines.map((l) => (l.key === key ? { ...l, ...patch } : l)))
  const removeLine = (key: string) => setCart((lines) => lines.filter((l) => l.key !== key))

  function changeSection(id: string) {
    if (cart.length && !window.confirm('Changing section clears the items in this sale. Continue?')) return
    setSection(id)
    setCart([])
  }

  async function complete(event: FormEvent) {
    event.preventDefault()
    if (!preview) return
    const errors: FieldErrors = {}
    if (paying < 0 || paying > total) errors['payment.amount'] = [`Enter 0 to ${formatMoney(String(total), currency)}.`]
    if (balance > 0 && !customer) errors.customer = ['Choose a customer to leave a balance, or take full payment.']
    if (method === 'cash' && tendered && Number(tendered) < paying)
      errors['payment.amount_tendered'] = ['Cash given is less than the amount paid.']
    if (Object.keys(errors).length) {
      setFieldErrors(errors)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const sale = await api.post<SaleDetail>(
        '/sales/',
        {
          section,
          currency,
          items,
          customer: customer?.id ?? null,
          sale_discount: saleDiscount || '0',
          notes: notes.trim(),
          payment:
            paying > 0
              ? {
                  amount: paying.toFixed(2),
                  method,
                  reference: method === 'cash' ? '' : reference.trim(),
                  amount_tendered: method === 'cash' && tendered ? tendered : null,
                }
              : null,
        },
        idempotencyKey,
      )
      onComplete(sale)
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page checkout">
      <div className="page-header">
        <div>
          <p className="eyebrow">SALES</p>
          <h1>New sale</h1>
        </div>
        <button
          className="button button-secondary"
          onClick={() => {
            if (!cart.length || window.confirm('Discard this sale?')) onCancel()
          }}
        >
          Cancel
        </button>
      </div>
      {currency === 'LRD' && <RateBanner rates={rates} onChanged={reloadRates} />}

      <div className="checkout-grid">
        <section className="panel checkout-items">
          <div className="checkout-controls">
            {sections.length > 1 && (
              <div className="segmented-tabs" role="radiogroup" aria-label="Section">
                {sections.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    role="radio"
                    aria-checked={section === s.id}
                    className={section === s.id ? 'active' : ''}
                    onClick={() => changeSection(s.id)}
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            )}
            <div className="segmented-tabs" role="radiogroup" aria-label="Currency">
              {(['USD', 'LRD'] as const).map((code) => (
                <button
                  key={code}
                  type="button"
                  role="radio"
                  aria-checked={currency === code}
                  className={currency === code ? 'active' : ''}
                  onClick={() => setCurrency(code)}
                >
                  {code}
                </button>
              ))}
            </div>
          </div>

          <ProductPicker section={section} currency={currency} lrdPerUsd={lrdPerUsd} onPick={addItem} />

          {cart.length === 0 ? (
            <p className="checkout-empty">Search or tap a product above to add it.</p>
          ) : (
            <ul className="cart">
              {cart.map((line, index) => {
                const priced = preview?.lines[index]
                const lineErrors = ['quantity', 'unit_price', 'discount', 'variant', 'product'].flatMap(
                  (f) => fieldErrors[`items.${index}.${f}`] ?? [],
                )
                return (
                  <li key={line.key} className={lineErrors.length || priced?.stock_ok === false ? 'cart-line has-error' : 'cart-line'}>
                    <div className="cart-main">
                      <b>{line.label}</b>
                      <small>
                        {priced ? `${formatMoney(priced.unit_price, currency)} each` : '…'}
                        {priced && !priced.stock_ok && (
                          <span className="stock-warn">
                            {' '}
                            · Not enough stock ({Number(priced.available_after) + Number(priced.quantity)} left)
                          </span>
                        )}
                      </small>
                      {lineErrors.length > 0 && <span className="field-error">{lineErrors.join(' ')}</span>}
                    </div>
                    <div className="stepper" aria-label={`Quantity of ${line.label}`}>
                      <button
                        type="button"
                        aria-label="Decrease"
                        onClick={() =>
                          Number(line.quantity) <= 1
                            ? removeLine(line.key)
                            : updateLine(line.key, { quantity: String(Number(line.quantity) - 1) })
                        }
                      >
                        −
                      </button>
                      <input
                        inputMode="decimal"
                        aria-label="Quantity"
                        value={line.quantity}
                        onChange={(e) => updateLine(line.key, { quantity: e.target.value })}
                      />
                      <button
                        type="button"
                        aria-label="Increase"
                        onClick={() => updateLine(line.key, { quantity: String(Number(line.quantity || 0) + 1) })}
                      >
                        +
                      </button>
                    </div>
                    <b className="cart-total">{priced ? formatMoney(priced.line_total, currency) : '—'}</b>
                    <details className="cart-more">
                      <summary>{Number(line.discount) > 0 || line.unitPrice !== null ? 'Price/discount changed' : 'Discount'}</summary>
                      <div className="cart-more-fields">
                        <label>
                          Line discount ({currency})
                          <input
                            inputMode="decimal"
                            value={line.discount}
                            onChange={(e) => updateLine(line.key, { discount: e.target.value })}
                            placeholder="0.00"
                          />
                        </label>
                        {canOverride && (
                          <label>
                            Unit price ({currency})
                            <input
                              inputMode="decimal"
                              value={line.unitPrice ?? priced?.list_price ?? ''}
                              onChange={(e) =>
                                updateLine(line.key, { unitPrice: e.target.value === priced?.list_price ? null : e.target.value })
                              }
                            />
                          </label>
                        )}
                        <button type="button" className="button button-ghost" onClick={() => removeLine(line.key)}>
                          Remove item
                        </button>
                      </div>
                    </details>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <form id="checkout-summary" className="panel checkout-summary" onSubmit={complete} noValidate>
          <ErrorBanner error={error} />
          <CustomerPicker customer={customer} onChange={setCustomer} error={fieldErrors.customer} />

          <dl className="summary-lines">
            <div>
              <dt>Subtotal</dt>
              <dd>{preview ? formatMoney(preview.subtotal, currency) : '—'}</dd>
            </div>
            <div>
              <dt>
                <label htmlFor="sale-discount">Sale discount</label>
              </dt>
              <dd>
                <input
                  id="sale-discount"
                  className="inline-input"
                  inputMode="decimal"
                  placeholder="0.00"
                  value={saleDiscount}
                  onChange={(e) => setSaleDiscount(e.target.value)}
                />
              </dd>
            </div>
            {fieldErrors.sale_discount && <p className="field-error">{fieldErrors.sale_discount.join(' ')}</p>}
            <div className="summary-total">
              <dt>Total</dt>
              <dd>{preview ? formatMoney(preview.total, currency) : '—'}</dd>
            </div>
            {preview && currency === 'LRD' && (
              <div className="summary-sub">
                <dt>In USD</dt>
                <dd>≈ {formatMoney(preview.base_total, 'USD')}</dd>
              </div>
            )}
          </dl>

          <fieldset className="pay-methods">
            <legend>Payment</legend>
            <div className="method-grid">
              {PAYMENT_METHODS.filter(([m]) => m !== 'other').map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={`method ${method === value ? 'active' : ''}`}
                  aria-pressed={method === value}
                  onClick={() => setMethod(value)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="field-row">
              <div className="field">
                <label htmlFor="pay-amount">Amount paid ({currency})</label>
                <input
                  id="pay-amount"
                  inputMode="decimal"
                  value={amount ?? (preview ? preview.total : '')}
                  onChange={(e) => setAmount(e.target.value)}
                />
                {fieldErrors['payment.amount'] && <p className="field-error">{fieldErrors['payment.amount'].join(' ')}</p>}
              </div>
              {method === 'cash' ? (
                <div className="field">
                  <label htmlFor="pay-tendered">Cash given (optional)</label>
                  <input id="pay-tendered" inputMode="decimal" value={tendered} onChange={(e) => setTendered(e.target.value)} />
                  {fieldErrors['payment.amount_tendered'] && (
                    <p className="field-error">{fieldErrors['payment.amount_tendered'].join(' ')}</p>
                  )}
                </div>
              ) : (
                <div className="field">
                  <label htmlFor="pay-ref">Reference (optional)</label>
                  <input id="pay-ref" value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Transaction ID" />
                </div>
              )}
            </div>
            {change > 0 && (
              <p className="change-due">
                Change to give: <b>{formatMoney(String(change), currency)}</b>
              </p>
            )}
            {balance > 0 && preview && (
              <p className="balance-due">
                Balance left on account: <b>{formatMoney(String(balance), currency)}</b>
              </p>
            )}
          </fieldset>

          <div className="field">
            <label htmlFor="sale-notes">Note (optional)</label>
            <input id="sale-notes" value={notes} onChange={(e) => setNotes(e.target.value)} />
          </div>
          <button
            type="submit"
            className="button button-primary button-block button-large"
            disabled={saving || !preview || !preview.stock_ok || lrdMissing}
          >
            {saving ? 'Saving…' : preview ? `Complete sale · ${formatMoney(preview.total, currency)}` : 'Complete sale'}
          </button>
          {preview && !preview.stock_ok && <p className="field-error">Some items do not have enough stock.</p>}
        </form>
      </div>
      {preview && (
        <div className="checkout-jump">
          <span>
            Total <b>{formatMoney(preview.total, currency)}</b> · {cart.length} {cart.length === 1 ? 'item' : 'items'}
          </span>
          <button
            type="button"
            className="button button-primary"
            onClick={() => document.getElementById('checkout-summary')?.scrollIntoView({ behavior: 'smooth' })}
          >
            Payment ↓
          </button>
        </div>
      )}
    </div>
  )
}

function ProductPicker({
  section,
  currency,
  lrdPerUsd,
  onPick,
}: {
  section: string
  currency: 'USD' | 'LRD'
  lrdPerUsd: number | null
  onPick: (p: Product, v: Product['variants'][number] | null) => void
}) {
  // Display hint only; the server preview prices the sale.
  const price = (usd: string) =>
    currency === 'LRD' && lrdPerUsd ? formatMoney(String(Number(usd) * lrdPerUsd), 'LRD') : formatMoney(usd, 'USD')
  const [query, setQuery] = useState('')
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    if (!section) return
    const timer = window.setTimeout(
      () => {
        api
          .get<Page<Product>>('/products/', { section, status: 'active', search: query, page_size: 24 })
          .then((page) => {
            setProducts(page.results)
            setError(null)
          })
          .catch(setError)
      },
      query ? 250 : 0,
    )
    return () => window.clearTimeout(timer)
  }, [section, query])

  return (
    <div className="picker">
      <input
        type="search"
        className="search-input picker-search"
        placeholder="Search products and services"
        aria-label="Search products"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <ErrorBanner error={error} />
      <div className="picker-grid">
        {products.map((product) => {
          const options = product.variants.filter((v) => v.active && v.code !== 'default')
          if (product.tracks_stock && options.length > 1) {
            return (
              <div key={product.id} className="picker-card picker-card-options">
                <span className="picker-name">{product.name}</span>
                <div className="picker-options">
                  {options.map((v) => (
                    <button key={v.id} type="button" onClick={() => onPick(product, v)}>
                      {[v.size, v.color].filter(Boolean).join(' / ') || v.code}
                    </button>
                  ))}
                </div>
              </div>
            )
          }
          const variant = product.tracks_stock ? (options[0] ?? product.variants.find((v) => v.active) ?? null) : null
          return (
            <button key={product.id} type="button" className="picker-card" onClick={() => onPick(product, variant)}>
              {product.image_url && <img className="picker-img" src={product.image_url} alt="" loading="lazy" />}
              <span className="picker-name">{optionLabel(product, variant)}</span>
              <small>
                {price(product.selling_price_base)}
                {product.kind === 'service' ? ' · Service' : ''}
              </small>
            </button>
          )
        })}
        {products.length === 0 && <p className="field-hint">{query ? 'No matching products.' : 'No active products in this section.'}</p>}
      </div>
    </div>
  )
}

export function CustomerPicker({
  customer,
  onChange,
  error,
  required = false,
}: {
  customer: Contact | null
  onChange: (c: Contact | null) => void
  error?: string[]
  required?: boolean
}) {
  const { can } = useAuth()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<Contact[]>([])
  const [adding, setAdding] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (query.trim().length < 2) return
    const timer = window.setTimeout(() => {
      api
        .get<Page<Contact>>('/customers/', { search: query.trim(), page_size: 6 })
        .then((page) => setResults(page.results.filter((c) => c.active)))
        .catch(() => setResults([]))
    }, 250)
    return () => window.clearTimeout(timer)
  }, [query])

  if (customer) {
    return (
      <div className="customer-chosen">
        <span>
          <small>Customer</small>
          <b>{customer.name}</b>
          {customer.phone && <small>{customer.phone}</small>}
        </span>
        <button type="button" className="button button-ghost" onClick={() => onChange(null)}>
          Change
        </button>
      </div>
    )
  }
  return (
    <div className={`field customer-picker ${error ? 'has-error' : ''}`}>
      <label htmlFor="customer-search">Customer {!required && <span className="label-note">(walk-in if left empty)</span>}</label>
      <input
        id="customer-search"
        ref={inputRef}
        type="search"
        autoComplete="off"
        placeholder="Search name or phone"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          if (e.target.value.trim().length < 2) setResults([])
        }}
      />
      {error && <p className="field-error">{error.join(' ')}</p>}
      {(results.length > 0 || query.trim().length >= 2) && (
        <ul className="suggestions" role="listbox">
          {results.map((c) => (
            <li key={c.id}>
              <button
                type="button"
                onClick={() => {
                  onChange(c)
                  setQuery('')
                  setResults([])
                }}
              >
                {c.name}
                {c.phone && <small> · {c.phone}</small>}
              </button>
            </li>
          ))}
          {can('customers.create') && (
            <li>
              <button type="button" className="suggest-add" onClick={() => setAdding(true)}>
                ＋ Add “{query.trim()}” as a new customer
              </button>
            </li>
          )}
        </ul>
      )}
      {adding && (
        <ContactDialog
          kind={CUSTOMERS}
          contact={null}
          initialName={query.trim()}
          onClose={() => setAdding(false)}
          onSaved={(saved) => {
            setAdding(false)
            onChange(saved)
            setQuery('')
            setResults([])
          }}
        />
      )}
    </div>
  )
}
