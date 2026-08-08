import { useCallback, useEffect, useRef, useState } from 'react'
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
import NumberInput from '../components/NumberInput.jsx'

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
        <NumberInput
          placeholder="T"
          title="Tool-specific"
          value={toolValue}
          onChange={setToolValue}
          onBlur={handleBlur}
        />
      </label>
      <label title="Non-tool-specific (mm)">
        NT{' '}
        <NumberInput
          placeholder="NT"
          title="Non-tool-specific"
          value={nonToolValue}
          onChange={setNonToolValue}
          onBlur={handleBlur}
        />
      </label>
    </div>
  )
}

// The admin-editable tolerance matrix for one process type -- rows are
// user-defined tolerance groups (e.g. "TG1"), columns are user-defined
// dimension ranges (e.g. "1 to 3" mm), each cell an optional
// tool-specific/non-tool-specific +/- pair. Matches a typical industrial
// tolerance standard's "Limit dimensions" table shape, without any
// values pre-filled in.
function ToleranceMatrixPage() {
  const { processTypeId } = useParams()
  const [groups, setGroups] = useState([])
  const [ranges, setRanges] = useState([])
  const [cells, setCells] = useState({})
  const [error, setError] = useState(null)
  const scrollRef = useRef(null)

  // A wide matrix (many range columns) scrolls inside .tolerance-matrix-
  // scroll rather than widening the page -- but a plain vertical mouse
  // wheel does nothing to a horizontal-only overflow container by
  // itself (confirmed: deltaY never touches scrollLeft), so without this
  // the only way to reach the far columns is dragging the native
  // scrollbar thumb exactly, which is easy to miss entirely. This
  // translates an ordinary wheel scroll into horizontal movement while
  // the pointer is over the table, matching how this app hand-rolls
  // controls elsewhere (e.g. NumberInput's steppers) rather than relying
  // on a browser/OS affordance a user might not discover.
  //
  // A plain JSX onWheel handler can't do this: React attaches wheel
  // listeners as passive by default, so preventDefault() inside one is
  // silently ignored (with a console warning) and the page would still
  // scroll vertically underneath. A real, non-passive listener is the
  // only way to actually take over the event.
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    function handleWheel(event) {
      // Only take over when there's actually somewhere to scroll --
      // otherwise a normal page scroll over a matrix that happens to fit
      // would get swallowed for no reason.
      if (el.scrollWidth <= el.clientWidth) return
      event.preventDefault()
      el.scrollLeft += event.deltaY
    }
    el.addEventListener('wheel', handleWheel, { passive: false })
    return () => el.removeEventListener('wheel', handleWheel)
  }, [])

  function scrollMatrix(direction) {
    // Instant, not smooth -- smooth scrolling is driven by requestAnimationFrame
    // internally, which some browser/OS/accessibility configurations (e.g.
    // prefers-reduced-motion, or a backgrounded tab) can throttle or skip
    // entirely, silently leaving the button looking like it did nothing.
    // An instant jump has no such dependency -- it just happens.
    const el = scrollRef.current
    if (!el) return
    el.scrollLeft += direction * el.clientWidth * 0.8
  }

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

      <div className="tolerance-matrix-scroll-controls">
        <button type="button" onClick={() => scrollMatrix(-1)}>
          &larr; Scroll
        </button>
        <button type="button" onClick={() => scrollMatrix(1)}>
          Scroll &rarr;
        </button>
        <span className="form-hint">Or point at the table and use the mouse wheel.</span>
      </div>
      <div className="tolerance-matrix-scroll" ref={scrollRef}>
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
          <NumberInput placeholder="Min" value={newRangeMin} onChange={setNewRangeMin} required />
        </label>
        <label>
          Max (mm){' '}
          <NumberInput placeholder="Max" value={newRangeMax} onChange={setNewRangeMax} required />
        </label>
        <button type="submit">Add range</button>
      </form>
    </div>
  )
}

export default ToleranceMatrixPage
