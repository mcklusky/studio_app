import { MenuSelect } from '../../components/MenuSelect'
import { Layers, MapPin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../../lib/api'
import { todayIso } from '../../lib/format'
import { CurrencySwitch } from '../currencies/DisplayCurrency'
import { useAuth } from '../identity/AuthContext'

import { periodLabel, presetRange, type Preset } from '../../lib/dates'

export { periodLabel, presetRange }
export type { Preset }

export interface ReportFilter {
  preset: Preset
  from: string
  to: string
  section: string
  branch: string
}

const PRESETS: [Preset, string][] = [
  ['today', 'Today'],
  ['week', 'This week'],
  ['month', 'This month'],
  ['year', 'This year'],
  ['custom', 'Custom'],
]

export function useReportFilter(initial: Preset = 'today') {
  return useState<ReportFilter>(() => ({ preset: initial, ...presetRange(initial), section: '', branch: '' }))
}

export function filterParams(filter: ReportFilter) {
  return { from: filter.from, to: filter.to, section: filter.section || undefined, branch: filter.branch || undefined }
}

interface Branch {
  id: string
  name: string
}

export function ReportFilterBar({
  filter,
  onChange,
  compact = false,
}: {
  filter: ReportFilter
  onChange: (next: ReportFilter) => void
  /** Overview: no section/branch menus here, because the top-bar selector already sets them. */
  compact?: boolean
}) {
  const { viewSections: sections } = useAuth()
  const [branches, setBranches] = useState<Branch[]>([])
  useEffect(() => {
    api
      .get<Branch[]>('/branches/')
      .then(setBranches)
      .catch(() => setBranches([]))
  }, [])

  return (
    <div className="report-filters">
      <div className="segmented-tabs" role="radiogroup" aria-label="Period">
        {PRESETS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={filter.preset === value}
            className={filter.preset === value ? 'active' : ''}
            onClick={() => onChange({ ...filter, preset: value, ...(value === 'custom' ? {} : presetRange(value)) })}
          >
            {label}
          </button>
        ))}
      </div>
      {filter.preset === 'custom' && (
        <div className="date-range">
          <label>
            <span className="visually-hidden">From</span>
            <input
              type="date"
              value={filter.from}
              max={filter.to}
              onChange={(e) => e.target.value && onChange({ ...filter, from: e.target.value })}
            />
          </label>
          <span aria-hidden="true">–</span>
          <label>
            <span className="visually-hidden">To</span>
            <input
              type="date"
              value={filter.to}
              min={filter.from}
              max={todayIso()}
              onChange={(e) => e.target.value && onChange({ ...filter, to: e.target.value })}
            />
          </label>
        </div>
      )}
      {!compact && sections.length > 1 && (
        <MenuSelect
          variant="pill"
          icon={Layers}
          className="toolbar-select"
          aria-label="Business section"
          value={filter.section}
          onChange={(e) => onChange({ ...filter, section: e.target.value })}
        >
          <option value="">All sections</option>
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </MenuSelect>
      )}
      {!compact && branches.length > 1 && (
        <MenuSelect
          variant="pill"
          icon={MapPin}
          className="toolbar-select"
          aria-label="Branch"
          value={filter.branch}
          onChange={(e) => onChange({ ...filter, branch: e.target.value })}
        >
          <option value="">All branches</option>
          {branches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </MenuSelect>
      )}
      <CurrencySwitch compact />
    </div>
  )
}
