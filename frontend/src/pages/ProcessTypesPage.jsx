import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createProcessType,
  deleteProcessType,
  importProcessType,
  importTemplateUrl,
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

  const [importName, setImportName] = useState('')
  const [importFile, setImportFile] = useState(null)
  const [importing, setImporting] = useState(false)
  // Controlled <input type="file"> can't have its value set directly
  // (browsers reject scripted assignment for security) -- a ref is the
  // standard way to reset the picker after a successful import.
  const importFileInputRef = useRef(null)

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

  async function handleImport(event) {
    event.preventDefault()
    setError(null)
    setImporting(true)
    try {
      await importProcessType(importName, importFile)
      setImportName('')
      setImportFile(null)
      if (importFileInputRef.current) {
        importFileInputRef.current.value = ''
      }
      refresh()
    } catch (err) {
      setError(err.message)
    } finally {
      setImporting(false)
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
                  <input type="text" value={editingName} onChange={(e) => setEditingName(e.target.value)} />
                ) : (
                  <Link to={`/client-admin/process-types/${processType.process_type_id}/tolerance-matrix`}>
                    {processType.name}
                  </Link>
                )}
              </td>
              <td>
                {editingId === processType.process_type_id ? (
                  <button type="button" onClick={() => saveEdit(processType.process_type_id)}>
                    Save
                  </button>
                ) : pendingDeleteId === processType.process_type_id ? (
                  <>
                    <span>Delete this process type?</span>{' '}
                    <button type="button" onClick={() => handleDelete(processType.process_type_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" onClick={() => setPendingDeleteId(null)}>
                      No
                    </button>
                  </>
                ) : (
                  <>
                    <button type="button" className="link-button" onClick={() => startEditing(processType)}>
                      Edit
                    </button>{' '}
                    <button
                      type="button"
                      className="link-button"
                      onClick={() => setPendingDeleteId(processType.process_type_id)}
                    >
                      Delete
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="section-divider" />

      <form onSubmit={handleCreate} className="inline-form">
        <label>
          New process type{' '}
          <input
            type="text"
            placeholder="New process type"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            required
          />
        </label>
        <button type="submit">Create</button>
      </form>

      <div className="section-divider" />

      {/* Always creates a brand-new process type from the file -- there's
          no existing matrix to merge into, so this is create-only, same
          as the form above. */}
      <form onSubmit={handleImport} className="inline-form">
        <label>
          Import new process type from CSV{' '}
          <input
            type="text"
            placeholder="Name"
            value={importName}
            onChange={(e) => setImportName(e.target.value)}
            required
          />
        </label>
        <label>
          File{' '}
          <input
            ref={importFileInputRef}
            type="file"
            accept=".csv"
            onChange={(e) => setImportFile(e.target.files[0] ?? null)}
            required
          />
        </label>
        <button type="submit" disabled={importing}>
          {importing ? 'Importing...' : 'Import'}
        </button>
        <a href={importTemplateUrl}>Download template</a>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default ProcessTypesPage
