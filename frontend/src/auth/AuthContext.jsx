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

  async function login(username, password) {
    const loggedInUser = await api.login(username, password)
    setUser(loggedInUser)
  }

  async function logout() {
    await api.logout()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
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
