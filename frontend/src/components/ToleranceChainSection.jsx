import { useCallback, useEffect, useState } from 'react'
import {
  createChainComponent,
  deleteChainComponent,
  getSimulation,
  listChainComponents,
  listDimensionRanges,
  listProcessTypes,
  listStandardTolerances,
  listToleranceGroups,
  listToleranceValues,
  updateChainComponent,
} from '../api/client.js'
import NumberInput from './NumberInput.jsx'
import RssDistributionChart from './RssDistributionChart.jsx'

// not_evaluated is what the backend returns when the chain is still empty
// -- there's no verdict to give yet (see core/simulation.py).
const RAG_LABELS = {
  green: 'Green',
  amber: 'Amber',
  red: 'Red',
  not_evaluated: 'Not evaluated',
}

// Mapped explicitly rather than interpolated as `rag-${result.rag}`: the
// backend's value uses an underscore (not_evaluated) while the CSS class
// is hyphenated, and .rag-badge sets white text with the background
// coming from this class -- so a name that doesn't match renders white on
// white, i.e. an invisible badge rather than an obviously broken one.
const RAG_CLASS = {
  green: 'rag-green',
  amber: 'rag-amber',
  red: 'rag-red',
  not_evaluated: 'rag-not-evaluated',
}

const CONTRIBUTOR_TYPE_LABELS = {
  COMPONENT: 'Component tolerance',
  PROCESS: 'Assembly process variation',
}

// standard:<id> namespaces a preset's id inside the same string-valued
// <select> as the two base contributor types, so "Type" is one control
// instead of two (a Type dropdown plus a separate Standard tolerance
// dropdown) -- the two used to require touching both to describe one
// contributor.
function standardOptionValue(standardToleranceId) {
  return `standard:${standardToleranceId}`
}

