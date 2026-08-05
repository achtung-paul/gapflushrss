import { useState } from 'react'
import { requestPasswordReset } from '../api/client.js'

function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    // The backend always returns the same generic message here, whether
    // or not the email is registered, so we don't leak that information.
    const result = await requestPasswordReset(email)
    setMessage(result.message)
  }

  return (
    <div className="page-form">
      <h2>Forgot password</h2>
      <form onSubmit={handleSubmit}>
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <button type="submit">Send reset link</button>
      </form>
      {message && <p>{message}</p>}
    </div>
  )
}

export default ForgotPasswordPage
