import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createProcessType,
  deleteProcessType,
  listProcessTypes,
  updateProcessType,
} from '../api/client.js'

function ProcessTypesPage() {
  const [processTypes, setProcessTypes] = useState([])
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editingName, setEditingName] = useState('')
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    listProcessTypes().then(setProcessTypes).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createProcessType(newName)
      setNewName('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditing(processType) {
    setEditingId(processType.process_type_id)
    setEditingName(processType.name)
  }

  async function saveEdit(processTypeId) {
    setError(null)
    try {
      await updateProcessType(processTypeId, editingName)
      setEditingId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(processTypeId) {
    setError(null)
    try {
      await deleteProcessType(processTypeId)
      setPendingDeleteId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <h2>Process types</h2>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {processTypes.map((processType) => (
            <tr key={processType.process_type_id}>
              <td>
                {editingId === processType.process_type_id ? (
                  <input value={editingName} onChange={(e) => setEditingName(e.target.value)} />
                ) : (
                  <Link to={`/admin/process-types/${processType.process_type_id}/tolerance-matrix`}>
                    {processType.name}
                  </Link>
                )}
              </td>
              <td>
                {editingId === processType.process_type_id ? (
                  <button onClick={() => saveEdit(processType.process_type_id)}>Save</button>
                ) : pendingDeleteId === processType.process_type_id ? (
                  <>
                    <span>Delete this process type?</span>{' '}
                    <button onClick={() => handleDelete(processType.process_type_id)}>Yes</button>{' '}
                    <button onClick={() => setPendingDeleteId(null)}>No</button>
                  </>
                ) : (
                  <>
                    <button onClick={() => startEditing(processType)}>Edit</button>{' '}
                    <button onClick={() => setPendingDeleteId(processType.process_type_id)}>Delete</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <form onSubmit={handleCreate} className="inline-form">
        <input
          placeholder="New process type"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          required
        />
        <button type="submit">Create</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default ProcessTypesPage
