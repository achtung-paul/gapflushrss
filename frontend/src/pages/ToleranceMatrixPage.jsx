import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  createDimensionRange,
  createToleranceGroup,
  deleteDimensionRange,
  deleteToleranceGroup,
  listDimensionRanges,
  listToleranceGroups,
  listToleranceValues,
  setToleranceValueCell,
} from '../api/client.js'

function cellKey(groupId, rangeId) {
  return `${groupId}-${rangeId}`
}

// One tool-value/non-tool-value pair, editable in place. Committed on
// blur (rather than on every keystroke) so we're not firing a network
// request per character typed.
function CellInputs({ cell, onSave }) {
  const [toolValue, setToolValue] = useState(cell?.tool_value ?? '')
  const [nonToolValue, setNonToolValue] = useState(cell?.non_tool_value ?? '')

  useEffect(() => {
    setToolValue(cell?.tool_value ?? '')
    setNonToolValue(cell?.non_tool_value ?? '')
  }, [cell])

  function handleBlur() {
    onSave(toolValue === '' ? null : Number(toolValue), nonToolValue === '' ? null : Number(nonToolValue))
  }

  return (
    <div className="matrix-cell">
      <label title="Tool-specific (mm)">
        T{' '}
        <input
          type="number"
          step="0.1"
          placeholder="T"
          title="Tool-specific"
          value={toolValue}
          onChange={(e) => setToolValue(e.target.value)}
          onBlur={handleBlur}
        />
      </label>
      <label title="Non-tool-specific (mm)">
        NT{' '}
        <input
          type="number"
          step="0.1"
          placeholder="NT"
          title="Non-tool-specific"
          value={nonToolValue}
          onChange={(e) => setNonToolValue(e.target.value)}
          onBlur={handleBlur}
        />
      </label>
    </div>
  )
}

// The admin-editable tolerance matrix for one process type -- rows are
// user-defined tolerance groups (e.g. "TG1"), columns are user-defined
// dimension ranges (e.g. "1 to 3" mm), each cell an optional
// tool-specific/non-tool-specific +/- pair. Matches the DIN 16742
// "Limit dimensions" table shape, without any values pre-filled in.
function ToleranceMatrixPage() {
  const { processTypeId } = useParams()
  const [groups, setGroups] = useState([])
  const [ranges, setRanges] = useState([])
  const [cells, setCells] = useState({})
  const [error, setError] = useState(null)

  const [newGroupName, setNewGroupName] = useState('')
  const [newRangeMin, setNewRangeMin] = useState('')
  const [newRangeMax, setNewRangeMax] = useState('')
  const [pendingDeleteGroupId, setPendingDeleteGroupId] = useState(null)
  const [pendingDeleteRangeId, setPendingDeleteRangeId] = useState(null)

  const refreshGroups = useCallback(() => {
    listToleranceGroups(processTypeId).then(setGroups).catch((err) => setError(err.message))
  }, [processTypeId])

  const refreshRanges = useCallback(() => {
    listDimensionRanges(processTypeId).then(setRanges).catch((err) => setError(err.message))
  }, [processTypeId])

  const refreshCells = useCallback(() => {
    listToleranceValues(processTypeId)
      .then((values) => {
        const byKey = {}
        for (const value of values) {
          byKey[cellKey(value.tolerance_group_id, value.dimension_range_id)] = value
        }
        setCells(byKey)
      })
      .catch((err) => setError(err.message))
  }, [processTypeId])

  useEffect(refreshGroups, [refreshGroups])
  useEffect(refreshRanges, [refreshRanges])
  useEffect(refreshCells, [refreshCells])

  async function handleAddGroup(event) {
    event.preventDefault()
    setError(null)
    try {
      await createToleranceGroup(processTypeId, newGroupName)
      setNewGroupName('')
      refreshGroups()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteGroup(groupId) {
    setError(null)
    try {
      await deleteToleranceGroup(groupId)
      setPendingDeleteGroupId(null)
      refreshGroups()
      refreshCells()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleAddRange(event) {
    event.preventDefault()
    setError(null)
    try {
      await createDimensionRange(processTypeId, Number(newRangeMin), Number(newRangeMax))
      setNewRangeMin('')
      setNewRangeMax('')
      refreshRanges()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteRange(rangeId) {
    setError(null)
    try {
      await deleteDimensionRange(rangeId)
      setPendingDeleteRangeId(null)
      refreshRanges()
      refreshCells()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleSaveCell(groupId, rangeId, toolValue, nonToolValue) {
    setError(null)
    try {
      await setToleranceValueCell(groupId, rangeId, toolValue, nonToolValue)
      refreshCells()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <p>
        <Link to="/admin/process-types">&larr; Process types</Link>
      </p>
      <h2>Tolerance matrix</h2>
      <p>
        Each cell holds a tool-specific (T) and/or non-tool-specific (NT) symmetric ± value. Leave
        both blank for a cell that doesn't apply to that group/range combination.
      </p>
      {error && <p className="form-error">{error}</p>}

      <div className="tolerance-matrix-scroll">
        <table className="tolerance-matrix">
          <thead>
            <tr>
              <th>Tolerance group</th>
              {ranges.map((range) => (
                <th key={range.dimension_range_id}>
                  {range.min_value} to {range.max_value} mm
                  <br />
                  {pendingDeleteRangeId === range.dimension_range_id ? (
                    <>
                      <button type="button" onClick={() => handleDeleteRange(range.dimension_range_id)}>
                        Yes
                      </button>
                      <button type="button" onClick={() => setPendingDeleteRangeId(null)}>
                        No
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setPendingDeleteRangeId(range.dimension_range_id)}
                    >
                      Delete
                    </button>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr key={group.tolerance_group_id}>
                <th>
                  {group.name}
                  <br />
                  {pendingDeleteGroupId === group.tolerance_group_id ? (
                    <>
                      <button type="button" onClick={() => handleDeleteGroup(group.tolerance_group_id)}>
                        Yes
                      </button>
                      <button type="button" onClick={() => setPendingDeleteGroupId(null)}>
                        No
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setPendingDeleteGroupId(group.tolerance_group_id)}
                    >
                      Delete
                    </button>
                  )}
                </th>
                {ranges.map((range) => (
                  <td key={range.dimension_range_id}>
                    <CellInputs
                      cell={cells[cellKey(group.tolerance_group_id, range.dimension_range_id)]}
                      onSave={(toolValue, nonToolValue) =>
                        handleSaveCell(
                          group.tolerance_group_id,
                          range.dimension_range_id,
                          toolValue,
                          nonToolValue,
                        )
                      }
                    />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h3>Add a tolerance group (row)</h3>
      <form onSubmit={handleAddGroup} className="inline-form">
        <label>
          Group name{' '}
          <input
            placeholder="Group name (e.g. TG1)"
            value={newGroupName}
            onChange={(e) => setNewGroupName(e.target.value)}
            required
          />
        </label>
        <button type="submit">Add group</button>
      </form>

      <h3>Add a dimension range (column)</h3>
      <form onSubmit={handleAddRange} className="inline-form">
        <label>
          Min (mm){' '}
          <input
            type="number"
            step="0.1"
            placeholder="Min"
            value={newRangeMin}
            onChange={(e) => setNewRangeMin(e.target.value)}
            required
          />
        </label>
        <label>
          Max (mm){' '}
          <input
            type="number"
            step="0.1"
            placeholder="Max"
            value={newRangeMax}
            onChange={(e) => setNewRangeMax(e.target.value)}
            required
          />
        </label>
        <button type="submit">Add range</button>
      </form>
    </div>
  )
}

export default ToleranceMatrixPage
