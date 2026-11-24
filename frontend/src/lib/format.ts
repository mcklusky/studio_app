/** Display helpers. Amounts arrive from the API as decimal strings; we only format them. */

export function formatMoney(value: string | null | undefined, currency = 'USD') {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return value
  return `${currency} ${number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

export function formatQuantity(value: string | null | undefined) {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return value
  return number.toLocaleString('en-US', { maximumFractionDigits: 3 })
}

export function formatDateTime(iso: string) {
  return new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(iso))
}

/** A calendar date (YYYY-MM-DD, no time zone) such as "Tue 1 Dec". */
export function formatDate(isoDate: string, withYear = false) {
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number)
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    ...(withYear ? { year: 'numeric' } : {}),
  }).format(new Date(y, m - 1, d))
}

/** Whole days from today to a YYYY-MM-DD date (negative when past). */
export function daysFromToday(isoDate: string) {
  const [y, m, d] = isoDate.slice(0, 10).split('-').map(Number)
  const now = new Date()
  return Math.round((new Date(y, m - 1, d).getTime() - new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()) / 86_400_000)
}

/** A fresh key per user action, so a retried request is applied at most once. */
export function newIdempotencyKey() {
  // randomUUID needs a secure context (HTTPS/localhost); phones testing over LAN HTTP do not have one.
  if (typeof crypto.randomUUID === 'function' && window.isSecureContext) return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

/** Today's date in the browser's local time zone, as YYYY-MM-DD. */
export function todayIso() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}

/** Up to two initials for an avatar ("Amara Sesay" -> "AS"). */
export function initials(name: string) {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join('') || '?'
  )
}