// Lets the user build the RSS tolerance chain for one Gap/Flush entry
// (brief step 4: component tolerances + assembly-process variation),
// then shows the computed 3/4/5 sigma simulation (brief steps 5-6)
// against the entry's own nominal/tolerance band.
function ToleranceChainSection({ projectId, entryId, nominal, upperLimit, lowerLimit }) {
  const [components, setComponents] = useState([])
  const [simulation, setSimulation] = useState(null)
  const [error, setError] = useState(null)
  const [pendingDeleteId, setPendingDeleteId] = useState(null)

  // 'COMPONENT', 'PROCESS', or `standard:<standard_tolerance_id>` -- see
  // standardOptionValue above.
  const [typeSelection, setTypeSelection] = useState('COMPONENT')
  const [description, setDescription] = useState('')
  // Only used when neither a preset nor a matrix cell supplies a value
  // (see pickedValue below) -- otherwise that value is shown read-only
  // via the picker itself, and this box is hidden entirely so the
  // number is never shown twice.
  const [manualToleranceValue, setManualToleranceValue] = useState('')

  const [processTypes, setProcessTypes] = useState([])
  const [selectedProcessTypeId, setSelectedProcessTypeId] = useState('')
  const [groups, setGroups] = useState([])
  const [selectedGroupId, setSelectedGroupId] = useState('')
  const [ranges, setRanges] = useState([])
  const [selectedRangeId, setSelectedRangeId] = useState('')
  const [cells, setCells] = useState([])
  const [selectedVariance, setSelectedVariance] = useState('')

  const [note, setNote] = useState('')
  const [standardTolerances, setStandardTolerances] = useState([])

  // Editing an existing contributor swaps its <li> for this same set of
  // fields, pre-filled -- deliberately simpler than the add form: it
  // doesn't re-expose the process-type/group/range/variance or standard-
  // tolerance pickers (those are create-time convenience for prefilling
  // a value), just the three fields that were actually saved.
  // tolerance_value_id is sent back unchanged on save, since hand-
  // editing the number may no longer match the cell it came from.
  const [editingId, setEditingId] = useState(null)
  const [editContributorType, setEditContributorType] = useState('COMPONENT')
  const [editDescription, setEditDescription] = useState('')
  const [editToleranceValue, setEditToleranceValue] = useState('')
  const [editNote, setEditNote] = useState('')

  const refresh = useCallback(() => {
    listChainComponents(projectId, entryId).then(setComponents).catch((err) => setError(err.message))
    getSimulation(projectId, entryId).then(setSimulation).catch((err) => setError(err.message))
  }, [projectId, entryId])

  useEffect(refresh, [refresh])

  useEffect(() => {
    listProcessTypes().then(setProcessTypes).catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    listStandardTolerances(projectId).then(setStandardTolerances).catch((err) => setError(err.message))
  }, [projectId])

  useEffect(() => {
    if (!selectedProcessTypeId) {
      setGroups([])
      setRanges([])
      setCells([])
      return
    }
    listToleranceGroups(selectedProcessTypeId).then(setGroups).catch((err) => setError(err.message))
    listDimensionRanges(selectedProcessTypeId).then(setRanges).catch((err) => setError(err.message))
    listToleranceValues(selectedProcessTypeId).then(setCells).catch((err) => setError(err.message))
  }, [selectedProcessTypeId])

  const selectedStandard = standardTolerances.find(
    (s) => typeSelection === standardOptionValue(s.standard_tolerance_id),
  )

  // The matrix cell for whichever group + range are currently picked,
  // if one exists -- a blank "-" cell in the admin matrix has no row at
  // all (see backend/app/api/reference_data.py), so no match just means
  // "nothing to prefill, enter the value manually". Irrelevant (and
  // harmless) once a preset is selected -- the matrix pickers are
  // hidden and their selections cleared by handleTypeChange below.
  const matchedCell = cells.find(
    (cell) =>
      String(cell.tolerance_group_id) === selectedGroupId &&
      String(cell.dimension_range_id) === selectedRangeId,
  )
  const hasBothVariances =
    matchedCell && matchedCell.tool_value !== null && matchedCell.non_tool_value !== null

  // The value the matrix currently supplies, or null if it doesn't (no
  // cell matched, or a both-variance cell with neither variance picked
  // yet). Plain derivation rather than a useEffect pushing into state --
  // there's nothing to synchronise, so nothing to get stale.
  const matrixValue = !matchedCell
    ? null
    : hasBothVariances
      ? selectedVariance === 'tool'
        ? matchedCell.tool_value
        : selectedVariance === 'non_tool'
          ? matchedCell.non_tool_value
          : null
      : (matchedCell.tool_value ?? matchedCell.non_tool_value)

  // The one number this contributor will save with, from whichever
  // source is currently active -- a preset beats the matrix, since
  // picking one hides the matrix pickers entirely (see the JSX below).
  // null means neither supplies a value yet, which is exactly when the
  // manual Tolerance box needs to be shown.
  const pickedValue = selectedStandard ? Number(selectedStandard.tolerance_value) : matrixValue

  function handleTypeChange(value) {
    setTypeSelection(value)
    const standardId = value.startsWith('standard:') ? Number(value.slice('standard:'.length)) : null
    if (standardId !== null) {
      // Picking a preset is the same convenience the old, separate
      // Standard tolerance dropdown gave: prefill the description and
      // drop the matrix pickers, since the preset already carries its
      // own value.
      const standard = standardTolerances.find((s) => s.standard_tolerance_id === standardId)
      if (standard) {
        setDescription(standard.name)
      }
      setSelectedProcessTypeId('')
      setSelectedGroupId('')
      setSelectedRangeId('')
      setSelectedVariance('')
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    try {
      const contributorType = selectedStandard ? selectedStandard.contributor_type : typeSelection
      const toleranceValue = pickedValue !== null ? pickedValue : Number(manualToleranceValue)
      await createChainComponent(projectId, entryId, {
        contributor_type: contributorType,
        description,
        tolerance_value: toleranceValue,
        // Only true provenance when the value actually came from the
        // matrix -- a preset's own tolerance_value_id would misrepresent
        // where this contributor's number came from.
        tolerance_value_id: !selectedStandard && matchedCell ? matchedCell.tolerance_value_id : null,
        note,
      })
      setTypeSelection('COMPONENT')
      setDescription('')
      setNote('')
      setManualToleranceValue('')
      setSelectedProcessTypeId('')
      setSelectedGroupId('')
      setSelectedRangeId('')
      setSelectedVariance('')
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditing(component) {
    setEditingId(component.chain_component_id)
    setEditContributorType(component.contributor_type)
    setEditDescription(component.description)
    setEditToleranceValue(String(component.tolerance_value))
    setEditNote(component.note ?? '')
    setError(null)
  }

  async function handleSaveEdit(component) {
    setError(null)
    try {
      await updateChainComponent(projectId, component.chain_component_id, {
        contributor_type: editContributorType,
        description: editDescription,
        tolerance_value: Number(editToleranceValue),
        tolerance_value_id: component.tolerance_value_id,
        note: editNote,
      })
      setEditingId(null)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleDelete = useCallback(
    async (chainComponentId) => {
      setError(null)
      try {
        await deleteChainComponent(projectId, chainComponentId)
        setPendingDeleteId(null)
        refresh()
      } catch (err) {
        setError(err.message)
      }
    },
    [projectId, refresh],
  )

  return (
    <div className="tolerance-chain">
      <h4>Tolerance chain</h4>
      {error && <p className="form-error">{error}</p>}

      {components.length === 0 && (
        <p>No chain components yet -- add component tolerances and assembly-process variations below.</p>
      )}

      <ul>
        {components.map((component) =>
          editingId === component.chain_component_id ? (
            <li key={component.chain_component_id}>
              <label>
                Type{' '}
                <select value={editContributorType} onChange={(e) => setEditContributorType(e.target.value)}>
                  <option value="COMPONENT">Component tolerance</option>
                  <option value="PROCESS">Assembly process variation</option>
                </select>
              </label>{' '}
              <label>
                Description{' '}
                <input
                  type="text"
                  value={editDescription}
                  onChange={(e) => setEditDescription(e.target.value)}
                  required
                />
              </label>{' '}
              <label>
                Tolerance (± mm){' '}
                <NumberInput min="0" value={editToleranceValue} onChange={setEditToleranceValue} required />
              </label>{' '}
              <label>
                Note{' '}
                <input
                  type="text"
                  maxLength={500}
                  value={editNote}
                  onChange={(e) => setEditNote(e.target.value)}
                />
              </label>{' '}
              <button type="button" onClick={() => handleSaveEdit(component)}>
                Save
              </button>{' '}
              <button type="button" onClick={() => setEditingId(null)}>
                Cancel
              </button>
            </li>
          ) : (
            <li key={component.chain_component_id}>
              [{component.contributor_type}] {component.description}: ±{component.tolerance_value} mm{' '}
              {pendingDeleteId === component.chain_component_id ? (
                <>
                  <span>Delete this contributor?</span>{' '}
                  <button type="button" onClick={() => handleDelete(component.chain_component_id)}>
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
                  <button type="button" onClick={() => setPendingDeleteId(component.chain_component_id)}>
                    Delete
                  </button>
                </>
              )}
              {component.note && (
                // Plain text, rendered as an ordinary React string -- any
                // markup someone types here shows as literal characters,
                // which is why this field needs no sanitising (unlike the
                // entry notes above).
                <div className="contributor-note">{component.note}</div>
              )}
            </li>
          ),
        )}
      </ul>

      <form onSubmit={handleSubmit} className="inline-form">
        <label>
          Type{' '}
          <select value={typeSelection} onChange={(e) => handleTypeChange(e.target.value)}>
            <option value="COMPONENT">Component tolerance</option>
            <option value="PROCESS">Assembly process variation</option>
            {standardTolerances.length > 0 && (
              <optgroup label="Standard tolerances">
                {standardTolerances.map((standard) => (
                  <option
                    key={standard.standard_tolerance_id}
                    value={standardOptionValue(standard.standard_tolerance_id)}
                  >
                    {standard.name} (±{standard.tolerance_value} mm,{' '}
                    {CONTRIBUTOR_TYPE_LABELS[standard.contributor_type] ?? standard.contributor_type})
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </label>
        <label>
          Description{' '}
          <input
            type="text"
            placeholder="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            required
          />
        </label>
        {!selectedStandard && (
          <>
            <label>
              DIN matrix{' '}
              <select
                value={selectedProcessTypeId}
                onChange={(e) => {
                  setSelectedProcessTypeId(e.target.value)
                  setSelectedGroupId('')
                  setSelectedRangeId('')
                  setSelectedVariance('')
                }}
              >
                <option value="">(manual value)</option>
                {processTypes.map((processType) => (
                  <option key={processType.process_type_id} value={processType.process_type_id}>
                    {processType.name}
                  </option>
                ))}
              </select>
            </label>
            {selectedProcessTypeId && (
              <>
                <label>
                  Tolerance group{' '}
                  <select
                    value={selectedGroupId}
                    onChange={(e) => {
                      setSelectedGroupId(e.target.value)
                      setSelectedVariance('')
                    }}
                  >
                    <option value="">Tolerance group...</option>
                    {groups.map((group) => (
                      <option key={group.tolerance_group_id} value={group.tolerance_group_id}>
                        {group.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Dimension range (mm){' '}
                  <select
                    value={selectedRangeId}
                    onChange={(e) => {
                      setSelectedRangeId(e.target.value)
                      setSelectedVariance('')
                    }}
                  >
                    <option value="">Dimension range...</option>
                    {ranges.map((range) => (
                      <option key={range.dimension_range_id} value={range.dimension_range_id}>
                        {range.min_value} to {range.max_value} mm
                      </option>
                    ))}
                  </select>
                </label>
              </>
            )}
            {hasBothVariances && (
              <label>
                Variance{' '}
                <select value={selectedVariance} onChange={(e) => setSelectedVariance(e.target.value)}>
                  <option value="">Tool or non-tool...</option>
                  <option value="tool">Tool-specific (±{matchedCell.tool_value} mm)</option>
                  <option value="non_tool">Non-tool-specific (±{matchedCell.non_tool_value} mm)</option>
                </select>
              </label>
            )}
            {selectedGroupId && selectedRangeId && !matchedCell && (
              <span className="form-hint">No value defined for this cell -- enter manually</span>
            )}
          </>
        )}
        {pickedValue === null && (
          <label>
            Tolerance (± mm){' '}
            <NumberInput
              min="0"
              placeholder="Tolerance (±)"
              value={manualToleranceValue}
              onChange={setManualToleranceValue}
              required
            />
          </label>
        )}
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
        <button type="submit">Add contributor</button>
      </form>

      {simulation && (
        <>
          <table className="rss-results">
            <thead>
              <tr>
                <th>Sigma level</th>
                <th>Spread (± mm)</th>
                <th>Predicted range (mm)</th>
                <th>RAG</th>
              </tr>
            </thead>
            <tbody>
              {simulation.results.map((result) => (
                <tr key={result.sigma_level}>
                  <td>{result.sigma_level}σ</td>
                  <td>{result.spread.toFixed(3)} mm</td>
                  <td>
                    {result.lower_bound.toFixed(3)} to {result.upper_bound.toFixed(3)} mm
                  </td>
                  <td className={`rag-badge ${RAG_CLASS[result.rag] ?? ''}`}>
                    {RAG_LABELS[result.rag] ?? result.rag}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <RssDistributionChart
            nominal={nominal}
            upperLimit={upperLimit}
            lowerLimit={lowerLimit}
            sigma1={simulation.sigma_1}
            results={simulation.results}
          />
        </>
      )}
    </div>
  )
}

export default ToleranceChainSection
