import { Calendar, CalendarCheck, CalendarCog, CalendarDays, CalendarFold, CalendarRange, type LucideIcon } from 'lucide-react'
import { MenuSelect } from './MenuSelect'
import { presetRange, type Preset } from '../lib/dates'
import { todayIso } from '../lib/format'

export type RangeChoice = 'any' | Preset
export interface DateRange {
  choice: RangeChoice
  from: string
  to: string
}

export const ANY_DATE: DateRange = { choice: 'any', from: '', to: '' }

const CHOICES: { choice: RangeChoice; text: string; icon: LucideIcon; tone: string }[] = [
  { choice: 'any', text: 'Any date', icon: CalendarRange, tone: 'neutral' },
  { choice: 'today', text: 'Today', icon: CalendarCheck, tone: 'green' },
  { choice: 'week', text: 'This week', icon: CalendarDays, tone: 'blue' },
  { choice: 'month', text: 'This month', icon: Calendar, tone: 'violet' },
  { choice: 'year', text: 'This year', icon: CalendarFold, tone: 'amber' },
  { choice: 'custom', text: 'Choose dates…', icon: CalendarCog, tone: 'olive' },
]

/** Query params for list endpoints that accept ?from=&to= (empty for "Any date"). */
export function rangeParams(range: DateRange) {
  return range.choice === 'any' ? {} : { from: range.from || undefined, to: range.to || undefined }
}

/** Compact date filter for list toolbars: a preset menu (the shared menu style), plus From/To inputs for custom dates. */
export function DateRangeFilter({
  value,
  onChange,
  label = 'Date',
}: {
  value: DateRange
  onChange: (next: DateRange) => void
  label?: string
}) {
  return (
    <>
      <MenuSelect
        variant="pill"
        aria-label={label}
        value={value.choice}
        options={CHOICES.map((c) => ({ value: c.choice, label: c.text, icon: c.icon, tone: c.tone }))}
        onChange={(e) => {
          const choice = e.target.value as RangeChoice
          if (choice === 'any') onChange(ANY_DATE)
          else if (choice === 'custom') onChange({ choice, ...(value.from ? value : presetRange('month')) })
          else onChange({ choice, ...presetRange(choice) })
        }}
      />
      {value.choice === 'custom' && (
        <div className="date-range">
          <label>
            <span className="visually-hidden">{label} from</span>
            <input
              type="date"
              value={value.from}
              max={value.to || todayIso()}
              onChange={(e) => e.target.value && onChange({ ...value, from: e.target.value })}
            />
          </label>
          <span aria-hidden="true">–</span>
          <label>
            <span className="visually-hidden">{label} to</span>
            <input
              type="date"
              value={value.to}
              min={value.from}
              max={todayIso()}
              onChange={(e) => e.target.value && onChange({ ...value, to: e.target.value })}
            />
          </label>
        </div>
      )}
    </>
  )
}
