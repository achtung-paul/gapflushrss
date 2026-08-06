import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { createProject, deleteProject, listProjects, updateProject } from '../api/client.js'

function ProjectListPage() {
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
        <button type="submit">Create project</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default ProjectListPage
