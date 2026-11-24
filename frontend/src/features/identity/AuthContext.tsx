import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, setOrganizationId, setViewFocus } from '../../lib/api'
import type { CurrentUser, OrganizationContext, Section } from './types'

type Status = 'loading' | 'signed-out' | 'no-organization' | 'ready'

interface AuthState {
  status: Status
  user: CurrentUser | null
  organization: OrganizationContext | null
  /** All sections the person may work in (use for forms). */
  sections: Section[]
  /** Sections in the current top-bar focus (use for list and report filters). */
  viewSections: Section[]
  focus: ViewFocus
  setFocus: (next: ViewFocus) => void
  can: (permission: string) => boolean
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  /** Replace the signed-in person's details after they edit their profile. */
  updateUser: (next: CurrentUser) => void
  /** Switch to another organization the person belongs to (reloads the app). */
  switchOrganization: (id: string) => void
}

export interface ViewFocus {
  section: string
  branch: string
}
const NO_FOCUS: ViewFocus = { section: '', branch: '' }

const AuthContext = createContext<AuthState | null>(null)
const ORG_STORAGE_KEY = 'studio.organizationId'
const focusKey = (orgId: string) => `studio.focus.${orgId}`

function applyFocus(orgId: string | null, next: ViewFocus) {
  setViewFocus({ section: next.section || undefined, branch: next.branch || undefined })
  if (orgId) localStorage.setItem(focusKey(orgId), JSON.stringify(next))
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [organization, setOrganization] = useState<OrganizationContext | null>(null)
  const [sections, setSections] = useState<Section[]>([])
  const [focus, setFocusState] = useState<ViewFocus>(NO_FOCUS)

  const loadOrganization = useCallback(async (current: CurrentUser) => {
    setUser(current)
    if (current.organizations.length === 0) {
      setStatus('no-organization')
      return
    }
    // The stored ID only selects among the user's own memberships; the server re-checks it.
    const stored = localStorage.getItem(ORG_STORAGE_KEY)
    const chosen = current.organizations.find((o) => o.id === stored) ?? current.organizations[0]
    setOrganizationId(chosen.id)
    localStorage.setItem(ORG_STORAGE_KEY, chosen.id)
    const [org, sectionList] = await Promise.all([
      api.get<OrganizationContext>('/organization/'),
      api.get<Section[]>('/business-sections/'),
    ])
    // Restore this organization's remembered focus; a section no longer in scope is dropped.
    let saved: ViewFocus = NO_FOCUS
    try {
      saved = { ...NO_FOCUS, ...JSON.parse(localStorage.getItem(focusKey(chosen.id)) ?? '{}') }
    } catch {
      saved = NO_FOCUS
    }
    if (saved.section && !sectionList.some((s) => s.id === saved.section)) saved = { ...saved, section: '' }
    applyFocus(chosen.id, saved)
    setFocusState(saved)
    setOrganization(org)
    setSections(sectionList)
    setStatus('ready')
  }, [])

  useEffect(() => {
    api
      .get<CurrentUser>('/auth/me/')
      .then(loadOrganization)
      .catch(() => setStatus('signed-out'))
  }, [loadOrganization])

  const signIn = useCallback(
    async (username: string, password: string) => {
      const current = await api.post<CurrentUser>('/auth/login/', { username, password })
      await loadOrganization(current)
    },
    [loadOrganization],
  )

  const signOut = useCallback(async () => {
    await api.post('/auth/logout/').catch(() => undefined)
    setOrganizationId(null)
    setViewFocus({})
    setFocusState(NO_FOCUS)
    setUser(null)
    setOrganization(null)
    setSections([])
    setStatus('signed-out')
  }, [])

  const switchOrganization = useCallback((id: string) => {
    localStorage.setItem(ORG_STORAGE_KEY, id)
    window.location.reload()
  }, [])

  const setFocus = useCallback(
    (next: ViewFocus) => {
      applyFocus(organization?.id ?? null, next)
      setFocusState(next)
    },
    [organization],
  )

  const value = useMemo<AuthState>(
    () => ({
      status,
      user,
      organization,
      sections,
      viewSections: focus.section ? sections.filter((s) => s.id === focus.section) : sections,
      focus,
      setFocus,
      can: (permission) => organization?.permissions.includes(permission) ?? false,
      signIn,
      signOut,
      updateUser: setUser,
      switchOrganization,
    }),
    [status, user, organization, sections, focus, setFocus, signIn, signOut, switchOrganization],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used inside AuthProvider')
  return context
}
