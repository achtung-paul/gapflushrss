import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createAngledComponent,
  deleteAngledComponent,
  getAngledSimulation,
  listAngledComponents,
  updateAngledComponent,
  updateAngledSettings,
} from '../api/client.js'
import NumberInput from './NumberInput.jsx'

// Same RAG maps as ToleranceChainSection.jsx -- backend value uses an
// underscore (not_evaluated), CSS class is hyphenated, and .rag-badge sets
// white text with the background coming from this class, so a name that
// doesn't match renders white on white rather than obviously broken.
const RAG_LABELS = {
  green: 'Green',
  amber: 'Amber',
  red: 'Red',
  not_evaluated: 'Not evaluated',
}
const RAG_CLASS = {
  green: 'rag-green',
  amber: 'rag-amber',
  red: 'rag-red',
  not_evaluated: 'rag-not-evaluated',
}

const METHOD_LABELS = {
  WORST_CASE: 'Worst case',
  RSS: 'Statistical (RSS)',
}

// The angled-interface counterpart to ToleranceChainSection.jsx, shown
// instead of it when the entry's direction is OTHER (see
// AnalysisDetailPage.jsx). Resolves each component's X/Y tolerance onto
// the interface angle server-side (core/angled_simulation.py) and never
// re-implements cos/sin here -- the table only ever displays what the API
// already computed.
function AngledInterfaceSection({ projectId, entryId, interfaceAngle, calculationMethod, onEntryChanged }) {
  const [components, setComponents] = useState([])
  const [simulation, setSimulation] = useState(null)
  const [error, setError] = useState(null)
  const [pendingDeleteId, setPendingDeleteId] = useState(null)

  // Seeded from props, kept in sync when the parent's entry object
  // changes (e.g. after this component's own save) -- same pattern as
  // ToleranceMatrixPage's CellInputs syncing from its `cell` prop.
  const [angleInput, setAngleInput] = useState(String(interfaceAngle))
  const [method, setMethod] = useState(calculationMethod)

  useEffect(() => setAngleInput(String(interfaceAngle)), [interfaceAngle])
  useEffect(() => setMethod(calculationMethod), [calculationMethod])

  const [componentName, setComponentName] = useState('')
  const [xTolerance, setXTolerance] = useState('')
  const [yTolerance, setYTolerance] = useState('')
  const [note, setNote] = useState('')

  const [editingId, setEditingId] = useState(null)
  const [editComponentName, setEditComponentName] = useState('')
  const [editXTolerance, setEditXTolerance] = useState('')
  const [editYTolerance, setEditYTolerance] = useState('')
  const [editNote, setEditNote] = useState('')

  const refresh = useCallback(() => {
    listAngledComponents(projectId, entryId).then(setComponents).catch((err) => setError(err.message))
    getAngledSimulation(projectId, entryId).then(setSimulation).catch((err) => setError(err.message))
  }, [projectId, entryId])

  useEffect(refresh, [refresh])

  async function saveSettings(nextAngle, nextMethod) {
    setError(null)
    try {
      await updateAngledSettings(projectId, entryId, Number(nextAngle), nextMethod)
      refresh()
      onEntryChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  function handleMethodChange(nextMethod) {
    setMethod(nextMethod)
    saveSettings(angleInput, nextMethod)
  }

  async function handleAdd(event) {
    event.preventDefault()
    setError(null)
    try {
      await createAngledComponent(projectId, entryId, {
        component_name: componentName,
        x_tolerance: Number(xTolerance),
        y_tolerance: Number(yTolerance),
        note,
      })
      setComponentName('')
      setXTolerance('')
      setYTolerance('')
      setNote('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditing(component) {
    setEditingId(component.angled_component_id)
    setEditComponentName(component.component_name)
    setEditXTolerance(String(component.x_tolerance))
    setEditYTolerance(String(component.y_tolerance))
    setEditNote(component.note ?? '')
    setError(null)
  }

  async function handleSaveEdit(component) {
    setError(null)
    try {
      await updateAngledComponent(projectId, component.angled_component_id, {
        component_name: editComponentName,
        x_tolerance: Number(editXTolerance),
        y_tolerance: Number(editYTolerance),
        note: editNote,
      })
      setEditingId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(angledComponentId) {
    setError(null)
    try {
      await deleteAngledComponent(projectId, angledComponentId)
      setPendingDeleteId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  // simulation.rows carries the server-resolved Vx/Vy per component, in
  // the same order as `components` -- joined by id here rather than
  // assumed-same-index, so a row added/removed between the two fetches
  // can't misalign the table.
  const simulationRowById = new Map((simulation?.rows ?? []).map((row) => [row.angled_component_id, row]))

  return (
    <div className="tolerance-chain angled-interface">
      <h4>Angled interface</h4>
      {error && <p className="form-error">{error}</p>}

      <div className="inline-form angled-method-options">
        <label>
          Interface angle θ (°){' '}
          <NumberInput
            step={1}
            min="0"
            max="90"
            value={angleInput}
            onChange={setAngleInput}
            onBlur={() => saveSettings(angleInput, method)}
          />
        </label>
        <label>
          <input
            type="radio"
            name={`angled-method-${entryId}`}
            value="WORST_CASE"
            checked={method === 'WORST_CASE'}
            onChange={() => handleMethodChange('WORST_CASE')}
          />{' '}
          Worst case
        </label>
        <label>
          <input
            type="radio"
            name={`angled-method-${entryId}`}
            value="RSS"
            checked={method === 'RSS'}
            onChange={() => handleMethodChange('RSS')}
          />{' '}
          Statistical (RSS)
        </label>
      </div>
      <p className="form-hint">
        <Link to="/help/angled-interface">How angled DVA works</Link>
      </p>

      {components.length === 0 && (
        <p>No angled components yet -- add component X/Y tolerances below.</p>
      )}

      {components.length > 0 && (
        <table className="rss-results angled-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>X tolerance (± mm)</th>
              <th>Y tolerance (± mm)</th>
              <th>Vx (mm)</th>
              <th>Vy (mm)</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {components.map((component) => {
              const row = simulationRowById.get(component.angled_component_id)
              return editingId === component.angled_component_id ? (
                <tr key={component.angled_component_id}>
                  <td>
                    <input
                      type="text"
                      value={editComponentName}
                      onChange={(e) => setEditComponentName(e.target.value)}
                      required
                    />
                    <input
                      type="text"
                      className="angled-note-input"
                      maxLength={500}
                      placeholder="Note (optional)"
                      value={editNote}
                      onChange={(e) => setEditNote(e.target.value)}
                    />
                  </td>
                  <td className="angled-value">
                    <NumberInput min="0" value={editXTolerance} onChange={setEditXTolerance} required />
                  </td>
                  <td className="angled-value">
                    <NumberInput min="0" value={editYTolerance} onChange={setEditYTolerance} required />
                  </td>
                  <td className="angled-value">--</td>
                  <td className="angled-value">--</td>
                  <td>
                    <button type="button" onClick={() => handleSaveEdit(component)}>
                      Save
                    </button>{' '}
                    <button type="button" onClick={() => setEditingId(null)}>
                      Cancel
                    </button>
                  </td>
                </tr>
              ) : (
                <tr key={component.angled_component_id}>
                  <td>
                    {component.component_name}
                    {component.note && (
                      // Plain text, rendered as an ordinary React string --
                      // React escapes it, so it needs no sanitising.
                      <div className="contributor-note">{component.note}</div>
                    )}
                  </td>
                  <td className="angled-value">±{component.x_tolerance} mm</td>
                  <td className="angled-value">±{component.y_tolerance} mm</td>
                  <td className="angled-value">{row ? row.vx.toFixed(3) : '--'}</td>
                  <td className="angled-value">{row ? row.vy.toFixed(3) : '--'}</td>
                  <td>
                    {pendingDeleteId === component.angled_component_id ? (
                      <>
                        <span>Delete this row?</span>{' '}
                        <button type="button" onClick={() => handleDelete(component.angled_component_id)}>
                          Yes
                        </button>{' '}
                        <button type="button" onClick={() => setPendingDeleteId(null)}>
                          No
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" onClick={() => startEditing(component)}>
                          Edit
                        </button>{' '}
                        <button
                          type="button"
                          onClick={() => setPendingDeleteId(component.angled_component_id)}
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}

      <form onSubmit={handleAdd} className="inline-form">
        <label>
          Component name{' '}
          <input
            type="text"
            placeholder="Component name"
            value={componentName}
            onChange={(e) => setComponentName(e.target.value)}
            required
          />
        </label>
        <label>
          X tolerance (± mm){' '}
          <NumberInput min="0" placeholder="X tolerance" value={xTolerance} onChange={setXTolerance} required />
        </label>
        <label>
          Y tolerance (± mm){' '}
          <NumberInput min="0" placeholder="Y tolerance" value={yTolerance} onChange={setYTolerance} required />
        </label>
        <label>
          Note{' '}
          <input
            type="text"
            maxLength={500}
            placeholder="Optional"
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        <button type="submit">Add component</button>
      </form>

      {simulation && (
        <div className="angled-total">
          <div className="angled-total-label">Total angled variation</div>
          <div className="angled-total-value">
            ±{simulation.total_variation.toFixed(3)} mm{' '}
            <span className={`rag-badge ${RAG_CLASS[simulation.rag] ?? ''}`}>
              {RAG_LABELS[simulation.rag] ?? simulation.rag}
            </span>
          </div>
          <div className="angled-total-detail">
            Predicted {simulation.lower_bound.toFixed(3)} to {simulation.upper_bound.toFixed(3)} mm ·{' '}
            {METHOD_LABELS[simulation.calculation_method] ?? simulation.calculation_method}, θ ={' '}
            {simulation.interface_angle}° · {components.length} component
            {components.length === 1 ? '' : 's'}
          </div>
        </div>
      )}
    </div>
  )
}

export default AngledInterfaceSection
