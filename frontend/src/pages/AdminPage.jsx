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
  updateUser,
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
  const [newFirstName, setNewFirstName] = useState('')
  const [newLastName, setNewLastName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newGlobalRole, setNewGlobalRole] = useState('standard')
  const [pendingDeleteUserId, setPendingDeleteUserId] = useState(null)
  const [error, setError] = useState(null)

  // Editing an existing user's details (not password -- that's the
  // email-based reset flow) in place, same inline-edit pattern as
  // ProcessTypesPage.jsx.
  const [editingUserId, setEditingUserId] = useState(null)
  const [editFirstName, setEditFirstName] = useState('')
  const [editLastName, setEditLastName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editGlobalRole, setEditGlobalRole] = useState('standard')

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
      await createUser(newFirstName, newLastName, newEmail, newPassword, newGlobalRole)
      setNewFirstName('')
      setNewLastName('')
      setNewEmail('')
      setNewPassword('')
      setNewGlobalRole('standard')
      refreshUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditingUser(user) {
    setEditingUserId(user.user_id)
    setEditFirstName(user.first_name)
    setEditLastName(user.last_name)
    setEditEmail(user.email)
    setEditGlobalRole(user.global_role)
    setError(null)
  }

  async function handleSaveEditUser(userId) {
    setError(null)
    try {
      await updateUser(userId, editFirstName, editLastName, editEmail, editGlobalRole)
      setEditingUserId(null)
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
        {' | '}
        <Link to="/admin/postgres-services">Postgres services</Link>
        {' | '}
        <Link to="/admin/minio-services">MinIO services</Link>
        {' | '}
        <Link to="/admin/logs">Service logs</Link>
        {' | '}
        <Link to="/admin/banner">Site banner</Link>
      </p>

      <h2>Users</h2>
      {error && <p className="form-error">{error}</p>}

      <label>
        Search users{' '}
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
            <th>Role</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) =>
            editingUserId === user.user_id ? (
              <tr key={user.user_id}>
                <td>
                  <input type="text" value={editFirstName} onChange={(e) => setEditFirstName(e.target.value)} />
                </td>
                <td>
                  <input type="text" value={editLastName} onChange={(e) => setEditLastName(e.target.value)} />
                </td>
                <td>
                  <input
                    type="email"
                    value={editEmail}
                    onChange={(e) => setEditEmail(e.target.value)}
                  />
                </td>
                <td>
                  <select value={editGlobalRole} onChange={(e) => setEditGlobalRole(e.target.value)}>
                    {GLOBAL_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <button type="button" onClick={() => handleSaveEditUser(user.user_id)}>
                    Save
                  </button>{' '}
                  <button type="button" onClick={() => setEditingUserId(null)}>
                    Cancel
                  </button>
                </td>
              </tr>
            ) : (
              <tr key={user.user_id}>
                <td>{user.first_name}</td>
                <td>{user.last_name}</td>
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
                    <>
                      <button type="button" className="link-button" onClick={() => startEditingUser(user)}>
                        Edit
                      </button>{' '}
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => setPendingDeleteUserId(user.user_id)}
                      >
                        Delete
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ),
          )}
          {users.length === 0 && (
            <tr>
              <td colSpan={5}>No users found.</td>
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
        <label>
          Password{' '}
          <input
            type="password"
            placeholder="Password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
        </label>
        <label>
          Role{' '}
          <select value={newGlobalRole} onChange={(e) => setNewGlobalRole(e.target.value)}>
            {GLOBAL_ROLES.map((role) => (
              <option key={role} value={role}>
                {role}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">Add user</button>
      </form>

      <div className="section-divider" />

      <h2>Project groups</h2>
      <p>
        Add or remove users from a project&apos;s Managers/Contributors/Viewers groups -- this is
        the only way permissions within a project are granted.
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
                <th>First name</th>
                <th>Last name</th>
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
                    <td>{member.first_name}</td>
                    <td>{member.last_name}</td>
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
                        <button type="button" className="link-button" onClick={() => setPendingRemoveKey(key)}>
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                )
              })}
              {members.length === 0 && (
                <tr>
                  <td colSpan={5}>No members yet.</td>
                </tr>
              )}
            </tbody>
          </table>

          <form onSubmit={handleAddMember} className="inline-form">
            <label>
              Search users{' '}
              <input
                type="text"
                placeholder="Search users..."
                value={memberSearchInput}
                onChange={(e) => setMemberSearchInput(e.target.value)}
              />
            </label>
            <label>
              User{' '}
              <select value={newMemberUserId} onChange={(e) => setNewMemberUserId(e.target.value)} required>
                <option value="">Select user...</option>
                {memberOptions.map((user) => (
                  <option key={user.user_id} value={user.user_id}>
                    {user.first_name} {user.last_name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Group{' '}
              <select value={newMemberRole} onChange={(e) => setNewMemberRole(e.target.value)}>
                {GROUP_ROLES.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit">Add to group</button>
          </form>
        </>
      )}
    </div>
  )
}

export default AdminPage
