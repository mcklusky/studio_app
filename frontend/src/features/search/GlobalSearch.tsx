import './search.css'
import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import type { PageKey } from '../../app/AppShell'
import type { Focus } from '../../app/focus'
import { api } from '../../lib/api'

interface Result {
  id: string
  title: string
  subtitle: string
  query?: string
  date?: string
}
interface Group {
  key: string
  label: string
  page: PageKey
  more: boolean
  results: Result[]
}

/** Top-bar search across every record type the person may see. "/" focuses it. */
export function GlobalSearch({ onOpen }: { onOpen: (page: PageKey, focus: Focus) => void }) {
  const [query, setQuery] = useState('')
  const [groups, setGroups] = useState<Group[]>([])
  const [searched, setSearched] = useState('')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const boxRef = useRef<HTMLDivElement>(null)
  const listId = useId()
  const term = query.trim()
  const flat = term.length >= 2 ? groups.flatMap((g) => g.results.map((r) => ({ group: g, result: r }))) : []

  useEffect(() => {
    if (term.length < 2) return
    let live = true
    const timer = window.setTimeout(() => {
      api
        .get<{ groups: Group[] }>('/search/', { q: term })
        .then((data) => {
          if (live) {
            setGroups(data.groups)
            setSearched(term)
            setActive(0)
          }
        })
        .catch(() => {
          if (live) setGroups([])
        })
    }, 220)
    return () => {
      live = false
      window.clearTimeout(timer)
    }
  }, [term])

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (event.key === '/' && !/input|textarea|select/i.test(target.tagName) && !target.isContentEditable) {
        event.preventDefault()
        inputRef.current?.focus()
      }
    }
    const onClick = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onClick)
    return () => {
      window.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onClick)
    }
  }, [])

  function choose(group: Group, result: Result) {
    // Records with their own detail view open directly; others open their list filtered to them.
    const focus: Focus = ['sales', 'orders', 'purchases'].includes(group.page) ? { id: result.id } : { query: result.query ?? result.title }
    onOpen(group.page, focus)
    setOpen(false)
    setQuery('')
    inputRef.current?.blur()
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Escape') {
      setOpen(false)
      inputRef.current?.blur()
      return
    }
    if (!flat.length) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => (i + 1) % flat.length)
      setOpen(true)
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => (i - 1 + flat.length) % flat.length)
    }
    if (event.key === 'Enter') {
      event.preventDefault()
      const pick = flat[active]
      if (pick) choose(pick.group, pick.result)
    }
  }

  const showPanel = open && term.length >= 2
  const offsets = groups.map((_, gi) => groups.slice(0, gi).reduce((n, g) => n + g.results.length, 0))
  return (
    <div className="global-search" ref={boxRef}>
      <span className="search-icon" aria-hidden="true">
        ⌕
      </span>
      <input
        ref={inputRef}
        type="search"
        role="combobox"
        aria-expanded={showPanel}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showPanel && flat[active] ? `${listId}-${active}` : undefined}
        placeholder="Search customers, receipts, orders…"
        aria-label="Search everything"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
      />
      <kbd className="search-kbd" aria-hidden="true">
        /
      </kbd>
      {showPanel && (
        <div className="search-panel" id={listId} role="listbox" aria-label="Search results">
          {searched !== term && !flat.length ? (
            <p className="search-empty">Searching…</p>
          ) : !flat.length ? (
            <p className="search-empty">Nothing matches “{term}”.</p>
          ) : (
            groups.map((group, gi) => (
              <div key={group.key} role="group" aria-label={group.label}>
                <p className="search-group">{group.label}</p>
                {group.results.map((result, ri) => {
                  const i = offsets[gi] + ri
                  return (
                    <button
                      key={`${group.key}-${result.id}`}
                      id={`${listId}-${i}`}
                      type="button"
                      role="option"
                      aria-selected={i === active}
                      className={`search-result ${i === active ? 'is-active' : ''}`}
                      onMouseEnter={() => setActive(i)}
                      onClick={() => choose(group, result)}
                    >
                      <b>{result.title}</b>
                      <small>{result.subtitle}</small>
                    </button>
                  )
                })}
                {group.more && (
                  <button
                    type="button"
                    className="search-more"
                    onClick={() => {
                      onOpen(group.page, { query: term })
                      setOpen(false)
                      setQuery('')
                    }}
                  >
                    See all {group.label.toLowerCase()} matching “{term}” →
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
