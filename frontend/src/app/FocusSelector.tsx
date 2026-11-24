import { MenuSelect } from '../components/MenuSelect'
import { Layers, MapPin } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../lib/api'
import { useAuth } from '../features/identity/AuthContext'

interface Branch {
  id: string
  name: string
}

/**
 * Top-bar "working in" selector. Narrows every list, the dashboard, reports and search to one
 * section and/or branch. Forms still offer every section the person may use, and the server
 * re-checks scope on every request, so this is a view filter, never a permission.
 */
export function FocusSelector({ onChange }: { onChange: () => void }) {
  const { sections, focus, setFocus } = useAuth()
  const [branches, setBranches] = useState<Branch[]>([])
  useEffect(() => {
    api
      .get<Branch[]>('/branches/')
      .then(setBranches)
      .catch(() => setBranches([]))
  }, [])

  if (sections.length < 2 && branches.length < 2) return null
  const change = (key: 'section' | 'branch', value: string) => {
    setFocus({ ...focus, [key]: value })
    onChange()
  }
  return (
    <div className="topbar-focus">
      {sections.length > 1 && (
        <MenuSelect
          variant="subtle"
          icon={Layers}
          className={`toolbar-select${focus.section ? ' active' : ''}`}
          aria-label="Show section"
          title="Show only this section across the app"
          value={focus.section}
          onChange={(e) => change('section', e.target.value)}
        >
          <option value="">All sections</option>
          {sections.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </MenuSelect>
      )}
      {branches.length > 1 && (
        <MenuSelect
          variant="subtle"
          icon={MapPin}
          className={`toolbar-select${focus.branch ? ' active' : ''}`}
          aria-label="Show branch"
          value={focus.branch}
          onChange={(e) => change('branch', e.target.value)}
        >
          <option value="">All branches</option>
          {branches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </MenuSelect>
      )}
    </div>
  )
}
