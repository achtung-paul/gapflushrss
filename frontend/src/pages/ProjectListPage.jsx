import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createProject,
  deleteProject,
  listMinioServices,
  listPostgresServices,
  listProjects,
  updateProject,
} from '../api/client.js'

function ProjectListPage() {
  const [projects, setProjects] = useState([])
  const [newProjectName, setNewProjectName] = useState('')
  const [postgresServices, setPostgresServices] = useState([])
  const [minioServices, setMinioServices] = useState([])
  const [postgresServiceId, setPostgresServiceId] = useState('')
  const [minioServiceId, setMinioServiceId] = useState('')
  const [error, setError] = useState(null)

  const [editingId, setEditingId] = useState(null)
  const [editingName, setEditingName] = useState('')
  const [confirmingRenameId, setConfirmingRenameId] = useState(null)
  const [pendingDeleteId, setPendingDeleteId] = useState(null)

  function refresh() {
    listProjects().then(setProjects).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  // Only an already-initialized service can be picked -- the backend
  // rejects creating a project against one that isn't (see
  // api/projects.py's create_project). Set up services first from
  // Admin > Postgres services / MinIO services.
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
      await createProject(newProjectName, Number(postgresServiceId), Number(minioServiceId))
      setNewProjectName('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditing(project) {
    setEditingId(project.project_id)
    setEditingName(project.project_name)
    setConfirmingRenameId(null)
  }

  async function handleConfirmRename(projectId) {
    setError(null)
    try {
      await updateProject(projectId, editingName)
      setEditingId(null)
      setConfirmingRenameId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(projectId) {
    setError(null)
    try {
      await deleteProject(projectId)
      setPendingDeleteId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2>Projects</h2>
      <ul>
        {projects.map((project) => (
          <li key={project.project_id}>
            {editingId === project.project_id ? (
              confirmingRenameId === project.project_id ? (
                <>
                  <span>Rename to &quot;{editingName}&quot;?</span>{' '}
                  <button onClick={() => handleConfirmRename(project.project_id)}>Yes</button>{' '}
                  <button onClick={() => setConfirmingRenameId(null)}>No</button>
                </>
              ) : (
                <>
                  <input value={editingName} onChange={(e) => setEditingName(e.target.value)} />{' '}
                  <button onClick={() => setConfirmingRenameId(project.project_id)}>Save</button>{' '}
                  <button onClick={() => setEditingId(null)}>Cancel</button>
                </>
              )
            ) : pendingDeleteId === project.project_id ? (
              <>
                <span>{project.project_name}</span>{' '}
                <span>Delete this project?</span>{' '}
                <button onClick={() => handleDelete(project.project_id)}>Yes</button>{' '}
                <button onClick={() => setPendingDeleteId(null)}>No</button>
              </>
            ) : (
              <>
                <Link to={`/projects/${project.project_id}/commodities`}>{project.project_name}</Link>{' '}
                <button onClick={() => startEditing(project)}>Edit</button>{' '}
                <button onClick={() => setPendingDeleteId(project.project_id)}>Delete</button>
              </>
            )}
          </li>
        ))}
      </ul>

      <form onSubmit={handleCreate} className="inline-form">
        <input
          placeholder="New project name"
          value={newProjectName}
          onChange={(e) => setNewProjectName(e.target.value)}
          required
        />
        <select value={postgresServiceId} onChange={(e) => setPostgresServiceId(e.target.value)} required>
          <option value="">Postgres service...</option>
          {postgresServices.map((service) => (
            <option key={service.postgres_service_id} value={service.postgres_service_id}>
              {service.name}
            </option>
          ))}
        </select>
        <select value={minioServiceId} onChange={(e) => setMinioServiceId(e.target.value)} required>
          <option value="">MinIO service...</option>
          {minioServices.map((service) => (
            <option key={service.minio_service_id} value={service.minio_service_id}>
              {service.name}
            </option>
          ))}
        </select>
        <button type="submit">Create project</button>
      </form>
      {(postgresServices.length === 0 || minioServices.length === 0) && (
        <p className="form-hint">
          No initialized services available yet -- set one up from{' '}
          <Link to="/admin/postgres-services">Postgres services</Link> or{' '}
          <Link to="/admin/minio-services">MinIO services</Link>.
        </p>
      )}
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default ProjectListPage
