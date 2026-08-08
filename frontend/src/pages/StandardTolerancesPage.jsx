import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  createStandardTolerance,
  deleteStandardTolerance,
  listStandardTolerances,
  updateStandardTolerance,
} from '../api/client.js'
import NumberInput from '../components/NumberInput.jsx'

const CONTRIBUTOR_TYPE_LABELS = {
  COMPONENT: 'Component tolerance',
  PROCESS: 'Assembly process variation',
}

// A project's own named tolerance presets (e.g. "Locator" = +/-0.1mm),
// offered as a pick-from option in ToleranceChainSection.jsx's merged
// Type dropdown alongside the separate, global tolerance matrix.
// contributor_type is what a chain component created from a given
// preset saves as -- see models/standard_tolerance.py -- so it needs
// setting here at the source. Add/edit/delete are Manager-only on the
// backend (see api/standard_tolerances.py) -- the controls here are
// shown to any project member and rely on the backend's 403 (surfaced
// inline) for anyone who isn't a Manager, same as every other write
// action in this app.
function StandardTolerancesPage() {
  const { projectId } = useParams()
  const [standards, setStandards] = useState([])
  const [newName, setNewName] = useState('')
  const [newToleranceValue, setNewToleranceValue] = useState('')
  const [newContributorType, setNewContributorType] = useState('COMPONENT')
  const [editingId, setEditingId] = useState(null)
  const [editingName, setEditingName] = useState('')
  const [editingToleranceValue, setEditingToleranceValue] = useState('')
  const [editingContributorType, setEditingContributorType] = useState('COMPONENT')
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
      await createStandardTolerance(projectId, newName, Number(newToleranceValue), newContributorType)
      setNewName('')
      setNewToleranceValue('')
      setNewContributorType('COMPONENT')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditing(standard) {
    setEditingId(standard.standard_tolerance_id)
    setEditingName(standard.name)
    setEditingToleranceValue(String(standard.tolerance_value))
    setEditingContributorType(standard.contributor_type)
  }

  async function saveEdit(standardToleranceId) {
    setError(null)
    try {
      await updateStandardTolerance(
        projectId,
        standardToleranceId,
        editingName,
        Number(editingToleranceValue),
        editingContributorType,
      )
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
            <th>Type</th>
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
                    <select
                      value={editingContributorType}
                      onChange={(e) => setEditingContributorType(e.target.value)}
                    >
                      <option value="COMPONENT">Component tolerance</option>
                      <option value="PROCESS">Assembly process variation</option>
                    </select>
                  </td>
                  <td>
                    <NumberInput
                      min="0"
                      value={editingToleranceValue}
                      onChange={setEditingToleranceValue}
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
                  <td>{CONTRIBUTOR_TYPE_LABELS[standard.contributor_type] ?? standard.contributor_type}</td>
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
              <td colSpan={5}>No standard tolerances defined yet.</td>
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
          Type{' '}
          <select value={newContributorType} onChange={(e) => setNewContributorType(e.target.value)}>
            <option value="COMPONENT">Component tolerance</option>
            <option value="PROCESS">Assembly process variation</option>
          </select>
        </label>
        <label>
          Tolerance (± mm){' '}
          <NumberInput min="0" value={newToleranceValue} onChange={setNewToleranceValue} required />
        </label>
        <button type="submit">Add</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default StandardTolerancesPage
