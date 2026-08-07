import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  addProjectMember,
  createUser,
  deleteUser,
  listProjectMembers,
  listProjects,
  listUsers,
  removeProjectMember,
} from '../api/client.js'

const GLOBAL_ROLES = ['standard', 'root_admin']
const GROUP_ROLES = ['Managers', 'Contributors', 'Viewers']
const USERS_PAGE_SIZE = 25

// Only reachable via <ProtectedRoute requireRootAdmin> (see App.jsx) --
// this page existing and loading data is the proof that role-gating works.
function AdminPage() {
  const [users, setUsers] = useState([])
  const [totalUsers, setTotalUsers] = useState(0)
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [page, setPage] = useState(1)
  const [newUsername, setNewUsername] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newGlobalRole, setNewGlobalRole] = useState('standard')
  const [pendingDeleteUserId, setPendingDeleteUserId] = useState(null)
  const [error, setError] = useState(null)

  const [projects, setProjects] = useState([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [members, setMembers] = useState([])
  // The "add to group" user picker has its own search -- it can't just
  // reuse `users` above, since that's now only the current page/search
  // of the Users table, not every user in the system.
  const [memberSearchInput, setMemberSearchInput] = useState('')
  const [memberSearchTerm, setMemberSearchTerm] = useState('')
  const [memberOptions, setMemberOptions] = useState([])
  const [newMemberUserId, setNewMemberUserId] = useState('')
  const [newMemberRole, setNewMemberRole] = useState('Contributors')
  // Composite "group_role:user_id" key of the membership awaiting a
  // remove confirmation, or null.
  const [pendingRemoveKey, setPendingRemoveKey] = useState(null)

  function refreshUsers() {
    listUsers(searchTerm, page)
      .then((result) => {
        setUsers(result.items)
        setTotalUsers(result.total)
      })
      .catch((err) => setError(err.message))
  }

  function refreshProjects() {
    listProjects().then(setProjects).catch((err) => setError(err.message))
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
  useEffect(refreshProjects, [])

  const totalPages = Math.max(1, Math.ceil(totalUsers / USERS_PAGE_SIZE))

  useEffect(() => {
    if (projects.length > 0 && selectedProjectId === '') {
      setSelectedProjectId(String(projects[0].project_id))
    }
  }, [projects, selectedProjectId])

  function refreshMembers() {
    if (selectedProjectId === '') {
      setMembers([])
      return
    }
    listProjectMembers(selectedProjectId).then(setMembers).catch((err) => setError(err.message))
  }

  useEffect(refreshMembers, [selectedProjectId])

  // Same debounce-then-fetch pattern as the Users table's search above,
  // just always page 1 -- narrowing by typing is enough for picking one
  // user out of a dropdown, no need for its own breadcrumb.
  useEffect(() => {
    const timeoutId = setTimeout(() => setMemberSearchTerm(memberSearchInput), 300)
    return () => clearTimeout(timeoutId)
  }, [memberSearchInput])

  useEffect(() => {
    listUsers(memberSearchTerm, 1)
      .then((result) => setMemberOptions(result.items))
      .catch((err) => setError(err.message))
  }, [memberSearchTerm])

  async function handleCreateUser(event) {
    event.preventDefault()
    setError(null)
    try {
      await createUser(newUsername, newEmail, newPassword, newGlobalRole)
      setNewUsername('')
      setNewEmail('')
      setNewPassword('')
      setNewGlobalRole('standard')
      refreshUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteUser(userId) {
    setError(null)
    try {
      await deleteUser(userId)
      setPendingDeleteUserId(null)
      refreshUsers()
      refreshMembers()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleAddMember(event) {
    event.preventDefault()
    setError(null)
    if (!newMemberUserId) return
    try {
      await addProjectMember(selectedProjectId, Number(newMemberUserId), newMemberRole)
      setNewMemberUserId('')
      refreshMembers()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleRemoveMember(groupRole, userId) {
    setError(null)
    try {
      await removeProjectMember(selectedProjectId, groupRole, userId)
      setPendingRemoveKey(null)
      refreshMembers()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <p>
        <Link to="/admin/process-types">Manage process types &amp; tolerance matrix</Link>
      </p>

      <h2>Users</h2>
      {error && <p className="form-error">{error}</p>}

      <input
        type="search"
        placeholder="Search by username or email..."
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
        className="admin-user-search"
      />

      <table>
        <thead>
          <tr>
            <th>Username</th>
            <th>Email</th>
            <th>Role</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <tr key={user.user_id}>
              <td>{user.username}</td>
              <td>{user.email}</td>
              <td>{user.global_role}</td>
              <td>
                {pendingDeleteUserId === user.user_id ? (
                  <>
                    <span>Delete this user?</span>{' '}
                    <button type="button" onClick={() => handleDeleteUser(user.user_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" onClick={() => setPendingDeleteUserId(null)}>
                      No
                    </button>
                  </>
                ) : (
                  <button type="button" onClick={() => setPendingDeleteUserId(user.user_id)}>
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
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

      <form onSubmit={handleCreateUser} className="inline-form">
        <input
          placeholder="Username"
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
          required
        />
        <input
          type="email"
          placeholder="Email"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          required
        />
        <select value={newGlobalRole} onChange={(e) => setNewGlobalRole(e.target.value)}>
          {GLOBAL_ROLES.map((role) => (
            <option key={role} value={role}>
              {role}
            </option>
          ))}
        </select>
        <button type="submit">Add user</button>
      </form>

      <h2>Project groups</h2>
      <p>
        Add or remove users from a project&apos;s Managers/Contributors/Viewers groups -- this is
        the only way permissions within a project are granted (per the brief, never assigned
        directly to a user).
      </p>
      <div className="inline-form">
        <label>
          Project:{' '}
          <select value={selectedProjectId} onChange={(e) => setSelectedProjectId(e.target.value)}>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.project_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {selectedProjectId !== '' && (
        <>
          <table>
            <thead>
              <tr>
                <th>Username</th>
                <th>Email</th>
                <th>Group</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => {
                const key = `${member.group_role}:${member.user_id}`
                return (
                  <tr key={key}>
                    <td>{member.username}</td>
                    <td>{member.email}</td>
                    <td>{member.group_role}</td>
                    <td>
                      {pendingRemoveKey === key ? (
                        <>
                          <span>Remove from this group?</span>{' '}
                          <button
                            type="button"
                            onClick={() => handleRemoveMember(member.group_role, member.user_id)}
                          >
                            Yes
                          </button>{' '}
                          <button type="button" onClick={() => setPendingRemoveKey(null)}>
                            No
                          </button>
                        </>
                      ) : (
                        <button type="button" onClick={() => setPendingRemoveKey(key)}>
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
              {members.length === 0 && (
                <tr>
                  <td colSpan={4}>No members yet.</td>
                </tr>
              )}
            </tbody>
          </table>

          <form onSubmit={handleAddMember} className="inline-form">
            <input
              placeholder="Search users..."
              value={memberSearchInput}
              onChange={(e) => setMemberSearchInput(e.target.value)}
            />
            <select value={newMemberUserId} onChange={(e) => setNewMemberUserId(e.target.value)} required>
              <option value="">Select user...</option>
              {memberOptions.map((user) => (
                <option key={user.user_id} value={user.user_id}>
                  {user.username}
                </option>
              ))}
            </select>
            <select value={newMemberRole} onChange={(e) => setNewMemberRole(e.target.value)}>
              {GROUP_ROLES.map((role) => (
                <option key={role} value={role}>
                  {role}
                </option>
              ))}
            </select>
            <button type="submit">Add to group</button>
          </form>
        </>
      )}
    </div>
  )
}

export default AdminPage
