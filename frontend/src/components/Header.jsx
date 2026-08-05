import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'

// Common header bar shown on every page. Nav dropdowns (project/commodity
// selectors) and the theme switch are added in later phases.
function Header() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/')
  }

  return (
    <header className="app-header">
      <h1>
        <Link to="/">GapFlushRSS</Link>
      </h1>
      <nav className="app-header-nav">
        {user ? (
          <>
            <Link to="/projects">Projects</Link>
            {user.global_role === 'root_admin' && <Link to="/admin">Admin</Link>}
            <span>{user.username}</span>
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
