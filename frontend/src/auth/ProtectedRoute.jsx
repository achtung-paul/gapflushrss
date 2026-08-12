import { Navigate } from 'react-router-dom'
import { useAuth } from './AuthContext.jsx'

// Wrap a page with this to require login (and optionally root_admin or
// client_admin) to view it, e.g.:
//   <ProtectedRoute requireRootAdmin><AdminPage /></ProtectedRoute>
//   <ProtectedRoute requireClientAdmin><ClientAdminPage /></ProtectedRoute>
// Deliberately two separate flags rather than one "admin" flag: a root
// admin is NOT a client admin (and vice versa) -- per the brief, root
// admin can never see inside a client's sandbox, so it must be refused
// a client-admin page just as a client admin is refused a root-admin one.
function ProtectedRoute({ children, requireRootAdmin = false, requireClientAdmin = false }) {
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
  if (requireClientAdmin && user.global_role !== 'client_admin') {
    return <p>You don't have access to this page.</p>
  }
  return children
}

export default ProtectedRoute
