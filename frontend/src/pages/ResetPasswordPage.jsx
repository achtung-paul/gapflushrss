import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { confirmPasswordReset } from '../api/client.js'

function ResetPasswordPage() {
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
        <h2>Password reset</h2>
        <p>
          Your password has been changed. <Link to="/login">Log in</Link>
        </p>
      </div>
    )
  }

  return (
    <div className="page-form">
      <h2>Reset password</h2>
      <form onSubmit={handleSubmit}>
        <label>
          New password
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </label>
        {error && <p className="form-error">{error}</p>}
        <button type="submit">Set new password</button>
      </form>
    </div>
  )
}

export default ResetPasswordPage
