import './account.css'
import { Building2, Check, ChevronDown, Coins, KeyRound, LogOut, MessagesSquare, ShieldCheck, Smartphone, UserRound } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useDisplayCurrency } from '../features/currencies/DisplayCurrency'
import { useAuth } from '../features/identity/AuthContext'
import { initials } from '../lib/format'

interface Props {
  unreadMessages: number
  onProfile: () => void
  onPassword: () => void
  onMessages: () => void
  onInstall: () => void
  onTeam?: () => void
}

/** The signed-in person's menu at the top right: profile, password, messages, display currency, business and sign out. */
export function AccountMenu({ unreadMessages, onProfile, onPassword, onMessages, onInstall, onTeam }: Props) {
  const { user, organization, signOut, switchOrganization } = useAuth()
  const { currency, setCurrency, lrdPerUsd } = useDisplayCurrency()
  const [open, setOpen] = useState(false)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!user || !organization) return null
  const name = user.display_name
  const pick = (action: () => void) => () => {
    setOpen(false)
    action()
  }

  return (
    <div className="account" ref={box}>
      <button type="button" className="account-trigger" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        <span className="account-avatar" aria-hidden="true">
          {initials(name)}
        </span>
        <span className="account-trigger-text">
          <b>{name}</b>
          <small>{organization.role}</small>
        </span>
        <ChevronDown size={16} className="account-chevron" aria-hidden="true" />
      </button>
      {open && (
        <div className="account-menu" role="menu" aria-label="Account">
          <div className="account-card">
            <span className="account-avatar account-avatar-lg" aria-hidden="true">
              {initials(name)}
            </span>
            <div>
              <b>{name}</b>
              <small>{user.email || `@${user.username}`}</small>
              <span className="account-role">
                {organization.role} · {organization.name}
              </span>
            </div>
          </div>
          <div className="account-group">
            <MenuItem icon={<UserRound size={17} />} tone="blue" onClick={pick(onProfile)}>
              My profile
            </MenuItem>
            <MenuItem icon={<KeyRound size={17} />} tone="amber" onClick={pick(onPassword)}>
              Change password
            </MenuItem>
            <MenuItem icon={<MessagesSquare size={17} />} tone="green" onClick={pick(onMessages)}>
              Messages
              {unreadMessages > 0 && <span className="account-count">{unreadMessages > 99 ? '99+' : unreadMessages}</span>}
            </MenuItem>
            <MenuItem icon={<Smartphone size={17} />} tone="olive" onClick={pick(onInstall)}>
              Get the app on your phone
            </MenuItem>
            {onTeam && (
              <MenuItem icon={<ShieldCheck size={17} />} tone="violet" onClick={pick(onTeam)}>
                Team &amp; access
              </MenuItem>
            )}
          </div>
          <div className="account-group account-setting">
            <span className="account-item-icon tone-olive" aria-hidden="true">
              <Coins size={17} />
            </span>
            <span className="account-setting-label">Show amounts in</span>
            <span className="account-segment" role="radiogroup" aria-label="Show amounts in">
              {(['USD', 'LRD'] as const).map((code) => (
                <button
                  key={code}
                  type="button"
                  role="radio"
                  aria-checked={currency === code}
                  className={currency === code ? 'active' : ''}
                  disabled={code === 'LRD' && !lrdPerUsd}
                  title={code === 'LRD' && !lrdPerUsd ? 'Enter an LRD exchange rate first' : undefined}
                  onClick={() => setCurrency(code)}
                >
                  {code}
                </button>
              ))}
            </span>
          </div>
          {user.organizations.length > 1 && (
            <div className="account-group">
              <p className="account-heading">Switch business</p>
              {user.organizations.map((org) => (
                <MenuItem
                  key={org.id}
                  icon={<Building2 size={17} />}
                  tone="slate"
                  onClick={pick(() => org.id !== organization.id && switchOrganization(org.id))}
                >
                  <span className="account-org">
                    {org.name}
                    <small>{org.role}</small>
                  </span>
                  {org.id === organization.id && <Check size={16} className="account-check" aria-label="Current" />}
                </MenuItem>
              ))}
            </div>
          )}
          <div className="account-group">
            <MenuItem icon={<LogOut size={17} />} tone="red" danger onClick={pick(() => void signOut())}>
              Sign out
            </MenuItem>
          </div>
        </div>
      )}
    </div>
  )
}

function MenuItem({
  icon,
  tone,
  danger,
  onClick,
  children,
}: {
  icon: ReactNode
  tone: string
  danger?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button type="button" role="menuitem" className={`account-item ${danger ? 'is-danger' : ''}`} onClick={onClick}>
      <span className={`account-item-icon tone-${tone}`} aria-hidden="true">
        {icon}
      </span>
      {children}
    </button>
  )
}
