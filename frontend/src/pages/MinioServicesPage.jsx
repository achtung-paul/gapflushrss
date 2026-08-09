import { useEffect, useState } from 'react'
import {
  createMinioService,
  deleteMinioService,
  initializeMinioService,
  listMinioServices,
} from '../api/client.js'

// Reuses the RAG badge styling from the tolerance-chain simulation
// results (see index.css) -- initialized/not_initialized/unreachable
// map naturally onto green/amber/red.
const STATUS_LABELS = { initialized: 'Initialized', not_initialized: 'Not initialized', unreachable: 'Unreachable' }
const STATUS_RAG = { initialized: 'green', not_initialized: 'amber', unreachable: 'red' }

// Admin management of registered MinIO connections that Projects can be
// assigned to (see ProjectListPage.jsx's create form). A brand-new
// service starts "not_initialized" until Initialize is clicked, which
// creates its bucket (core/service_storage.py).
function MinioServicesPage() {
  const [services, setServices] = useState([])
  const [name, setName] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [accessKey, setAccessKey] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [secure, setSecure] = useState(false)
  const [bucket, setBucket] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    listMinioServices().then(setServices).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createMinioService({
        name,
        endpoint,
        access_key: accessKey,
        secret_key: secretKey,
        secure,
        bucket,
      })
      setName('')
      setEndpoint('')
      setAccessKey('')
      setSecretKey('')
      setSecure(false)
      setBucket('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleInitialize(minioServiceId) {
    setError(null)
    setBusyId(minioServiceId)
    try {
      await initializeMinioService(minioServiceId)
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  async function handleDelete(minioServiceId) {
    setError(null)
    try {
      await deleteMinioService(minioServiceId)
      setPendingDeleteId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2>MinIO services</h2>
      {error && <p className="form-error">{error}</p>}

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Endpoint</th>
            <th>Bucket</th>
            <th>Access key</th>
            <th>Secure</th>
            <th>Status</th>
            <th></th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {services.map((service) => (
            <tr key={service.minio_service_id}>
              <td>{service.name}</td>
              <td>{service.endpoint}</td>
              <td>{service.bucket}</td>
              <td>{service.access_key}</td>
              <td>{service.secure ? 'Yes' : 'No'}</td>
              <td>
                <span className={`rag-badge rag-${STATUS_RAG[service.status]}`}>
                  {STATUS_LABELS[service.status]}
                </span>
              </td>
              <td>
                {service.status !== 'initialized' && (
                  <button
                    type="button"
                    disabled={busyId === service.minio_service_id}
                    onClick={() => handleInitialize(service.minio_service_id)}
                  >
                    Initialize
                  </button>
                )}
              </td>
              <td>
                {pendingDeleteId === service.minio_service_id ? (
                  <>
                    <span>Delete this service?</span>{' '}
                    <button type="button" onClick={() => handleDelete(service.minio_service_id)}>
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
                    onClick={() => setPendingDeleteId(service.minio_service_id)}
                  >
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
          {services.length === 0 && (
            <tr>
              <td colSpan={8}>No MinIO services registered yet.</td>
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
            placeholder="Endpoint (host:port)"
            value={endpoint}
            onChange={(e) => setEndpoint(e.target.value)}
            required
          />
        </label>
        <label>
          Access key{' '}
          <input
            type="text"
            placeholder="Access key"
            value={accessKey}
            onChange={(e) => setAccessKey(e.target.value)}
            required
          />
        </label>
        <label>
          Secret key{' '}
          <input
            type="password"
            placeholder="Secret key"
            value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)}
            required
          />
        </label>
        <label>
          Bucket{' '}
          <input type="text" placeholder="Bucket" value={bucket} onChange={(e) => setBucket(e.target.value)} required />
        </label>
        <label>
          <input type="checkbox" checked={secure} onChange={(e) => setSecure(e.target.checked)} /> Secure
          (HTTPS)
        </label>
        <button type="submit">Add service</button>
      </form>

      <p className="form-hint">
        <strong>Name</strong> is just a label shown in this list and in the project-creation
        dropdown -- any text, up to 100 characters, must be unique across services.
        <br />
        <strong>Endpoint</strong> is host:port, no http:// or https:// prefix -- an IP address
        (e.g. 192.168.4.50:9000), a DNS domain name (e.g. minio.example.com:9000), or another
        Docker service name on the same network (e.g. minio:9000). Use the Secure checkbox for
        https, not a prefix on this field.
        <br />
        <strong>Access key / Secret key</strong> are MinIO (or any S3-compatible) credentials with
        permission to create and write to a bucket on that server.
        <br />
        <strong>Bucket</strong> follows S3 bucket naming rules: 3-63 characters, lowercase letters,
        digits, hyphens, and periods only, must start and end with a letter or digit, no
        consecutive periods, and can&apos;t be formatted as an IP address. Created automatically by
        the Initialize step below if it doesn&apos;t already exist.
        <br />
        <strong>Initialize</strong> connects and creates the bucket if it&apos;s missing. A project
        can&apos;t be created against a service until it shows Initialized.
      </p>
    </div>
  )
}

export default MinioServicesPage
