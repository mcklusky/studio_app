import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import { formatMoney } from '../../lib/format'
import { useCurrentRates, type CurrentRates } from './ExchangeRate'

/**
 * Display currency for summaries and lists (not for receipts or transaction details,
 * which always show the currency the money actually changed hands in).
 *
 * - Reporting figures are stored in USD (the base currency) and converted to LRD at
 *   today's rate when LRD is selected.
 * - A transaction shown in another currency uses its own saved FX snapshot where
 *   available, and keeps its original amount visible as secondary text.
 */
export type DisplayCode = 'USD' | 'LRD'

interface DisplayCurrencyState {
  currency: DisplayCode
  setCurrency: (code: DisplayCode) => void
  rates: CurrentRates | null
  reloadRates: () => void
  /** LRD per 1 USD in force today, or null when no rate has been entered. */
  lrdPerUsd: number | null
  /** Format a USD base amount in the display currency. */
  base: (usd: string | number | null | undefined) => string
  /** Format a transaction amount; `original` is set when it was converted. */
  txn: (
    amount: string,
    currency: string,
    opts?: { baseAmount?: string | null; unitsPerUsd?: string | null },
  ) => { main: string; original: string | null }
}

const Context = createContext<DisplayCurrencyState | null>(null)
const STORAGE_KEY = 'studio.displayCurrency'

export function DisplayCurrencyProvider({ children }: { children: ReactNode }) {
  const { rates, reload } = useCurrentRates()
  const [chosen, setChosen] = useState<DisplayCode>(() => (localStorage.getItem(STORAGE_KEY) === 'LRD' ? 'LRD' : 'USD'))
  const lrdPerUsd = rates?.rates.LRD ? Number(rates.rates.LRD.units_per_usd) : null
  // Without a rate, LRD cannot be shown honestly: fall back to USD.
  const currency: DisplayCode = chosen === 'LRD' && lrdPerUsd ? 'LRD' : 'USD'

  const setCurrency = useCallback((code: DisplayCode) => {
    setChosen(code)
    localStorage.setItem(STORAGE_KEY, code)
  }, [])

  const value = useMemo<DisplayCurrencyState>(() => {
    const base = (usd: string | number | null | undefined) => {
      if (usd === null || usd === undefined || usd === '') return '—'
      const amount = Number(usd)
      return currency === 'LRD' && lrdPerUsd ? formatMoney(String(amount * lrdPerUsd), 'LRD') : formatMoney(String(amount), 'USD')
    }
    const txn: DisplayCurrencyState['txn'] = (amount, txnCurrency, opts = {}) => {
      if (txnCurrency === currency) return { main: formatMoney(amount, txnCurrency), original: null }
      const original = formatMoney(amount, txnCurrency)
      // Prefer the transaction's own FX snapshot; otherwise today's rate.
      const snapshot = opts.unitsPerUsd ? Number(opts.unitsPerUsd) : null
      let usd: number
      if (txnCurrency === 'USD') usd = Number(amount)
      else if (opts.baseAmount) usd = Number(opts.baseAmount)
      else if (snapshot) usd = Number(amount) / snapshot
      else if (lrdPerUsd) usd = Number(amount) / lrdPerUsd
      else return { main: original, original: null }
      if (currency === 'USD') return { main: `≈ ${formatMoney(String(usd), 'USD')}`, original }
      const rate = txnCurrency === 'USD' ? lrdPerUsd : (snapshot ?? lrdPerUsd)
      return rate ? { main: `≈ ${formatMoney(String(usd * rate), 'LRD')}`, original } : { main: original, original: null }
    }
    return { currency, setCurrency, rates, reloadRates: reload, lrdPerUsd, base, txn }
  }, [currency, setCurrency, rates, reload, lrdPerUsd])

  return <Context.Provider value={value}>{children}</Context.Provider>
}

export function useDisplayCurrency() {
  const context = useContext(Context)
  if (!context) throw new Error('useDisplayCurrency must be used inside DisplayCurrencyProvider')
  return context
}

/** The USD | LRD switch. Every instance controls the same app-wide setting. */
export function CurrencySwitch({ compact = false }: { compact?: boolean }) {
  const { currency, setCurrency, lrdPerUsd } = useDisplayCurrency()
  const rateLabel = lrdPerUsd ? `1 USD = ${lrdPerUsd.toLocaleString('en-US', { maximumFractionDigits: 4 })} LRD` : 'No LRD rate set yet'
  return (
    <div className={`currency-switch ${compact ? 'currency-switch-compact' : ''}`}>
      <div className="segmented-tabs" role="radiogroup" aria-label="Show amounts in">
        {(['USD', 'LRD'] as const).map((code) => (
          <button
            key={code}
            type="button"
            role="radio"
            aria-checked={currency === code}
            className={currency === code ? 'active' : ''}
            disabled={code === 'LRD' && !lrdPerUsd}
            title={code === 'LRD' && !lrdPerUsd ? 'Enter an LRD exchange rate first' : `Show amounts in ${code}`}
            onClick={() => setCurrency(code)}
          >
            {code}
          </button>
        ))}
      </div>
      {!compact && <small>{currency === 'LRD' ? `Converted at ${rateLabel}` : rateLabel}</small>}
    </div>
  )
}

/** A converted transaction amount with its original underneath when different. */
export function TxnAmount({
  amount,
  currency,
  baseAmount,
  unitsPerUsd,
}: {
  amount: string
  currency: string
  baseAmount?: string | null
  unitsPerUsd?: string | null
}) {
  const { txn } = useDisplayCurrency()
  const { main, original } = txn(amount, currency, { baseAmount, unitsPerUsd })
  return (
    <>
      {main}
      {original && <small className="cell-sub">{original}</small>}
    </>
  )
}
