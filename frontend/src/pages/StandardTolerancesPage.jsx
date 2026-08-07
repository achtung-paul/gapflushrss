import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  createStandardTolerance,
  deleteStandardTolerance,
  listStandardTolerances,
  updateStandardTolerance,
} from '../api/client.js'

// A project's own named tolerance presets (e.g. "Locator" = +/-0.1mm),
// offered as a pick-from option in ToleranceChainSection.jsx alongside
// the separate, global DIN tolerance matrix. Add/edit/delete are
// Manager-only on the backend (see api/standard_tolerances.py) -- the
// controls here are shown to any project member and rely on the
// backend's 403 (surfaced inline) for anyone who isn't a Manager, same
// as every other write action in this app.
function StandardTolerancesPage() {
  const { projectId } = useParams()
  const [standards, setStandards] = useState([])
  const [newName, setNewName] = useState('')
  const [newToleranceValue, setNewToleranceValue] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editingName, setEditingName] = useState('')
  const [editingToleranceValue, setEditingToleranceValue] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    listStandardTolerances(projectId).then(setStandards).catch((err) => setError(err.message))
  }

  useEffect(refresh, [projectId])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createStandardTolerance(projectId, newName, Number(newToleranceValue))
      setNewName('')
      setNewToleranceValue('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditing(standard) {
    setEditingId(standard.standard_tolerance_id)
    setEditingName(standard.name)
    setEditingToleranceValue(String(standard.tolerance_value))
  }

  async function saveEdit(standardToleranceId) {
    setError(null)
    try {
      await updateStandardTolerance(projectId, standardToleranceId, editingName, Number(editingToleranceValue))
      setEditingId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(standardToleranceId) {
    setError(null)
    try {
      await deleteStandardTolerance(projectId, standardToleranceId)
      setPendingDeleteId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <p>
        <Link to={`/projects/${projectId}/commodities`}>&larr; Commodities</Link>
      </p>
      <h2>Standard tolerances</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Tolerance (± mm)</th>
            <th>Last modified by</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {standards.map((standard) => (
            <tr key={standard.standard_tolerance_id}>
              {editingId === standard.standard_tolerance_id ? (
                <>
                  <td>
                    <input value={editingName} onChange={(e) => setEditingName(e.target.value)} />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="0.1"
                      min="0"
                      value={editingToleranceValue}
                      onChange={(e) => setEditingToleranceValue(e.target.value)}
                    />
                  </td>
                  <td>{standard.updated_by_name}</td>
                  <td>
                    <button onClick={() => saveEdit(standard.standard_tolerance_id)}>Save</button>{' '}
                    <button onClick={() => setEditingId(null)}>Cancel</button>
                  </td>
                </>
              ) : (
                <>
                  <td>{standard.name}</td>
                  <td>±{standard.tolerance_value} mm</td>
                  <td>{standard.updated_by_name}</td>
                  <td>
                    {pendingDeleteId === standard.standard_tolerance_id ? (
                      <>
                        <span>Delete this standard tolerance?</span>{' '}
                        <button onClick={() => handleDelete(standard.standard_tolerance_id)}>Yes</button>{' '}
                        <button onClick={() => setPendingDeleteId(null)}>No</button>
                      </>
                    ) : (
                      <>
                        <button onClick={() => startEditing(standard)}>Edit</button>{' '}
                        <button onClick={() => setPendingDeleteId(standard.standard_tolerance_id)}>
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </>
              )}
            </tr>
          ))}
          {standards.length === 0 && (
            <tr>
              <td colSpan={4}>No standard tolerances defined yet.</td>
            </tr>
          )}
        </tbody>
      </table>

      <form onSubmit={handleCreate} className="inline-form">
        <label>
          Name{' '}
          <input
            placeholder="e.g. Locator"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            required
          />
        </label>
        <label>
          Tolerance (± mm){' '}
          <input
            type="number"
            step="0.1"
            min="0"
            value={newToleranceValue}
            onChange={(e) => setNewToleranceValue(e.target.value)}
            required
          />
        </label>
        <button type="submit">Add</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default StandardTolerancesPage
