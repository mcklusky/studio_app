/** Calendar ranges shared by the report filters and list date filters (browser's local date). */

export type Preset = 'today' | 'week' | 'month' | 'year' | 'custom'

export function isoDate(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Range for a preset, ending today. Weeks start on Monday. 'custom' returns today–today. */
export function presetRange(preset: Preset): { from: string; to: string } {
  const now = new Date()
  const to = isoDate(now)
  if (preset === 'week') {
    const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - ((now.getDay() + 6) % 7))
    return { from: isoDate(monday), to }
  }
  if (preset === 'month') return { from: isoDate(new Date(now.getFullYear(), now.getMonth(), 1)), to }
  if (preset === 'year') return { from: isoDate(new Date(now.getFullYear(), 0, 1)), to }
  return { from: to, to }
}

/** "1 Nov – 24 Nov 2026", or a single day. */
export function periodLabel(from: string, to: string) {
  const parse = (value: string) => {
    const [y, m, d] = value.split('-').map(Number)
    return new Date(y, m - 1, d)
  }
  const long = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
  const short = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' })
  if (from === to) return long.format(parse(from))
  const sameYear = from.slice(0, 4) === to.slice(0, 4)
  return `${(sameYear ? short : long).format(parse(from))} – ${long.format(parse(to))}`
}
