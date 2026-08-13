import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  addProjectMember,
  createClientUser,
  deleteClientUser,
  forceClientUserPasswordReset,
  listClientUsers,
  listProjectMembers,
  listProjects,
  removeProjectMember,
  resendClientUserInvite,
  resetClientUser2fa,
  updateClientUser,
} from '../api/client.js'
import { useAuth } from '../auth/AuthContext.jsx'

const GLOBAL_ROLES = ['standard', 'client_admin']
const GROUP_ROLES = ['Managers', 'Contributors', 'Viewers']
const USERS_PAGE_SIZE = 25

// Only reachable via <ProtectedRoute requireClientAdmin> (see App.jsx).
// Everything here is scoped server-side to the caller's own client (see
// api/client_admin.py) -- this is the client-admin twin of the old
// combined AdminPage, minus anything root_admin still owns (services,
// logs, banner, other clients).
function ClientAdminPage() {
  const { user } = useAuth()
  const [users, setUsers] = useState([])
  const [totalUsers, setTotalUsers] = useState(0)
  const [searchInput, setSearchInput] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [page, setPage] = useState(1)
  const [newFirstName, setNewFirstName] = useState('')
  const [newLastName, setNewLastName] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newGlobalRole, setNewGlobalRole] = useState('standard')
  const [pendingDeleteUserId, setPendingDeleteUserId] = useState(null)
  const [resetMessageUserId, setResetMessageUserId] = useState(null)
  const [inviteSentUserId, setInviteSentUserId] = useState(null)
  const [reset2faUserId, setReset2faUserId] = useState(null)
  const [error, setError] = useState(null)

  const [editingUserId, setEditingUserId] = useState(null)
  const [editFirstName, setEditFirstName] = useState('')
  const [editLastName, setEditLastName] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editGlobalRole, setEditGlobalRole] = useState('standard')

  const [projects, setProjects] = useState([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [members, setMembers] = useState([])
  const [memberSearchInput, setMemberSearchInput] = useState('')
  const [memberSearchTerm, setMemberSearchTerm] = useState('')
  const [memberOptions, setMemberOptions] = useState([])
  const [newMemberUserId, setNewMemberUserId] = useState('')
  const [newMemberRole, setNewMemberRole] = useState('Contributors')
  const [pendingRemoveKey, setPendingRemoveKey] = useState(null)

  function refreshUsers() {
    listClientUsers(searchTerm, page)
      .then((result) => {
        setUsers(result.items)
        setTotalUsers(result.total)
      })
      .catch((err) => setError(err.message))
  }

  function refreshProjects() {
    listProjects().then(setProjects).catch((err) => setError(err.message))
  }

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

  useEffect(() => {
    const timeoutId = setTimeout(() => setMemberSearchTerm(memberSearchInput), 300)
    return () => clearTimeout(timeoutId)
  }, [memberSearchInput])

  useEffect(() => {
    listClientUsers(memberSearchTerm, 1)
      .then((result) => setMemberOptions(result.items))
      .catch((err) => setError(err.message))
  }, [memberSearchTerm])

  async function handleCreateUser(event) {
    event.preventDefault()
    setError(null)
    try {
      await createClientUser(newFirstName, newLastName, newEmail, newGlobalRole)
      setNewFirstName('')
      setNewLastName('')
      setNewEmail('')
      setNewGlobalRole('standard')
      refreshUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditingUser(u) {
    setEditingUserId(u.user_id)
    setEditFirstName(u.first_name)
    setEditLastName(u.last_name)
    setEditEmail(u.email)
    setEditGlobalRole(u.global_role)
    setError(null)
  }

  async function handleSaveEditUser(userId) {
    setError(null)
    try {
      await updateClientUser(userId, editFirstName, editLastName, editEmail, editGlobalRole)
      setEditingUserId(null)
      refreshUsers()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteUser(userId) {
    setError(null)
    try {
      await deleteClientUser(userId)
      setPendingDeleteUserId(null)
      refreshUsers()
      refreshMembers()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleForceReset(userId) {
    setError(null)
    try {
      await forceClientUserPasswordReset(userId)
      setResetMessageUserId(userId)
      setTimeout(() => setResetMessageUserId(null), 4000)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleResendInvite(userId) {
    setError(null)
    try {
      await resendClientUserInvite(userId)
      setInviteSentUserId(userId)
      setTimeout(() => setInviteSentUserId(null), 4000)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleReset2fa(userId) {
    setError(null)
    try {
      await resetClientUser2fa(userId)
      setReset2faUserId(userId)
      setTimeout(() => setReset2faUserId(null), 4000)
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
      <p>Workspace: {user?.client_name}</p>
      <p>
        <Link to="/client-admin/process-types">Manage process types &amp; tolerance matrix</Link>
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
                  <select value={editGlobalRole} onChange={(e) => setEditGlobalRole(e.target.value)}>
                    {GLOBAL_ROLES.map((role) => (
                      <option key={role} value={role}>
                        {role}
                      </option>
                    ))}
                  </select>
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
                <td>{u.global_role}</td>
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
                      <button type="button" className="link-button" onClick={() => handleForceReset(u.user_id)}>
                        {resetMessageUserId === u.user_id ? 'Reset sent' : 'Force password reset'}
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
      <p className="form-hint">
        A new user is emailed a link to set their own password -- no password is entered here.
      </p>

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
                {memberOptions.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.first_name} {u.last_name}
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

export default ClientAdminPage
