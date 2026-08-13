import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'

function LoginPage() {
  const { login, completeTwoFactor } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)

  // Set once login() comes back with anything other than "ok" -- the
  // whole LoginResult (see api/client.js), which is either a
  // "2fa_required" challenge (just need a code) or an
  // "enrollment_required" one (need to scan a QR code first, then enter
  // the code it produces). Its presence is what switches this page from
  // the password form to the code-entry form.
  const [challenge, setChallenge] = useState(null)
  const [code, setCode] = useState('')

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    try {
      const result = await login(email, password)
      if (result.status === 'ok') {
        navigate('/')
        return
      }
      setChallenge(result)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleVerify(event) {
    event.preventDefault()
    setError(null)
    try {
      await completeTwoFactor(challenge.challenge_token, code)
      navigate('/')
    } catch (err) {
      setError(err.message)
    }
  }

  if (challenge) {
    const enrolling = challenge.status === 'enrollment_required'
    return (
      <div className="page-form">
        <h2>{enrolling ? 'Set up two-factor authentication' : 'Enter your authentication code'}</h2>
        {enrolling && (
          <>
            <p className="form-hint">
              Two-factor authentication is now required. Scan this code with an authenticator app
              (Google Authenticator, Authy, 1Password, ...), then enter the 6-digit code it shows
              below.
            </p>
            <img className="totp-qr" src={challenge.qr_data_uri} alt="Two-factor authentication QR code" />
            <p className="form-hint">
              Can&apos;t scan it? Enter this key manually in your authenticator app:{' '}
              <code>{new URL(challenge.otpauth_uri).searchParams.get('secret')}</code>
            </p>
          </>
        )}
        <form onSubmit={handleVerify}>
          <label>
            6-digit code
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              required
              autoFocus
            />
          </label>
          {error && <p className="form-error">{error}</p>}
          <button type="submit">Verify</button>
        </form>
        <p>
          <button type="button" className="link-button" onClick={() => setChallenge(null)}>
            &larr; Back to login
          </button>
        </p>
      </div>
    )
  }

  return (
    <div className="page-form">
      <h2>Log in</h2>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit">Log in</button>
      </form>
      <p>
        <Link to="/forgot-password">Forgot your password?</Link>
      </p>
    </div>
  )
}

export default LoginPage
