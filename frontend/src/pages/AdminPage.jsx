import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listUsers } from '../api/client.js'

// Only reachable via <ProtectedRoute requireRootAdmin> (see App.jsx) --
// this page existing and loading data is the proof that role-gating works.
function AdminPage() {
  const [users, setUsers] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    listUsers().then(setUsers).catch((err) => setError(err.message))
  }, [])

  return (
    <div>
      <p>
        <Link to="/admin/process-types">Manage process types &amp; tolerance classes</Link>
      </p>
      <h2>Users</h2>
      {error && <p className="form-error">{error}</p>}
      <table>
        <thead>
          <tr>
            <th>Username</th>
            <th>Email</th>
            <th>Role</th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.user_id}>
              <td>{user.username}</td>
              <td>{user.email}</td>
              <td>{user.global_role}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default AdminPage
