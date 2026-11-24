import { useState } from 'react'
import { api } from '../../lib/api'
import { formatDateTime, formatMoney, formatQuantity } from '../../lib/format'
import type { SaleDetail } from './types'

/** Customer receipt. Printing hides everything else on the page (see .receipt print rules). */
export function Receipt({ sale }: { sale: SaleDetail }) {
  const c = sale.currency
  const payments = sale.payments.filter((p) => p.status === 'posted')
  return (
    <article className="receipt" aria-label={`Receipt ${sale.number}`}>
      <header className="receipt-head">
        <img className="receipt-logo-screen" src="/brand/just-smile-on-dark.png" alt="" width="76" height="76" />
        <img className="receipt-logo-print" src="/brand/just-smile-ink.png" alt="" width="72" height="72" />
        <h2>{sale.organization_name}</h2>
        <p>Printing Press · Photography &amp; Videography · Clothing</p>
      </header>
      {sale.status === 'reversed' && <p className="receipt-void">VOID: this sale was reversed</p>}
      <dl className="receipt-meta">
        <div>
          <dt>Receipt</dt>
          <dd>{sale.number}</dd>
        </div>
        <div>
          <dt>Date</dt>
          <dd>{formatDateTime(sale.posted_at)}</dd>
        </div>
        <div>
          <dt>Customer</dt>
          <dd>{sale.customer_name}</dd>
        </div>
        <div>
          <dt>Served by</dt>
          <dd>{sale.created_by_name}</dd>
        </div>
      </dl>
      <table className="receipt-lines">
        <tbody>
          {sale.lines.map((line) => (
            <tr key={line.id}>
              <td>
                {line.description}
                <small>
                  {formatQuantity(line.quantity)} × {formatMoney(line.unit_price, c)}
                  {Number(line.discount) > 0 && ` − ${formatMoney(line.discount, c)}`}
                </small>
              </td>
              <td className="num">{formatMoney(line.line_total, c)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <dl className="receipt-totals">
        {Number(sale.discount_total) > 0 && (
          <div>
            <dt>Subtotal</dt>
            <dd>{formatMoney(sale.subtotal, c)}</dd>
          </div>
        )}
        {Number(sale.sale_discount) > 0 && (
          <div>
            <dt>Discount</dt>
            <dd>− {formatMoney(sale.sale_discount, c)}</dd>
          </div>
        )}
        <div className="receipt-grand receipt-total">
          <dt>Total</dt>
          <dd>{formatMoney(sale.total, c)}</dd>
        </div>
        {payments.map((p) => (
          <div key={p.id}>
            <dt>
              Paid · {p.method_label}
              {p.reference && ` (${p.reference})`}
            </dt>
            <dd>{formatMoney(p.amount, c)}</dd>
          </div>
        ))}
        {payments
          .filter((p) => p.amount_tendered)
          .map((p) => (
            <div key={`${p.id}-cash`} className="receipt-sub">
              <dt>Cash given / change</dt>
              <dd>
                {formatMoney(p.amount_tendered, c)} / {formatMoney(p.change, c)}
              </dd>
            </div>
          ))}
        {Number(sale.balance_due) > 0 && sale.status !== 'reversed' && (
          <div className="receipt-grand receipt-due">
            <dt>Balance due</dt>
            <dd>{formatMoney(sale.balance_due, c)}</dd>
          </div>
        )}
        {Number(sale.balance_due) <= 0 && sale.status !== 'reversed' && (
          <div className="receipt-paid">
            <dt>Paid in full</dt>
            <dd>Thank you</dd>
          </div>
        )}
      </dl>
      <footer className="receipt-foot">
        Thank you for choosing Just Smile Empire.
        <b>Keep smiling!</b>
      </footer>
    </article>
  )
}

function receiptText(sale: SaleDetail) {
  const c = sale.currency
  const lines = sale.lines.map((l) => `${formatQuantity(l.quantity)} x ${l.description}  ${formatMoney(l.line_total, c)}`)
  return [
    `${sale.organization_name}: receipt ${sale.number}`,
    formatDateTime(sale.posted_at),
    ...lines,
    `Total: ${formatMoney(sale.total, c)}`,
    `Paid: ${formatMoney(sale.paid_amount, c)}`,
    ...(Number(sale.balance_due) > 0 ? [`Balance due: ${formatMoney(sale.balance_due, c)}`] : []),
    'Thank you for choosing Just Smile Empire!',
  ].join('\n')
}

/** Print, download the server-made PDF (for WhatsApp/email), or share as text via the device's share sheet. */
export function ReceiptActions({ sale }: { sale: SaleDetail }) {
  const [message, setMessage] = useState('')
  const [downloading, setDownloading] = useState(false)

  async function downloadPdf() {
    setDownloading(true)
    setMessage('')
    try {
      await api.download(`/sales/${sale.id}/receipt/`)
    } catch {
      setMessage('The PDF could not be downloaded. Check the connection and try again.')
    } finally {
      setDownloading(false)
    }
  }

  async function share() {
    const text = receiptText(sale)
    try {
      if (navigator.share) {
        await navigator.share({ title: `Receipt ${sale.number}`, text })
        return
      }
      await navigator.clipboard.writeText(text)
      setMessage('Receipt copied. Paste it into WhatsApp, SMS or email.')
    } catch {
      /* the user closed the share sheet */
    }
  }

  return (
    <div className="receipt-actions">
      <button type="button" className="button button-secondary" onClick={() => window.print()}>
        Print
      </button>
      <button type="button" className="button button-secondary" onClick={downloadPdf} disabled={downloading}>
        {downloading ? 'Preparing PDF…' : 'Download PDF'}
      </button>
      <button type="button" className="button button-secondary" onClick={share}>
        Share
      </button>
      {message && (
        <p className="field-hint" role="status">
          {message}
        </p>
      )}
    </div>
  )
}
