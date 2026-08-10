import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'
import headerLogoIcon from '../StackFitPro-header-logo.svg'

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
        {/* Points at the marketing site (stackfitpro.com), not the app's
            own "/" route -- unlike every other link in this header, which
            is in-app navigation. Opens in a new tab so it doesn't carry a
            logged-in user away from whatever they were doing.
            StackFitPro-header-logo.svg is icon-only (no baked-in text) --
            deliberately, since an SVG's own fill colours can't respond to
            the light/dark toggle. The "StackFit"/"Pro" text lives in real
            markup instead, so .brand-accent can follow the theme the same
            way every other themed colour in this app does. The icon gets
            alt="" (decorative) since the adjacent text already gives the
            link its accessible name -- a real alt here would just repeat
            it for screen readers. */}
        <a href="https://stackfitpro.com" target="_blank" rel="noopener noreferrer" className="brand-link">
          <img src={headerLogoIcon} alt="" className="brand-logo" />
          StackFit<span className="brand-accent">Pro</span>
        </a>
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
