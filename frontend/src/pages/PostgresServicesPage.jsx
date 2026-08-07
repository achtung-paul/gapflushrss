import { useEffect, useState } from 'react'
import {
  createPostgresService,
  deletePostgresService,
  initializePostgresService,
  listPostgresServices,
} from '../api/client.js'

// Reuses the RAG badge styling from the tolerance-chain simulation
// results (see index.css) -- initialized/not_initialized/unreachable
// map naturally onto green/amber/red.
const STATUS_LABELS = { initialized: 'Initialized', not_initialized: 'Not initialized', unreachable: 'Unreachable' }
const STATUS_RAG = { initialized: 'green', not_initialized: 'amber', unreachable: 'red' }

// Admin management of registered Postgres connections that Projects can
// be assigned to (see ProjectListPage.jsx's create form). A brand-new
// service starts "not_initialized" until Initialize is clicked, which
// runs the project-scoped schema against it (core/service_db.py).
function PostgresServicesPage() {
  const [services, setServices] = useState([])
  const [name, setName] = useState('')
  const [host, setHost] = useState('')
  const [port, setPort] = useState('5432')
  const [database, setDatabase] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    listPostgresServices().then(setServices).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createPostgresService({
        name,
        host,
        port: Number(port),
        database,
        username,
        password,
      })
      setName('')
      setHost('')
      setPort('5432')
      setDatabase('')
      setUsername('')
      setPassword('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleInitialize(postgresServiceId) {
    setError(null)
    setBusyId(postgresServiceId)
    try {
      await initializePostgresService(postgresServiceId)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(postgresServiceId) {
    setError(null)
    try {
      await deletePostgresService(postgresServiceId)
      setPendingDeleteId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2>Postgres services</h2>
      {error && <p className="form-error">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Host</th>
            <th>Port</th>
            <th>Database</th>
            <th>Username</th>
            <th>Status</th>
            <th></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {services.map((service) => (
            <tr key={service.postgres_service_id}>
              <td>{service.name}</td>
              <td>{service.host}</td>
              <td>{service.port}</td>
              <td>{service.database}</td>
              <td>{service.username}</td>
              <td className={`rag-badge rag-${STATUS_RAG[service.status]}`}>
                {STATUS_LABELS[service.status]}
              </td>
              <td>
                {service.status !== 'initialized' && (
                  <button
                    type="button"
                    disabled={busyId === service.postgres_service_id}
                    onClick={() => handleInitialize(service.postgres_service_id)}
                  >
                    Initialize
                  </button>
                )}
              </td>
              <td>
                {pendingDeleteId === service.postgres_service_id ? (
                  <>
                    <span>Delete this service?</span>{' '}
                    <button type="button" onClick={() => handleDelete(service.postgres_service_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" onClick={() => setPendingDeleteId(null)}>
                      No
                    </button>
                  </>
                ) : (
                  <button type="button" onClick={() => setPendingDeleteId(service.postgres_service_id)}>
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
          {services.length === 0 && (
            <tr>
              <td colSpan={8}>No Postgres services registered yet.</td>
            </tr>
          )}
        </tbody>
      </table>

      <form onSubmit={handleCreate} className="inline-form">
        <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <input placeholder="Host" value={host} onChange={(e) => setHost(e.target.value)} required />
        <input
          type="number"
          placeholder="Port"
          value={port}
          onChange={(e) => setPort(e.target.value)}
          required
        />
        <input
          placeholder="Database"
          value={database}
          onChange={(e) => setDatabase(e.target.value)}
          required
        />
        <input
          placeholder="Username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button type="submit">Add service</button>
      </form>

      <p className="form-hint">
        <strong>Name</strong> is just a label shown in this list and in the project-creation
        dropdown -- any text, up to 100 characters, must be unique across services.
        <br />
        <strong>Host</strong> is whatever this app&apos;s containers can resolve: an IP address
        (e.g. 192.168.4.50), a DNS domain name (e.g. db.example.com), or another Docker service
        name on the same network (e.g. postgres).
        <br />
        <strong>Port</strong> is normally 5432 unless the server&apos;s been configured otherwise.
        <br />
        <strong>Database</strong> must already exist on that server -- this app connects to it, it
        doesn&apos;t create it. Standard Postgres identifier rules apply (letters, digits,
        underscores; can&apos;t start with a digit).
        <br />
        <strong>Username</strong> must be an existing Postgres role on that server with
        permission to create tables in the chosen database -- required for the Initialize step
        below, which creates this app&apos;s schema there.
        <br />
        <strong>Initialize</strong> connects and creates this app&apos;s tables if the database is
        empty. A project can&apos;t be created against a service until it shows Initialized.
      </p>
    </div>
  )
}

export default PostgresServicesPage
