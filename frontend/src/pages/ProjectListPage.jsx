import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { createProject, deleteProject, listProjects, updateProject } from '../api/client.js'
import { useAuth } from '../auth/AuthContext.jsx'

function ProjectListPage() {
  const { user } = useAuth()
  const isClientAdmin = user?.global_role === 'client_admin'
  const [projects, setProjects] = useState([])
  const [newProjectName, setNewProjectName] = useState('')
  const [error, setError] = useState(null)

  const [editingId, setEditingId] = useState(null)
  const [editingName, setEditingName] = useState('')
  const [confirmingRenameId, setConfirmingRenameId] = useState(null)
  const [pendingDeleteId, setPendingDeleteId] = useState(null)

  function refresh() {
    listProjects().then(setProjects).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  // No service picker here any more -- a new project always inherits its
  // client's own dedicated Postgres/MinIO (set once, at the client level,
  // by root admin -- see api/projects.py's create_project). A client
  // admin never sees the service list at all.
  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createProject(newProjectName)
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
      <table className="rss-results contributor-table">
        <thead>
          <tr>
            <th>Project</th>
            <th>Role</th>
            {isClientAdmin && <th>Actions</th>}
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.project_id}>
              {isClientAdmin && editingId === project.project_id ? (
                confirmingRenameId === project.project_id ? (
                  <td colSpan={isClientAdmin ? 3 : 2}>
                    <span>Rename to &quot;{editingName}&quot;?</span>{' '}
                    <button type="button" className="link-button" onClick={() => handleConfirmRename(project.project_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" className="link-button" onClick={() => setConfirmingRenameId(null)}>
                      No
                    </button>
                  </td>
                ) : (
                  <td colSpan={isClientAdmin ? 3 : 2}>
                    <label>
                      New name{' '}
                      <input type="text" value={editingName} onChange={(e) => setEditingName(e.target.value)} />
                    </label>{' '}
                    <button type="button" className="link-button" onClick={() => setConfirmingRenameId(project.project_id)}>
                      Save
                    </button>{' '}
                    <button type="button" className="link-button" onClick={() => setEditingId(null)}>
                      Cancel
                    </button>
                  </td>
                )
              ) : isClientAdmin && pendingDeleteId === project.project_id ? (
                <>
                  <td>{project.project_name}</td>
                  <td colSpan={2}>
                    <span>Delete this project?</span>{' '}
                    <button type="button" className="link-button" onClick={() => handleDelete(project.project_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" className="link-button" onClick={() => setPendingDeleteId(null)}>
                      No
                    </button>
                  </td>
                </>
              ) : (
                <>
                  <td>
                    <Link to={`/projects/${project.project_id}/commodities`}>{project.project_name}</Link>
                  </td>
                  <td>
                    <span className="tag">{project.my_role}</span>
                  </td>
                  {isClientAdmin && (
                    <td>
                      <button type="button" className="link-button" onClick={() => startEditing(project)}>
                        Edit
                      </button>{' '}
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => setPendingDeleteId(project.project_id)}
                      >
                        Delete
                      </button>
                    </td>
                  )}
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      {isClientAdmin && (
        <>
          <div className="section-divider" />

          <form onSubmit={handleCreate} className="inline-form">
            <label>
              Project name{' '}
              <input
                type="text"
                placeholder="New project name"
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                required
              />
            </label>
            <button type="submit">Create project</button>
          </form>
        </>
      )}
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default ProjectListPage
