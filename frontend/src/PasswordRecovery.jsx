import { useState } from 'react'
import { api, json } from './messagingApi'

export default function PasswordRecovery({ route, onReset }) {
  const token =
    new URLSearchParams(route.split('?')[1] || '').get('token') || ''
  const resetting = route.startsWith('reset-password')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  async function submit(event) {
    event.preventDefault()
    if (busy) return
    setError('')
    setMessage('')
    if (resetting && password !== confirmation) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    try {
      const data = await api(
        `/api/auth/${resetting ? 'reset-password' : 'forgot-password'}`,
        json('POST', resetting ? { token, password } : { email }),
      )
      setMessage(data.message)
      if (resetting) {
        setPassword('')
        setConfirmation('')
        onReset?.()
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <a href="#/login">Back to sign in</a>
      <h2>{resetting ? 'Choose a new password' : 'Recover your account'}</h2>
      {message ? (
        <p role="status">{message}</p>
      ) : (
        <form onSubmit={submit}>
          <fieldset disabled={busy}>
            {resetting ? (
              <>
                <label>
                  New password
                  <input
                    aria-label="New password"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </label>
                <label>
                  Confirm new password
                  <input
                    aria-label="Confirm new password"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                    required
                  />
                </label>
              </>
            ) : (
              <label>
                Email address
                <input
                  aria-label="Recovery email address"
                  type="email"
                  autoComplete="email"
                  maxLength={254}
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </label>
            )}
            <button
              className="auth-primary"
              disabled={busy || (resetting && !token)}
            >
              {busy
                ? 'Saving…'
                : resetting
                  ? 'Reset password'
                  : 'Send recovery link'}
            </button>
          </fieldset>
        </form>
      )}
      {resetting && !token && (
        <p role="alert">
          This link is missing its recovery token. Request a new link.
        </p>
      )}
      {error && <p role="alert">{error}</p>}
    </>
  )
}
