import { Toast } from '../components/Feedback'
import {
  BarChart3,
  Boxes,
  ClipboardList,
  Globe,
  LayoutDashboard,
  MessagesSquare,
  Package,
  ReceiptText,
  ShieldCheck,
  ShoppingBag,
  Truck,
  Users,
  Wallet,
  type LucideIcon,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { ProductsPage } from '../features/catalog/ProductsPage'
import { ChatPanel, useConversations } from '../features/chat/ChatPanel'
import { ContactsPage, CUSTOMERS, SUPPLIERS } from '../features/contacts/ContactsPage'
import { Dashboard } from '../features/dashboard/Dashboard'
import { DisplayCurrencyProvider } from '../features/currencies/DisplayCurrency'
import { useAuth } from '../features/identity/AuthContext'
import { ExpensesPage } from '../features/expenses/ExpensesPage'
import { InventoryPage } from '../features/inventory/InventoryPage'
import { OrdersPage } from '../features/orders/OrdersPage'
import { PurchasesPage } from '../features/purchasing/PurchasesPage'
import { ReportsPage } from '../features/reports/ReportsPage'
import { TeamPage } from '../features/staff/TeamPage'
import { WebsitePage } from '../features/website/WebsitePage'
import { ChangePasswordDialog } from '../features/identity/ChangePassword'
import { InstallAppDialog } from '../features/identity/InstallApp'
import { ProfileDialog } from '../features/identity/ProfileDialog'
import { AlertsBell } from '../features/notifications/AlertsBell'
import { GlobalSearch } from '../features/search/GlobalSearch'
import { initials } from '../lib/format'
import { AccountMenu } from './AccountMenu'
import { FocusSelector } from './FocusSelector'
import { MobileNav } from './MobileNav'
import type { Focus } from './focus'
import { SalesPage } from '../features/sales/SalesPage'

export type PageKey =
  | 'overview'
  | 'sales'
  | 'orders'
  | 'products'
  | 'inventory'
  | 'customers'
  | 'suppliers'
  | 'purchases'
  | 'expenses'
  | 'reports'
  | 'team'
  | 'website'

interface NavEntry {
  key: PageKey
  label: string
  icon: LucideIcon
  group: 'WORKSPACE' | 'MANAGE' | 'INSIGHTS'
  /** Shown when the role holds any of these. */
  permission: string | string[]
}

// Each entry is shown only when the signed-in role holds its view permission.
// The server enforces the same rules; hiding is a convenience, not the control.
const NAV: NavEntry[] = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard, group: 'WORKSPACE', permission: 'dashboard.view' },
  { key: 'sales', label: 'Sales', icon: ReceiptText, group: 'WORKSPACE', permission: 'sales.view' },
  { key: 'orders', label: 'Orders', icon: ClipboardList, group: 'WORKSPACE', permission: 'orders.view' },
  { key: 'products', label: 'Products', icon: Package, group: 'MANAGE', permission: 'catalog.view' },
  { key: 'inventory', label: 'Inventory', icon: Boxes, group: 'MANAGE', permission: 'inventory.view' },
  { key: 'customers', label: 'Customers', icon: Users, group: 'MANAGE', permission: 'customers.view' },
  { key: 'suppliers', label: 'Suppliers', icon: Truck, group: 'MANAGE', permission: 'suppliers.view' },
  { key: 'purchases', label: 'Purchases', icon: ShoppingBag, group: 'MANAGE', permission: 'purchases.view' },
  { key: 'expenses', label: 'Expenses', icon: Wallet, group: 'MANAGE', permission: 'expenses.view' },
  { key: 'website', label: 'Website', icon: Globe, group: 'MANAGE', permission: 'website.manage' },
  { key: 'reports', label: 'Reports', icon: BarChart3, group: 'INSIGHTS', permission: 'reports.view' },
  { key: 'team', label: 'Team & access', icon: ShieldCheck, group: 'INSIGHTS', permission: ['staff.manage', 'audit.view'] },
]

