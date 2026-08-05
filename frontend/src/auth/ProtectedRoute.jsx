import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext.jsx'

// Wrap a page with this to require login (and optionally root_admin) to
// view it, e.g.:
//   <ProtectedRoute requireRootAdmin><AdminPage /></ProtectedRoute>
function ProtectedRoute({ children, requireRootAdmin = false }) {
  const { user, loading } = useAuth()

  if (loading) {
    return <p>Loading...</p>
  }
  if (!user) {
    return <Navigate to="/login" replace />
  }
  if (requireRootAdmin && user.global_role !== 'root_admin') {
    return <p>You don't have access to this page.</p>
  }
  return children
}

export default ProtectedRoute
