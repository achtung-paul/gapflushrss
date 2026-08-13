import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createRootAdmin,
  deleteRootAdmin,
  listRootAdmins,
  resendRootAdminInvite,
  resetRootAdmin2fa,
  updateRootAdmin,
} from '../api/client.js'
import { useAuth } from '../auth/AuthContext.jsx'

const USERS_PAGE_SIZE = 25

// Only reachable via <ProtectedRoute requireRootAdmin> (see App.jsx).
// Root admin is an infrastructure operator now, not a superuser -- this
// page only ever shows other root_admin accounts and links to
// infrastructure config. It has no route into any client's users,
// projects, or tolerance matrix -- see api/admin.py and
// CLAUDE.md's tenancy-boundary gotcha. Client sandboxes are managed from
// pages/ClientAdminPage.jsx instead, by that client's own client_admin.
function AdminPage() {
  const { user } = useAuth()
  const [users, setUsers] = useState([])
  const [totalUsers, setTotalUsers] = useState(0)
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [page, setPage] = useState(1)
  const [newFirstName, setNewFirstName] = useState('')
  const [newLastName, setNewLastName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [pendingDeleteUserId, setPendingDeleteUserId] = useState(null)
  const [inviteSentUserId, setInviteSentUserId] = useState(null)
  const [reset2faUserId, setReset2faUserId] = useState(null)
  const [error, setError] = useState(null)

  // Editing an existing user's details (not password -- that's the
  // email-based reset flow) in place, same inline-edit pattern as
  // ProcessTypesPage.jsx.
  const [editingUserId, setEditingUserId] = useState(null)
  const [editFirstName, setEditFirstName] = useState('')
  const [editLastName, setEditLastName] = useState('')
  const [editEmail, setEditEmail] = useState('')

  function refreshUsers() {
    listRootAdmins(searchTerm, page)
      .then((result) => {
        setUsers(result.items)
        setTotalUsers(result.total)
      })
      .catch((err) => setError(err.message))
  }

  // Debounce typing into the search box -- wait for a pause before
  // querying, and jump back to page 1 since the old page number may no
  // longer make sense against the new result set.
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setSearchTerm(searchInput)
      setPage(1)
    }, 300)
    return () => clearTimeout(timeoutId)
  }, [searchInput])

  useEffect(refreshUsers, [searchTerm, page])

  const totalPages = Math.max(1, Math.ceil(totalUsers / USERS_PAGE_SIZE))

  async function handleCreateUser(event) {
    event.preventDefault()
    setError(null)
    try {
      await createRootAdmin(newFirstName, newLastName, newEmail)
      setNewFirstName('')
      setNewLastName('')
      setNewEmail('')
      refreshUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleResendInvite(userId) {
    setError(null)
    try {
      await resendRootAdminInvite(userId)
      setInviteSentUserId(userId)
      setTimeout(() => setInviteSentUserId(null), 4000)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleReset2fa(userId) {
    setError(null)
    try {
      await resetRootAdmin2fa(userId)
      setReset2faUserId(userId)
      setTimeout(() => setReset2faUserId(null), 4000)
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditingUser(u) {
    setEditingUserId(u.user_id)
    setEditFirstName(u.first_name)
    setEditLastName(u.last_name)
    setEditEmail(u.email)
    setError(null)
  }

  async function handleSaveEditUser(userId) {
    setError(null)
    try {
      await updateRootAdmin(userId, editFirstName, editLastName, editEmail)
      setEditingUserId(null)
      refreshUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteUser(userId) {
    setError(null)
    try {
      await deleteRootAdmin(userId)
      setPendingDeleteUserId(null)
      refreshUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <p>
        <Link to="/admin/clients">Clients</Link>
        {' | '}
        <Link to="/admin/postgres-services">Postgres services</Link>
        {' | '}
        <Link to="/admin/minio-services">MinIO services</Link>
        {' | '}
        <Link to="/admin/postgres-servers">Postgres servers</Link>
        {' | '}
        <Link to="/admin/minio-servers">MinIO servers</Link>
        {' | '}
        <Link to="/admin/logs">Service logs</Link>
        {' | '}
        <Link to="/admin/banner">Site banner</Link>
        {' | '}
        <Link to="/admin/security">Two-factor authentication</Link>
      </p>

      <h2>Root admin accounts</h2>
      {error && <p className="form-error">{error}</p>}

      <label>
        Search{' '}
        <input
          type="search"
          placeholder="Search by name or email..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="admin-user-search"
        />
      </label>

      <table>
        <thead>
          <tr>
            <th>First name</th>
            <th>Last name</th>
            <th>Email</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) =>
            editingUserId === u.user_id ? (
              <tr key={u.user_id}>
                <td>
                  <input type="text" value={editFirstName} onChange={(e) => setEditFirstName(e.target.value)} />
                </td>
                <td>
                  <input type="text" value={editLastName} onChange={(e) => setEditLastName(e.target.value)} />
                </td>
                <td>
                  <input type="email" value={editEmail} onChange={(e) => setEditEmail(e.target.value)} />
                </td>
                <td>
                  <button type="button" onClick={() => handleSaveEditUser(u.user_id)}>
                    Save
                  </button>{' '}
                  <button type="button" onClick={() => setEditingUserId(null)}>
                    Cancel
                  </button>
                </td>
              </tr>
            ) : (
              <tr key={u.user_id}>
                <td>{u.first_name}</td>
                <td>{u.last_name}</td>
                <td>{u.email}</td>
                <td>
                  {pendingDeleteUserId === u.user_id ? (
                    <>
                      <span>Delete this user?</span>{' '}
                      <button type="button" onClick={() => handleDeleteUser(u.user_id)}>
                        Yes
                      </button>{' '}
                      <button type="button" onClick={() => setPendingDeleteUserId(null)}>
                        No
                      </button>
                    </>
                  ) : (
                    <>
                      <button type="button" className="link-button" onClick={() => startEditingUser(u)}>
                        Edit
                      </button>{' '}
                      <button type="button" className="link-button" onClick={() => handleResendInvite(u.user_id)}>
                        {inviteSentUserId === u.user_id ? 'Invite sent' : 'Resend invite'}
                      </button>{' '}
                      <button type="button" className="link-button" onClick={() => handleReset2fa(u.user_id)}>
                        {reset2faUserId === u.user_id ? '2FA reset' : 'Reset 2FA'}
                      </button>{' '}
                      {u.user_id !== user?.user_id && (
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => setPendingDeleteUserId(u.user_id)}
                        >
                          Delete
                        </button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ),
          )}
          {users.length === 0 && (
            <tr>
              <td colSpan={4}>No users found.</td>
            </tr>
          )}
        </tbody>
      </table>

      {totalUsers > USERS_PAGE_SIZE && (
        <nav className="pagination-breadcrumb">
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            &larr; Prev
          </button>
          {Array.from({ length: totalPages }, (_, i) => i + 1).map((pageNumber) => (
            <button
              key={pageNumber}
              type="button"
              className={pageNumber === page ? 'pagination-current' : undefined}
              disabled={pageNumber === page}
              onClick={() => setPage(pageNumber)}
            >
              {pageNumber}
            </button>
          ))}
          <button type="button" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Next &rarr;
          </button>
        </nav>
      )}

      <div className="section-divider" />

      <form onSubmit={handleCreateUser} className="inline-form">
        <label>
          First name{' '}
          <input
            type="text"
            placeholder="First name"
            value={newFirstName}
            onChange={(e) => setNewFirstName(e.target.value)}
            required
          />
        </label>
        <label>
          Last name{' '}
          <input
            type="text"
            placeholder="Last name"
            value={newLastName}
            onChange={(e) => setNewLastName(e.target.value)}
            required
          />
        </label>
        <label>
          Email{' '}
          <input
            type="email"
            placeholder="Email"
            value={newEmail}
            onChange={(e) => setNewEmail(e.target.value)}
            required
          />
        </label>
        <button type="submit">Add root admin</button>
      </form>
      <p className="form-hint">
        A new root admin is emailed a link to set their own password -- no password is entered here.
      </p>
    </div>
  )
}

export default AdminPage
