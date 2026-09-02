import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext.jsx'

// "/" itself has no content of its own -- send the visitor straight to
// wherever they'd end up next anyway (their project list, or the login
// page), same redirect-while-loading pattern as ProtectedRoute.jsx.
function Home() {
  const { user, loading } = useAuth()

  if (loading) {
    return null
  }
  return <Navigate to={user ? '/projects' : '/login'} replace />
}

export default Home
