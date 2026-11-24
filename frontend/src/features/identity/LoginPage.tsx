import { useState, type FormEvent } from 'react'
import { ErrorBanner, TextField } from '../../components/Form'
import { useAuth } from './AuthContext'

export function LoginPage() {
  const { signIn } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await signIn(username.trim(), password)
    } catch (err) {
      setError(err)
      setPassword('')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <img className="auth-logo" src="/brand/just-smile-on-dark.png" alt="Just Smile Empire" width="150" height="150" />
      <p className="auth-empire" aria-hidden="true">
        EMPIRE
      </p>
      <form className="auth-card" onSubmit={handleSubmit} noValidate>
        <h1>Sign in</h1>
        <p className="subheading">Use the account your administrator gave you.</p>
        <ErrorBanner error={error} />
        <TextField
          label="Username"
          autoComplete="username"
          autoFocus
          required
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="button button-primary button-block" type="submit" disabled={submitting || !username || !password}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}

export function NoOrganizationPage() {
  const { user, signOut } = useAuth()
  return (
    <main className="auth-page">
      <div className="auth-card">
        <h1>No workspace yet</h1>
        <p className="subheading">
          {user?.display_name}, your account is not linked to a business workspace. Ask the owner or an administrator to add you.
        </p>
        <button className="button button-secondary button-block" onClick={signOut}>
          Sign out
        </button>
      </div>
    </main>
  )
}
