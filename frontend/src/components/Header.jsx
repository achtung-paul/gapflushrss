import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'

// Common header bar shown on every page. Nav dropdowns (project/commodity
// selectors) are added in a later phase; the light/dark switch below
// covers the other half of Phase 8.
function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light')

  // Applies to <html> (not just this component's own subtree) so every
  // page's CSS -- most of which lives in the global index.css, not
  // component-scoped styles -- sees the same [data-theme] selector.
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  function toggleTheme() {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }

  async function handleLogout() {
    await logout()
    navigate('/')
  }

  return (
    <header className="app-header">
      <h1>
        <Link to="/">
          Gap<span className="brand-accent">Fit Pro</span>
        </Link>
      </h1>
      <nav className="app-header-nav">
        <button type="button" className="theme-toggle" onClick={toggleTheme}>
          {theme === 'dark' ? 'Light mode' : 'Dark mode'}
        </button>
        {user ? (
          <>
            <Link to="/projects">Projects</Link>
            {user.global_role === 'root_admin' && <Link to="/admin">Admin</Link>}
            <span>
              {user.last_name}, {user.first_name}
            </span>
            <button onClick={handleLogout}>Log out</button>
          </>
        ) : (
          <Link to="/login">Log in</Link>
        )}
      </nav>
    </header>
  )
}

export default Header
