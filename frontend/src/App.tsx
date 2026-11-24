import './App.css'
import './app/app.css'
import { AppShell } from './app/AppShell'
import { AuthProvider, useAuth } from './features/identity/AuthContext'
import { LoginPage, NoOrganizationPage } from './features/identity/LoginPage'

function Root() {
  const { status } = useAuth()
  if (status === 'loading')
    return (
      <div className="boot-screen" role="status">
        Loading Just Smile Empire…
      </div>
    )
  if (status === 'signed-out') return <LoginPage />
  if (status === 'no-organization') return <NoOrganizationPage />
  return <AppShell />
}

export default function App() {
  return (
    <AuthProvider>
      <Root />
    </AuthProvider>
  )
}