export function AppShell() {
  const { user, organization, can } = useAuth()
  const visible = NAV.filter((entry) => [entry.permission].flat().some((code) => can(code)))
  const [view, setView] = useState<{ page: PageKey; focus?: Focus; nonce: number }>({ page: visible[0]?.key ?? 'overview', nonce: 0 })
  const active = view.page
  // Opening a page (optionally at a record or search) remounts it, so each page reads its focus as initial state.
  const navigate = (page: PageKey, focus?: Focus) => setView((v) => ({ page, focus, nonce: v.nonce + 1 }))
  const [notice, setNotice] = useState('')
  const [dialog, setDialog] = useState<'password' | 'profile' | 'install' | null>(null)
  const [chatOpen, setChatOpen] = useState(false)
  const chat = useConversations(chatOpen)

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 4000)
    return () => window.clearTimeout(timer)
  }, [notice])

  if (!user || !organization) return null
  const current = visible.find((entry) => entry.key === active) ?? visible[0]
  const displayName = user.display_name
  const openFrom = (page: PageKey, focus: Focus) => {
    if (visible.some((e) => e.key === page)) navigate(page, focus)
  }

  return (
    <DisplayCurrencyProvider>
      <div className="app-shell">
        <aside className="sidebar">
          <button className="brand brand-button" onClick={() => navigate('overview')}>
            <img className="brand-logo" src="/brand/just-smile-on-dark.png" alt="" width="40" height="40" />
            <span>
              Just Smile<small className="brand-empire">EMPIRE</small>
            </span>
          </button>
          <div className="workspace-switch" aria-label="Current workspace">
            <span className="workspace-avatar">{initials(organization.name)[0]}</span>
            <span className="workspace-copy">
              <b>{organization.name}</b>
              <small>{organization.role}</small>
            </span>
          </div>
          <nav className="nav-scroll" aria-label="Main">
            {(['WORKSPACE', 'MANAGE', 'INSIGHTS'] as const).map((group) => {
              const entries = visible.filter((entry) => entry.group === group)
              if (!entries.length) return null
              return (
                <div key={group}>
                  <p className="nav-heading">{group}</p>
                  {entries.map((entry) => {
                    const Icon = entry.icon
                    return (
                      <button
                        key={entry.key}
                        className={`nav-item ${current?.key === entry.key ? 'selected' : ''}`}
                        aria-current={current?.key === entry.key ? 'page' : undefined}
                        title={entry.label}
                        onClick={() => navigate(entry.key)}
                      >
                        <span className="nav-icon" aria-hidden="true">
                          <Icon size={18} strokeWidth={2} />
                        </span>
                        {entry.label}
                      </button>
                    )
                  })}
                </div>
              )
            })}
          </nav>
          <div className="sidebar-bottom">
            <button type="button" className="nav-item sidebar-chat" onClick={() => setChatOpen(true)}>
              <span className="nav-icon" aria-hidden="true">
                <MessagesSquare size={18} />
              </span>
              Team chat
              {chat.unread > 0 && <span className="nav-count">{chat.unread > 99 ? '99+' : chat.unread}</span>}
            </button>
          </div>
        </aside>

        <main className="main-content">
          <header className="topbar">
            <button type="button" className="mobile-brand" aria-label="Overview" onClick={() => navigate('overview')}>
              <img src="/brand/just-smile-on-dark.png" alt="" width="34" height="34" />
            </button>
            <div className="breadcrumbs">
              {organization.name} <span>/</span> <b>{current?.label ?? 'Home'}</b>
            </div>
            <GlobalSearch onOpen={openFrom} />
            <FocusSelector onChange={() => navigate(view.page)} />
            <div className="top-actions">
              <button
                type="button"
                className="top-icon"
                aria-label={chat.unread ? `Messages: ${chat.unread} unread` : 'Messages'}
                title="Messages"
                onClick={() => setChatOpen(true)}
              >
                <MessagesSquare size={20} aria-hidden="true" />
                {chat.unread > 0 && (
                  <span className="top-icon-count" aria-hidden="true">
                    {chat.unread > 99 ? '99+' : chat.unread}
                  </span>
                )}
              </button>
              <AlertsBell onOpen={openFrom} />
              <AccountMenu
                unreadMessages={chat.unread}
                onProfile={() => setDialog('profile')}
                onPassword={() => setDialog('password')}
                onMessages={() => setChatOpen(true)}
                onInstall={() => setDialog('install')}
                onTeam={visible.some((e) => e.key === 'team') ? () => navigate('team') : undefined}
              />
            </div>
          </header>
          <div className="page-wrap">
            {!current ? (
              <section className="coming-soon panel">
                <h1>No areas available</h1>
                <p className="subheading">
                  Your role does not include any workspace areas yet. Ask an administrator to update your access.
                </p>
              </section>
            ) : current.key === 'overview' ? (
              <Dashboard key={view.nonce} userName={displayName} onNavigate={(key) => navigate(key)} />
            ) : current.key === 'sales' ? (
              <SalesPage key={view.nonce} notify={setNotice} focus={view.focus} />
            ) : current.key === 'website' ? (
              <WebsitePage key={view.nonce} notify={setNotice} focus={view.focus} />
            ) : current.key === 'team' ? (
              <TeamPage key={view.nonce} notify={setNotice} focus={view.focus} />
            ) : current.key === 'reports' ? (
              <ReportsPage notify={setNotice} />
            ) : current.key === 'orders' ? (
              <OrdersPage key={view.nonce} notify={setNotice} focus={view.focus} />
            ) : current.key === 'customers' ? (
              <ContactsPage key={`customers-${view.nonce}`} kind={CUSTOMERS} notify={setNotice} focus={view.focus} />
            ) : current.key === 'suppliers' ? (
              <ContactsPage key={`suppliers-${view.nonce}`} kind={SUPPLIERS} notify={setNotice} focus={view.focus} />
            ) : current.key === 'expenses' ? (
              <ExpensesPage key={view.nonce} notify={setNotice} focus={view.focus} />
            ) : current.key === 'purchases' ? (
              <PurchasesPage key={view.nonce} notify={setNotice} focus={view.focus} />
            ) : current.key === 'products' ? (
              <ProductsPage key={view.nonce} notify={setNotice} focus={view.focus} />
            ) : (
              <InventoryPage key={view.nonce} notify={setNotice} focus={view.focus} />
            )}
            <footer>Just Smile Empire · Business Manager</footer>
          </div>
        </main>
        <MobileNav
          entries={visible}
          current={current?.key}
          unreadMessages={chat.unread}
          onNavigate={(key) => navigate(key)}
          onChat={() => setChatOpen(true)}
        />
        {dialog === 'password' && (
          <ChangePasswordDialog
            onClose={() => setDialog(null)}
            onDone={() => {
              setDialog(null)
              setNotice('Your password has been changed.')
            }}
          />
        )}
        {dialog === 'profile' && (
          <ProfileDialog
            onClose={() => setDialog(null)}
            onDone={() => {
              setDialog(null)
              setNotice('Your profile has been saved.')
            }}
          />
        )}
        {dialog === 'install' && <InstallAppDialog onClose={() => setDialog(null)} />}
        {chatOpen && <ChatPanel rows={chat.rows} reload={chat.reload} onClose={() => setChatOpen(false)} />}
        {notice && <Toast key={notice} message={notice} onClose={() => setNotice('')} />}
      </div>
    </DisplayCurrencyProvider>
  )
}
