import { useEffect, useState } from 'react'
import { createMinioServer, deleteMinioServer, listMinioServers } from '../api/client.js'

const STATUS_LABELS = { reachable: 'Reachable', unreachable: 'Unreachable' }
const STATUS_RAG = { reachable: 'green', unreachable: 'red' }

// Root-admin management of MinIO *servers* -- distinct from MinIO
// *services* (MinioServicesPage.jsx), which each point at one
// already-existing bucket. A server is registered once here, then
// reused on the Clients page to auto-provision a brand-new bucket for a
// client, with its own dedicated, bucket-scoped access key -- not the
// root credential entered below, which never leaves the provisioning
// step (core/service_provisioning.py). The credentials here need to be
// MinIO's actual root/admin identity, since creating a scoped user and
// attaching a bucket policy are admin-only operations.
function MinioServersPage() {
  const [servers, setServers] = useState([])
  const [name, setName] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [secure, setSecure] = useState(false)
  const [rootAccessKey, setRootAccessKey] = useState('')
  const [rootSecretKey, setRootSecretKey] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    listMinioServers().then(setServers).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createMinioServer({
        name,
        endpoint,
        secure,
        root_access_key: rootAccessKey,
        root_secret_key: rootSecretKey,
      })
      setName('')
      setEndpoint('')
      setSecure(false)
      setRootAccessKey('')
      setRootSecretKey('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(minioServerId) {
    setError(null)
    try {
      await deleteMinioServer(minioServerId)
      setPendingDeleteId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2>MinIO servers</h2>
      {error && <p className="form-error">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Endpoint</th>
            <th>Secure</th>
            <th>Root access key</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {servers.map((server) => (
            <tr key={server.minio_server_id}>
              <td>{server.name}</td>
              <td>{server.endpoint}</td>
              <td>{server.secure ? 'Yes' : 'No'}</td>
              <td>{server.root_access_key}</td>
              <td>
                <span className={`rag-badge rag-${STATUS_RAG[server.status]}`}>
                  {STATUS_LABELS[server.status]}
                </span>
              </td>
              <td>
                {pendingDeleteId === server.minio_server_id ? (
                  <>
                    <span>Delete this server?</span>{' '}
                    <button type="button" onClick={() => handleDelete(server.minio_server_id)}>
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
                    onClick={() => setPendingDeleteId(server.minio_server_id)}
                  >
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
          {servers.length === 0 && (
            <tr>
              <td colSpan={6}>No MinIO servers registered yet.</td>
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
          Endpoint{' '}
          <input
            type="text"
            placeholder="host:port"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            required
          />
        </label>
        <label>
          <input type="checkbox" checked={secure} onChange={(e) => setSecure(e.target.checked)} /> Secure (TLS)
        </label>
        <label>
          Root access key{' '}
          <input
            type="text"
            placeholder="Root access key"
            value={rootAccessKey}
            onChange={(e) => setRootAccessKey(e.target.value)}
            required
          />
        </label>
        <label>
          Root secret key{' '}
          <input
            type="password"
            placeholder="Root secret key"
            value={rootSecretKey}
            onChange={(e) => setRootSecretKey(e.target.value)}
            required
          />
        </label>
        <button type="submit">Add server</button>
      </form>

      <p className="form-hint">
        This must be MinIO's actual root (or an admin-privileged) identity -- creating a client
        (Clients page, "Auto-provision") uses it to create a brand-new bucket, a dedicated IAM
        user scoped to just that bucket, and attach a bucket-only policy to it.
      </p>
    </div>
  )
}

export default MinioServersPage
