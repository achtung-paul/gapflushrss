import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
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
  green: 'Pass',
  amber: 'Caution',
  red: 'Fail',
  not_evaluated: 'Not evaluated',
}

// Mapped explicitly rather than interpolated as `rag-${result.rag}`: the
// backend's value uses an underscore (not_evaluated) while the CSS class
// is hyphenated -- a name that doesn't match one of the four modifiers
// falls back to .rag-badge's own neutral colour rather than an
// unstyled, easy-to-miss badge.
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

// Which of a process type's dimension ranges a measured dimension falls
// into, or null if it's outside all of them. Ranges are stored as plain
// [min_value, max_value] pairs with no inclusive/exclusive flag, so a
// value sitting exactly on the boundary between two adjacent ranges
// (e.g. 3 for both "1 to 3" and "3 to 6") matches both -- resolved by
// preferring the one with the larger numbers, i.e. the range this value
// is the *lower* edge of. That matches the tolerance standard's own
// convention for how these ranges are meant to be read (see the CSV
// import format's "> 3 to 6" labelling, core/tolerance_csv_import.py),
// where every range but the first is explicitly open on its lower
// bound.
function findMatchingRange(ranges, dimension) {
  const d = Number(dimension)
  if (dimension === '' || Number.isNaN(d)) {
    return null
  }
  const candidates = ranges.filter((r) => d >= Number(r.min_value) && d <= Number(r.max_value))
  if (candidates.length === 0) {
    return null
  }
  return candidates.reduce((largest, r) => (Number(r.min_value) > Number(largest.min_value) ? r : largest))
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
  const [measured, setMeasured] = useState('')
  const [material, setMaterial] = useState('')
  const [standardTolerances, setStandardTolerances] = useState([])

  // Editing an existing contributor swaps its <li> for this same set of
  // fields, pre-filled -- deliberately simpler than the add form: it
  // doesn't re-expose the process-type/group/range/variance or standard-
  // tolerance pickers (those are create-time convenience for prefilling
  // a value), just the fields that were actually saved.
  // tolerance_value_id is sent back unchanged on save, since hand-
  // editing the number may no longer match the cell it came from.
  const [editingId, setEditingId] = useState(null)
  const [editContributorType, setEditContributorType] = useState('COMPONENT')
  const [editDescription, setEditDescription] = useState('')
  const [editToleranceValue, setEditToleranceValue] = useState('')
  const [editNote, setEditNote] = useState('')
  const [editMeasured, setEditMeasured] = useState('')
  const [editMaterial, setEditMaterial] = useState('')

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

  // Re-runs whenever the typed Measured value changes (or the range list
  // loads) -- reused as the dimension for auto-picking the matching
  // Dimension range below, since that's the same number: the actual size
  // of the feature being toleranced is exactly what a size-based
  // tolerance standard looks up. Deliberately independent of which
  // tolerance group is selected, since dimension ranges are the matrix's
  // columns, shared across every group/row (see models/dimension_range.py),
  // not scoped per group. Only ever *sets* selectedRangeId, never clears
  // it -- a measured value outside every range, or an empty box, just
  // leaves whatever range was picked before alone, so a manual override
  // is never stomped by this effect re-running with the same match.
  useEffect(() => {
    const match = findMatchingRange(ranges, measured)
    if (match) {
      setSelectedRangeId(String(match.dimension_range_id))
      setSelectedVariance('')
    }
  }, [measured, ranges])

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
        measured_value: measured === '' ? null : Number(measured),
        material,
      })
      setTypeSelection('COMPONENT')
      setDescription('')
      setNote('')
      setMeasured('')
      setMaterial('')
      setManualToleranceValue('')
      // selectedProcessTypeId deliberately survives the reset -- once a
      // Tol matrix is picked, it stays the default for the next
      // contributor too, since a chain is usually built from the same
      // matrix component after component. Group/range/variance still
      // reset, since those are specific to the one cell just added.
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
    setEditMeasured(component.measured_value === null ? '' : String(component.measured_value))
    setEditMaterial(component.material ?? '')
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
        measured_value: editMeasured === '' ? null : Number(editMeasured),
        material: editMaterial,
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

      {components.length > 0 && (
        <table className="rss-results contributor-table">
          <thead>
            <tr>
              <th>Type</th>
              <th>Description</th>
              <th>Tolerance (± mm)</th>
              <th>Measured (mm)</th>
              <th>Material</th>
              <th>Tolerance group</th>
              <th>Note</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {components.map((component) =>
              editingId === component.chain_component_id ? (
                <tr key={component.chain_component_id}>
                  <td>
                    <select
                      value={editContributorType}
                      onChange={(e) => setEditContributorType(e.target.value)}
                    >
                      <option value="COMPONENT">Component tolerance</option>
                      <option value="PROCESS">Assembly process variation</option>
                    </select>
                  </td>
                  <td>
                    <input
                      type="text"
                      value={editDescription}
                      onChange={(e) => setEditDescription(e.target.value)}
                      required
                    />
                  </td>
                  <td>
                    <NumberInput min="0" value={editToleranceValue} onChange={setEditToleranceValue} required />
                  </td>
                  <td>
                    <NumberInput value={editMeasured} onChange={setEditMeasured} />
                  </td>
                  <td>
                    <input
                      type="text"
                      maxLength={255}
                      value={editMaterial}
                      onChange={(e) => setEditMaterial(e.target.value)}
                    />
                  </td>
                  {/* Not editable here -- see the comment on editingId
                      above for why (create-time-only pickers). */}
                  <td>{component.tolerance_group_name || '--'}</td>
                  <td>
                    <input
                      type="text"
                      maxLength={500}
                      value={editNote}
                      onChange={(e) => setEditNote(e.target.value)}
                    />
                  </td>
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
                <tr key={component.chain_component_id}>
                  <td>{CONTRIBUTOR_TYPE_LABELS[component.contributor_type] ?? component.contributor_type}</td>
                  <td>{component.description}</td>
                  <td>±{component.tolerance_value} mm</td>
                  <td>{component.measured_value !== null ? `${component.measured_value} mm` : '--'}</td>
                  <td>{component.material || '--'}</td>
                  <td>{component.tolerance_group_name || '--'}</td>
                  {/* Plain text, rendered as an ordinary React string -- any
                      markup someone types here shows as literal characters,
                      which is why this field needs no sanitising (unlike the
                      entry notes above). */}
                  <td>{component.note || '--'}</td>
                  <td>
                    {pendingDeleteId === component.chain_component_id ? (
                      <>
                        <span>Delete?</span>{' '}
                        <button type="button" onClick={() => handleDelete(component.chain_component_id)}>
                          Yes
                        </button>{' '}
                        <button type="button" onClick={() => setPendingDeleteId(null)}>
                          No
                        </button>
                      </>
                    ) : (
                      <>
                        <button type="button" className="link-button" onClick={() => startEditing(component)}>
                          Edit
                        </button>{' '}
                        <button
                          type="button"
                          className="link-button"
                          onClick={() => setPendingDeleteId(component.chain_component_id)}
                        >
                          Delete
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      )}

      <div className="section-divider" />

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
        <label>
          Measured (mm){' '}
          <NumberInput placeholder="Optional" value={measured} onChange={setMeasured} />
        </label>
        <label>
          Material{' '}
          <input
            type="text"
            maxLength={255}
            placeholder="Optional"
            value={material}
            onChange={(e) => setMaterial(e.target.value)}
          />
        </label>
        {!selectedStandard && (
          <>
            <label>
              Tol matrix{' '}
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

      <div className="section-divider" />

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
                  <td>
                    <span className={`rag-badge ${result.info_only ? 'rag-info' : RAG_CLASS[result.rag] ?? ''}`}>
                      {result.info_only ? 'Info' : RAG_LABELS[result.rag] ?? result.rag}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="form-hint">
            <Link to="/help/statistical-model">About the statistical model</Link>
          </p>
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
