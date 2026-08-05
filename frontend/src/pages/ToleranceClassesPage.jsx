import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  createToleranceClass,
  deleteToleranceClass,
  listToleranceClasses,
  updateToleranceClass,
} from '../api/client.js'

function ToleranceClassesPage() {
  const { processTypeId } = useParams()
  const [toleranceClasses, setToleranceClasses] = useState([])
  const [newClassName, setNewClassName] = useState('')
  const [newValue, setNewValue] = useState('')
  const [editingId, setEditingId] = useState(null)
  const [editingClassName, setEditingClassName] = useState('')
  const [editingValue, setEditingValue] = useState('')
  const [error, setError] = useState(null)

  function refresh() {
    listToleranceClasses(processTypeId).then(setToleranceClasses).catch((err) => setError(err.message))
  }

  useEffect(refresh, [processTypeId])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createToleranceClass(processTypeId, newClassName, Number(newValue))
      setNewClassName('')
      setNewValue('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditing(toleranceClass) {
    setEditingId(toleranceClass.tolerance_class_id)
    setEditingClassName(toleranceClass.class_name)
    setEditingValue(String(toleranceClass.value))
  }

  async function saveEdit(toleranceClassId) {
    setError(null)
    try {
      await updateToleranceClass(toleranceClassId, editingClassName, Number(editingValue))
      setEditingId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(toleranceClassId) {
    setError(null)
    try {
      await deleteToleranceClass(toleranceClassId)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <p>
        <Link to="/admin/process-types">&larr; Process types</Link>
      </p>
      <h2>Tolerance classes</h2>
      <table>
        <thead>
          <tr>
            <th>Class</th>
            <th>Value</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {toleranceClasses.map((toleranceClass) => (
            <tr key={toleranceClass.tolerance_class_id}>
              {editingId === toleranceClass.tolerance_class_id ? (
                <>
                  <td>
                    <input
                      value={editingClassName}
                      onChange={(e) => setEditingClassName(e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      step="any"
                      value={editingValue}
                      onChange={(e) => setEditingValue(e.target.value)}
                    />
                  </td>
                  <td>
                    <button onClick={() => saveEdit(toleranceClass.tolerance_class_id)}>Save</button>
                  </td>
                </>
              ) : (
                <>
                  <td>{toleranceClass.class_name}</td>
                  <td>{toleranceClass.value}</td>
                  <td>
                    <button onClick={() => startEditing(toleranceClass)}>Edit</button>{' '}
                    <button onClick={() => handleDelete(toleranceClass.tolerance_class_id)}>
                      Delete
                    </button>
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>

      <form onSubmit={handleCreate} className="inline-form">
        <input
          placeholder="Class name"
          value={newClassName}
          onChange={(e) => setNewClassName(e.target.value)}
          required
        />
        <input
          type="number"
          step="any"
          placeholder="Value"
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          required
        />
        <button type="submit">Create</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default ToleranceClassesPage
