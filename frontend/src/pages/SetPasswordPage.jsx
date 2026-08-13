import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { confirmPasswordReset } from '../api/client.js'

// The landing page for a first-time account invite link (see
// core/invites.py, api/auth.py's confirm_password_reset -- the same
// endpoint handles both an invite token and an ordinary "forgot
// password" token, since once the token is presented both mean the same
// thing: this person now controls the password). Deliberately a near
// copy of ResetPasswordPage.jsx rather than sharing one component --
// the wording ("Set up your account" vs "Reset password") is different
// enough, and there's no other logic difference worth abstracting over.
function SetPasswordPage() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') || ''
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState(null)
  const [done, setDone] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    try {
      await confirmPasswordReset(token, newPassword)
      setDone(true)
    } catch (err) {
      setError(err.message)
    }
  }

  if (done) {
    return (
      <div className="page-form">
        <h2>Account set up</h2>
        <p>
          Your password has been set. <Link to="/login">Log in</Link>
        </p>
      </div>
    )
  }

  return (
    <div className="page-form">
      <h2>Set up your account</h2>
      <p className="form-hint">Choose a password to finish setting up your account.</p>
      <form onSubmit={handleSubmit}>
        <label>
          Password
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            minLength={12}
            required
          />
        </label>
        <p className="form-hint">At least 12 characters. Avoid common or previously-breached passwords.</p>
        {error && <p className="form-error">{error}</p>}
        <button type="submit">Set password</button>
      </form>
    </div>
  )
}

export default SetPasswordPage
