import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { createProject, listProjects } from '../api/client.js'

function ProjectListPage() {
  const [projects, setProjects] = useState([])
  const [newProjectName, setNewProjectName] = useState('')
  const [error, setError] = useState(null)

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

  return (
    <div>
      <h2>Projects</h2>
      <ul>
        {projects.map((project) => (
          <li key={project.project_id}>
            <Link to={`/projects/${project.project_id}/commodities`}>{project.project_name}</Link>
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
