import { Fragment, useEffect, useState } from 'react'
import {
  addClientAdmin,
  createClient,
  deleteClient,
  forceClientAdminPasswordReset,
  listClientAdmins,
  listClients,
  listMinioServices,
  listPostgresServices,
  updateClient,
} from '../api/client.js'

// Root admin's management of Clients (SaaS tenants). Deliberately thin:
// a client's name, which services it sits on, whether it's active, how
// many projects it has, and its client_admin accounts -- never a
// project name, never an ordinary user, never any analysis data. See
// api/admin_clients.py and CLAUDE.md's tenancy-boundary gotcha.
function ClientsPage() {
  const [clients, setClients] = useState([])
  const [postgresServices, setPostgresServices] = useState([])
  const [minioServices, setMinioServices] = useState([])
  const [error, setError] = useState(null)

  const [name, setName] = useState('')
  const [postgresServiceId, setPostgresServiceId] = useState('')
  const [minioServiceId, setMinioServiceId] = useState('')
  const [adminFirstName, setAdminFirstName] = useState('')
  const [adminLastName, setAdminLastName] = useState('')
  const [adminEmail, setAdminEmail] = useState('')
  const [adminPassword, setAdminPassword] = useState('')

  const [expandedClientId, setExpandedClientId] = useState(null)
  const [clientAdmins, setClientAdmins] = useState([])
  const [newAdminFirstName, setNewAdminFirstName] = useState('')
  const [newAdminLastName, setNewAdminLastName] = useState('')
  const [newAdminEmail, setNewAdminEmail] = useState('')
  const [newAdminPassword, setNewAdminPassword] = useState('')

  const [editingId, setEditingId] = useState(null)
  const [editingName, setEditingName] = useState('')
  // Deactivating blocks every user of that client from logging in (and
  // kills their open sessions) -- worth a confirmation, same inline
  // pattern as every other destructive action in this app (see
  // CLAUDE.md: never window.confirm()).
  const [pendingDeactivateId, setPendingDeactivateId] = useState(null)

  // Purge is permanent (a snapshot is taken first -- see
  // api/admin_clients.py's delete_client -- but this app has no restore
  // button, only a host-side runbook, so it must be treated as
  // permanent from here). Typing the exact name is a stronger bar than
  // the usual Yes/No inline confirm, deliberately, for the one action in
  // this app that deletes a whole tenant.
  const [pendingPurgeId, setPendingPurgeId] = useState(null)
  const [purgeConfirmText, setPurgeConfirmText] = useState('')
  const [purgeBusy, setPurgeBusy] = useState(false)

  function refresh() {
    listClients().then(setClients).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  useEffect(() => {
    listPostgresServices()
      .then((services) => setPostgresServices(services.filter((s) => s.status === 'initialized')))
      .catch((err) => setError(err.message))
    listMinioServices()
      .then((services) => setMinioServices(services.filter((s) => s.status === 'initialized')))
      .catch((err) => setError(err.message))
  }, [])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createClient(
        name,
        Number(postgresServiceId),
        Number(minioServiceId),
        adminFirstName,
        adminLastName,
        adminEmail,
        adminPassword,
      )
      setName('')
      setPostgresServiceId('')
      setMinioServiceId('')
      setAdminFirstName('')
      setAdminLastName('')
      setAdminEmail('')
      setAdminPassword('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function toggleExpanded(clientId) {
    if (expandedClientId === clientId) {
      setExpandedClientId(null)
      return
    }
    setExpandedClientId(clientId)
    setError(null)
    listClientAdmins(clientId).then(setClientAdmins).catch((err) => setError(err.message))
  }

  async function handleAddAdmin(event, clientId) {
    event.preventDefault()
    setError(null)
    try {
      await addClientAdmin(clientId, newAdminFirstName, newAdminLastName, newAdminEmail, newAdminPassword)
      setNewAdminFirstName('')
      setNewAdminLastName('')
      setNewAdminEmail('')
      setNewAdminPassword('')
      listClientAdmins(clientId).then(setClientAdmins).catch((err) => setError(err.message))
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleForceReset(clientId, userId) {
    setError(null)
    try {
      await forceClientAdminPasswordReset(clientId, userId)
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditing(client) {
    setEditingId(client.client_id)
    setEditingName(client.name)
  }

  async function handleSaveRename(client) {
    setError(null)
    try {
      await updateClient(client.client_id, editingName, client.is_active)
      setEditingId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleToggleActive(client) {
    setError(null)
    try {
      await updateClient(client.client_id, client.name, !client.is_active)
      setPendingDeactivateId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handlePurge(client) {
    setError(null)
    setPurgeBusy(true)
    try {
      await deleteClient(client.client_id)
      setPendingPurgeId(null)
      setPurgeConfirmText('')
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setPurgeBusy(false)
    }
  }

  return (
    <div>
      <h2>Clients</h2>
      {error && <p className="form-error">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Projects</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {clients.map((client) => (
            <Fragment key={client.client_id}>
              <tr>
                <td>
                  {editingId === client.client_id ? (
                    <>
                      <input type="text" value={editingName} onChange={(e) => setEditingName(e.target.value)} />{' '}
                      <button type="button" className="link-button" onClick={() => handleSaveRename(client)}>
                        Save
                      </button>{' '}
                      <button type="button" className="link-button" onClick={() => setEditingId(null)}>
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button type="button" className="link-button" onClick={() => toggleExpanded(client.client_id)}>
                      {client.name}
                    </button>
                  )}
                </td>
                <td>{client.project_count}</td>
                <td>
                  <span className={`rag-badge rag-${client.is_active ? 'green' : 'red'}`}>
                    {client.is_active ? 'Active' : 'Deactivated'}
                  </span>
                </td>
                <td>
                  {pendingDeactivateId === client.client_id ? (
                    <>
                      <span>
                        {client.is_active
                          ? 'Deactivate this client? Every user is logged out and blocked from logging back in.'
                          : 'Reactivate this client?'}
                      </span>{' '}
                      <button type="button" onClick={() => handleToggleActive(client)}>
                        Yes
                      </button>{' '}
                      <button type="button" onClick={() => setPendingDeactivateId(null)}>
                        No
                      </button>
                    </>
                  ) : pendingPurgeId === client.client_id ? (
                    <>
                      <span>
                        This permanently deletes every project, user, and the tolerance matrix for{' '}
                        <strong>{client.name}</strong>, after taking a snapshot on the server. Type the
                        client name to confirm:
                      </span>{' '}
                      <input
                        type="text"
                        value={purgeConfirmText}
                        onChange={(e) => setPurgeConfirmText(e.target.value)}
                        placeholder={client.name}
                      />{' '}
                      <button
                        type="button"
                        disabled={purgeConfirmText !== client.name || purgeBusy}
                        onClick={() => handlePurge(client)}
                      >
                        {purgeBusy ? 'Purging...' : 'Permanently delete'}
                      </button>{' '}
                      <button
                        type="button"
                        onClick={() => {
                          setPendingPurgeId(null)
                          setPurgeConfirmText('')
                        }}
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    editingId !== client.client_id && (
                      <>
                        <button type="button" className="link-button" onClick={() => startEditing(client)}>
                          Rename
                        </button>{' '}
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => setPendingDeactivateId(client.client_id)}
                        >
                          {client.is_active ? 'Deactivate' : 'Reactivate'}
                        </button>{' '}
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => setPendingPurgeId(client.client_id)}
                        >
                          Delete permanently
                        </button>
                      </>
                    )
                  )}
                </td>
              </tr>
              {expandedClientId === client.client_id && (
                <tr>
                  <td colSpan={4}>
                    <h3>Client admins</h3>
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
                        {clientAdmins.map((admin) => (
                          <tr key={admin.user_id}>
                            <td>{admin.first_name}</td>
                            <td>{admin.last_name}</td>
                            <td>{admin.email}</td>
                            <td>
                              <button
                                type="button"
                                className="link-button"
                                onClick={() => handleForceReset(client.client_id, admin.user_id)}
                              >
                                Force password reset
                              </button>
                            </td>
                          </tr>
                        ))}
                        {clientAdmins.length === 0 && (
                          <tr>
                            <td colSpan={4}>No client admins yet.</td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                    <form onSubmit={(e) => handleAddAdmin(e, client.client_id)} className="inline-form">
                      <label>
                        First name{' '}
                        <input
                          type="text"
                          value={newAdminFirstName}
                          onChange={(e) => setNewAdminFirstName(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Last name{' '}
                        <input
                          type="text"
                          value={newAdminLastName}
                          onChange={(e) => setNewAdminLastName(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Email{' '}
                        <input
                          type="email"
                          value={newAdminEmail}
                          onChange={(e) => setNewAdminEmail(e.target.value)}
                          required
                        />
                      </label>
                      <label>
                        Password{' '}
                        <input
                          type="password"
                          value={newAdminPassword}
                          onChange={(e) => setNewAdminPassword(e.target.value)}
                          required
                        />
                      </label>
                      <button type="submit">Add admin</button>
                    </form>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {clients.length === 0 && (
            <tr>
              <td colSpan={4}>No clients registered yet.</td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="section-divider" />

      <form onSubmit={handleCreate} className="inline-form">
        <label>
          Client name{' '}
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Postgres service{' '}
          <select value={postgresServiceId} onChange={(e) => setPostgresServiceId(e.target.value)} required>
            <option value="">Postgres service...</option>
            {postgresServices.map((service) => (
              <option key={service.postgres_service_id} value={service.postgres_service_id}>
                {service.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          MinIO service{' '}
          <select value={minioServiceId} onChange={(e) => setMinioServiceId(e.target.value)} required>
            <option value="">MinIO service...</option>
            {minioServices.map((service) => (
              <option key={service.minio_service_id} value={service.minio_service_id}>
                {service.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Admin first name{' '}
          <input type="text" value={adminFirstName} onChange={(e) => setAdminFirstName(e.target.value)} required />
        </label>
        <label>
          Admin last name{' '}
          <input type="text" value={adminLastName} onChange={(e) => setAdminLastName(e.target.value)} required />
        </label>
        <label>
          Admin email{' '}
          <input type="email" value={adminEmail} onChange={(e) => setAdminEmail(e.target.value)} required />
        </label>
        <label>
          Admin password{' '}
          <input
            type="password"
            value={adminPassword}
            onChange={(e) => setAdminPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit">Create client</button>
      </form>
      {(postgresServices.length === 0 || minioServices.length === 0) && (
        <p className="form-hint">
          A client needs one initialized Postgres service and one initialized MinIO service, each
          dedicated to that client alone -- set one up from Postgres services or MinIO services
          first.
        </p>
      )}
    </div>
  )
}

export default ClientsPage
