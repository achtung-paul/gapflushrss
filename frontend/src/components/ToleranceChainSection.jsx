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
import RssDistributionChart from './RssDistributionChart.jsx'

const RAG_LABELS = { green: 'Green', amber: 'Amber', red: 'Red' }

// Lets the user build the RSS tolerance chain for one Gap/Flush entry
// (brief step 4: component tolerances + assembly-process variation),
// then shows the computed 3/4/5 sigma simulation (brief steps 5-6)
// against the entry's own nominal/tolerance band.
function ToleranceChainSection({ projectId, entryId, nominal, upperLimit, lowerLimit }) {
  const [components, setComponents] = useState([])
  const [simulation, setSimulation] = useState(null)
  const [error, setError] = useState(null)
  const [pendingDeleteId, setPendingDeleteId] = useState(null)

  const [contributorType, setContributorType] = useState('COMPONENT')
  const [description, setDescription] = useState('')
  const [toleranceValue, setToleranceValue] = useState('')

  const [processTypes, setProcessTypes] = useState([])
  const [selectedProcessTypeId, setSelectedProcessTypeId] = useState('')
  const [groups, setGroups] = useState([])
  const [selectedGroupId, setSelectedGroupId] = useState('')
  const [ranges, setRanges] = useState([])
  const [selectedRangeId, setSelectedRangeId] = useState('')
  const [cells, setCells] = useState([])
  const [selectedVariant, setSelectedVariant] = useState('')

  const [standardTolerances, setStandardTolerances] = useState([])
  const [selectedStandardToleranceId, setSelectedStandardToleranceId] = useState('')

  // Editing an existing contributor swaps its <li> for this same set of
  // fields, pre-filled -- deliberately simpler than the add form: it
  // doesn't re-expose the process-type/group/range/variant or standard-
  // tolerance pickers (those are create-time convenience for prefilling
  // a value), just the three fields that were actually saved.
  // tolerance_value_id is sent back unchanged on save, since hand-
  // editing the number may no longer match the cell it came from.
  const [editingId, setEditingId] = useState(null)
  const [editContributorType, setEditContributorType] = useState('COMPONENT')
  const [editDescription, setEditDescription] = useState('')
  const [editToleranceValue, setEditToleranceValue] = useState('')

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

  // The matrix cell for whichever group + range are currently picked,
  // if one exists -- a blank "-" cell in the admin matrix has no row at
  // all (see backend/app/api/reference_data.py), so no match just means
  // "nothing to prefill, enter the value manually".
  const matchedCell = cells.find(
    (cell) =>
      String(cell.tolerance_group_id) === selectedGroupId &&
      String(cell.dimension_range_id) === selectedRangeId,
  )
  const hasBothVariants =
    matchedCell && matchedCell.tool_value !== null && matchedCell.non_tool_value !== null

  useEffect(() => {
    if (!matchedCell) {
      return
    }
    if (hasBothVariants) {
      if (selectedVariant === 'tool') {
        setToleranceValue(String(matchedCell.tool_value))
      } else if (selectedVariant === 'non_tool') {
        setToleranceValue(String(matchedCell.non_tool_value))
      }
    } else if (matchedCell.tool_value !== null) {
      setToleranceValue(String(matchedCell.tool_value))
    } else if (matchedCell.non_tool_value !== null) {
      setToleranceValue(String(matchedCell.non_tool_value))
    }
  }, [matchedCell, hasBothVariants, selectedVariant])

  function handleSelectStandardTolerance(standardToleranceId) {
    setSelectedStandardToleranceId(standardToleranceId)
    const standard = standardTolerances.find(
      (s) => String(s.standard_tolerance_id) === standardToleranceId,
    )
    if (standard) {
      setDescription(standard.name)
      setToleranceValue(String(standard.tolerance_value))
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    try {
      await createChainComponent(projectId, entryId, {
        contributor_type: contributorType,
        description,
        tolerance_value: Number(toleranceValue),
        tolerance_value_id: matchedCell ? matchedCell.tolerance_value_id : null,
      })
      setDescription('')
      setToleranceValue('')
      setSelectedProcessTypeId('')
      setSelectedGroupId('')
      setSelectedRangeId('')
      setSelectedVariant('')
      setSelectedStandardToleranceId('')
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
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  value={editToleranceValue}
                  onChange={(e) => setEditToleranceValue(e.target.value)}
                  required
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
            </li>
          ),
        )}
      </ul>

      <form onSubmit={handleSubmit} className="inline-form">
        <label>
          Type{' '}
          <select value={contributorType} onChange={(e) => setContributorType(e.target.value)}>
            <option value="COMPONENT">Component tolerance</option>
            <option value="PROCESS">Assembly process variation</option>
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
          DIN matrix{' '}
          <select
            value={selectedProcessTypeId}
            onChange={(e) => {
              setSelectedProcessTypeId(e.target.value)
              setSelectedGroupId('')
              setSelectedRangeId('')
              setSelectedVariant('')
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
                  setSelectedVariant('')
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
                  setSelectedVariant('')
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
        {hasBothVariants && (
          <label>
            Variant{' '}
            <select value={selectedVariant} onChange={(e) => setSelectedVariant(e.target.value)}>
              <option value="">Tool or non-tool...</option>
              <option value="tool">Tool-specific (±{matchedCell.tool_value} mm)</option>
              <option value="non_tool">Non-tool-specific (±{matchedCell.non_tool_value} mm)</option>
            </select>
          </label>
        )}
        {selectedGroupId && selectedRangeId && !matchedCell && (
          <span className="form-hint">No value defined for this cell -- enter manually</span>
        )}
        <label>
          Standard tolerance{' '}
          <select
            value={selectedStandardToleranceId}
            onChange={(e) => handleSelectStandardTolerance(e.target.value)}
          >
            <option value="">(none)</option>
            {standardTolerances.map((standard) => (
              <option key={standard.standard_tolerance_id} value={standard.standard_tolerance_id}>
                {standard.name} (±{standard.tolerance_value} mm)
              </option>
            ))}
          </select>
        </label>
        <label>
          Tolerance (± mm){' '}
          <input
            type="number"
            step="0.1"
            min="0"
            placeholder="Tolerance (±)"
            value={toleranceValue}
            onChange={(e) => setToleranceValue(e.target.value)}
            required
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
                  <td className={`rag-badge rag-${result.rag}`}>{RAG_LABELS[result.rag]}</td>
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
