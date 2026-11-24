import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Dialog } from '../../components/Dialog'
import { ErrorBanner, TextField } from '../../components/Form'
import { api, ApiError, type FieldErrors, type Page } from '../../lib/api'
import { formatDateTime, todayIso } from '../../lib/format'
import { useAuth } from '../identity/AuthContext'

export interface CurrentRates {
  date: string
  rates: Record<string, { units_per_usd: string; effective_date: string; is_today: boolean } | null>
}

interface RateEntry {
  id: string
  currency: string
  units_per_usd: string
  effective_date: string
  note: string
  created_by_name: string
  created_at: string
}

export function useCurrentRates() {
  const [rates, setRates] = useState<CurrentRates | null>(null)
  const reload = useCallback(() => {
    api
      .get<CurrentRates>('/exchange-rates/current/')
      .then(setRates)
      .catch(() => setRates(null))
  }, [])
  useEffect(reload, [reload])
  return { rates, reload }
}

function trimRate(value: string) {
  return Number(value).toLocaleString('en-US', { maximumFractionDigits: 4 })
}

/** "1 USD = 190 LRD" with a prompt when today's rate is missing. */
export function RateBanner({ rates, onChanged }: { rates: CurrentRates | null; onChanged: () => void }) {
  const { can } = useAuth()
  const [open, setOpen] = useState(false)
  if (!rates) return null
  const lrd = rates.rates.LRD
  const stale = !lrd || !lrd.is_today
  return (
    <>
      <div className={`rate-banner ${stale ? 'rate-stale' : ''}`}>
        <span>
          {lrd ? (
            <>
              Exchange rate: <b>1 USD = {trimRate(lrd.units_per_usd)} LRD</b>
              {!lrd.is_today && <> (set {lrd.effective_date}; no rate entered today)</>}
            </>
          ) : (
            <>No LRD exchange rate has been entered yet. LRD transactions are blocked until one is set.</>
          )}
        </span>
        {can('fx.manage') && (
          <button className="button button-ghost" onClick={() => setOpen(true)}>
            {stale ? "Set today's rate" : 'Update'}
          </button>
        )}
      </div>
      {open && (
        <RateDialog
          current={lrd?.units_per_usd}
          onClose={() => setOpen(false)}
          onSaved={() => {
            setOpen(false)
            onChanged()
          }}
        />
      )}
    </>
  )
}

function RateDialog({ current, onClose, onSaved }: { current?: string; onClose: () => void; onSaved: () => void }) {
  const [value, setValue] = useState(current ? String(Number(current)) : '')
  const [date, setDate] = useState(todayIso())
  const [note, setNote] = useState('')
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<unknown>(null)
  const [saving, setSaving] = useState(false)
  const [history, setHistory] = useState<RateEntry[]>([])

  useEffect(() => {
    api
      .get<Page<RateEntry>>('/exchange-rates/', { currency: 'LRD', page_size: 10 })
      .then((p) => setHistory(p.results))
      .catch(() => undefined)
  }, [])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!(Number(value) > 0)) {
      setFieldErrors({ units_per_usd: ['Enter how many LRD buy 1 USD.'] })
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      await api.post('/exchange-rates/', { currency: 'LRD', units_per_usd: value, effective_date: date, note: note.trim() })
      onSaved()
    } catch (err) {
      if (err instanceof ApiError) setFieldErrors(err.fieldErrors)
      setError(err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog title="LRD exchange rate" onClose={onClose} onSubmit={handleSubmit}>
      <p className="dialog-lead">
        Applies to new transactions from the chosen date. Recorded transactions keep the rate they were saved with.
      </p>
      <ErrorBanner error={error} />
      <div className="field-row">
        <TextField
          label="LRD per 1 USD"
          inputMode="decimal"
          autoFocus
          value={value}
          onChange={(e) => setValue(e.target.value)}
          error={fieldErrors.units_per_usd}
        />
        <TextField
          label="Effective from"
          type="date"
          value={date}
          onChange={(e) => setDate(e.target.value)}
          error={fieldErrors.effective_date}
        />
      </div>
      <TextField
        label="Source / note (optional)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="e.g. Central bank midday rate"
      />
      {history.length > 0 && (
        <div className="mini-history">
          <p className="field-hint">Recent rates</p>
          <ul>
            {history.map((r) => (
              <li key={r.id}>
                <b>{trimRate(r.units_per_usd)}</b> from {r.effective_date}
                <small>
                  {r.created_by_name} · {formatDateTime(r.created_at)}
                  {r.note && ` · ${r.note}`}
                </small>
              </li>
            ))}
          </ul>
        </div>
      )}
      <div className="dialog-actions">
        <button type="button" className="button button-secondary" onClick={onClose}>
          Cancel
        </button>
        <button type="submit" className="button button-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Save rate'}
        </button>
      </div>
    </Dialog>
  )
}
