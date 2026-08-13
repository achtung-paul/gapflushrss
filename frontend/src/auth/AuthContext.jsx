import { createContext, useContext, useEffect, useState } from 'react'
import * as api from '../api/client.js'

const AuthContext = createContext(null)

// Wraps the whole app (see main.jsx) so any component can find out who's
// logged in via useAuth(), without passing user data down through props.
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // True until we've checked whether the session cookie is still valid.
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .fetchCurrentUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  // Returns the raw LoginResult (see api/client.js's login) rather than
  // setting `user` itself -- a "2fa_required"/"enrollment_required"
  // result means the caller isn't logged in yet, so LoginPage needs to
  // see the full result (challenge_token, otpauth_uri/qr_data_uri) to
  // render the next step. Only an "ok" result means there's a user to
  // set here.
  async function login(email, password) {
    const result = await api.login(email, password)
    if (result.status === 'ok') {
      setUser(result.user)
    }
    return result
  }

  // The second half of a 2FA login -- called once the user has entered
  // a code for the challenge login() returned. Always ends in either a
  // logged-in user or a thrown error (see api/auth.py's /2fa/verify),
  // unlike login() there's no partial result to hand back.
  async function completeTwoFactor(challengeToken, code) {
    const loggedInUser = await api.verifyTwoFactor(challengeToken, code)
    setUser(loggedInUser)
    return loggedInUser
  }

  async function logout() {
    await api.logout()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, completeTwoFactor, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth() must be used inside an <AuthProvider>')
  }
  return context
}
