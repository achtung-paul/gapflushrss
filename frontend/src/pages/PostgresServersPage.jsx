import { useEffect, useState } from 'react'
import { createPostgresServer, deletePostgresServer, listPostgresServers } from '../api/client.js'

const STATUS_LABELS = { reachable: 'Reachable', unreachable: 'Unreachable' }
const STATUS_RAG = { reachable: 'green', unreachable: 'red' }

// Root-admin management of Postgres *servers* -- distinct from Postgres
// *services* (PostgresServicesPage.jsx), which each point at one
// already-existing database. A server is registered once here, then
// reused on the Clients page (ClientsPage.jsx) to auto-provision a
// brand-new, dedicated database + login role for a client instead of an
// admin having to create that database by hand first. The credentials
// entered below need CREATEDB and CREATEROLE rights on the server, not
// just access to one database.
function PostgresServersPage() {
  const [servers, setServers] = useState([])
  const [name, setName] = useState('')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('5432')
  const [adminUsername, setAdminUsername] = useState('')
  const [adminPassword, setAdminPassword] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    listPostgresServers().then(setServers).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createPostgresServer({
        name,
        host,
        port: Number(port),
        admin_username: adminUsername,
        admin_password: adminPassword,
      })
      setName('')
      setHost('')
      setPort('5432')
      setAdminUsername('')
      setAdminPassword('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(postgresServerId) {
    setError(null)
    try {
      await deletePostgresServer(postgresServerId)
      setPendingDeleteId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2>Postgres servers</h2>
      {error && <p className="form-error">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Host</th>
            <th>Port</th>
            <th>Admin username</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {servers.map((server) => (
            <tr key={server.postgres_server_id}>
              <td>{server.name}</td>
              <td>{server.host}</td>
              <td>{server.port}</td>
              <td>{server.admin_username}</td>
              <td>
                <span className={`rag-badge rag-${STATUS_RAG[server.status]}`}>
                  {STATUS_LABELS[server.status]}
                </span>
              </td>
              <td>
                {pendingDeleteId === server.postgres_server_id ? (
                  <>
                    <span>Delete this server?</span>{' '}
                    <button type="button" onClick={() => handleDelete(server.postgres_server_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" onClick={() => setPendingDeleteId(null)}>
                      No
                    </button>
                  </>
                ) : (
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => setPendingDeleteId(server.postgres_server_id)}
                  >
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
          {servers.length === 0 && (
            <tr>
              <td colSpan={6}>No Postgres servers registered yet.</td>
            </tr>
          )}
        </tbody>
      </table>

      <div className="section-divider" />

      <form onSubmit={handleCreate} className="inline-form">
        <label>
          Name{' '}
          <input type="text" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Host{' '}
          <input type="text" placeholder="Host" value={host} onChange={(e) => setHost(e.target.value)} required />
        </label>
        <label>
          Port{' '}
          <input type="number" placeholder="Port" value={port} onChange={(e) => setPort(e.target.value)} required />
        </label>
        <label>
          Admin username{' '}
          <input
            type="text"
            placeholder="Admin username"
            value={adminUsername}
            onChange={(e) => setAdminUsername(e.target.value)}
            required
          />
        </label>
        <label>
          Admin password{' '}
          <input
            type="password"
            placeholder="Admin password"
            value={adminPassword}
            onChange={(e) => setAdminPassword(e.target.value)}
            required
          />
        </label>
        <button type="submit">Add server</button>
      </form>

      <p className="form-hint">
        This is a stronger credential than a Postgres <strong>service</strong>'s own username --
        it needs <code>CREATEDB</code> and <code>CREATEROLE</code> rights on the server, since
        creating a client (Clients page, "Auto-provision") uses it to create a brand-new database
        and a dedicated login role for that client, not just to connect to one that already
        exists.
      </p>
    </div>
  )
}

export default PostgresServersPage
