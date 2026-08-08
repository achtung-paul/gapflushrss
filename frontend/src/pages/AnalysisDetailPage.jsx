import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createFlushEntry,
  createGapEntry,
  getAnalysis,
  updateFlushEntry,
  updateGapEntry,
} from '../api/client.js'
import AnalysisImageGallery from '../components/AnalysisImageGallery.jsx'
import AngledInterfaceSection from '../components/AngledInterfaceSection.jsx'
import NumberInput from '../components/NumberInput.jsx'
import RichTextEditor from '../components/RichTextEditor.jsx'
import ToleranceChainSection from '../components/ToleranceChainSection.jsx'

// Shows an existing Gap or Flush entry (with an Edit button to change its
// direction/nominal/limits), or a form to create one if it's not
// attached yet -- an Analysis can be a placeholder with neither (see the
// brief), so both start out missing. Create and edit share the same
// form; which callback Save/Add invokes depends on whether an entry
// already existed when the form opened.
function EntrySection({ projectId, title, entry, onCreate, onUpdate, onEntryChanged }) {
  const [editing, setEditing] = useState(false)
  const [direction, setDirection] = useState('')
  const [nominalValue, setNominalValue] = useState('')
  const [upperLimit, setUpperLimit] = useState('')
  const [lowerLimit, setLowerLimit] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState(null)

  // e.g. "GAP-X" once a direction is set, or just "GAP" until it is --
  // direction lives on the entry (see api/analyses.py), not the analysis,
  // since Gap and Flush can be measured along different axes.
  const heading = title.toUpperCase() + (entry?.direction ? `-${entry.direction}` : '')

  function startEditing() {
    setDirection(entry?.direction ?? '')
    setNominalValue(entry ? String(entry.nominal_value) : '')
    setUpperLimit(entry ? String(entry.upper_limit) : '')
    setLowerLimit(entry ? String(entry.lower_limit) : '')
    setNotes(entry?.notes ?? '')
    setError(null)
    setEditing(true)
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    const body = {
      nominal_value: Number(nominalValue),
      upper_limit: Number(upperLimit),
      lower_limit: Number(lowerLimit),
      direction: direction || null,
      notes,
    }
    try {
      await (entry ? onUpdate(body) : onCreate(body))
      setEditing(false)
    } catch (err) {
      setError(err.message)
    }
  }

  if (entry && !editing) {
    // entry_code from the backend never includes direction (see
    // api/analyses.py's _entry_out) -- append it here, same as the
    // heading above, so e.g. "IP-001-GAP" becomes "IP-001-GAP-X" once a
    // direction is set.
    const displayCode = entry.entry_code + (entry.direction ? `-${entry.direction}` : '')
    return (
      <div>
        <h3>{heading}</h3>
        <p>
          {displayCode}: nominal {entry.nominal_value} mm, band {entry.nominal_value - entry.lower_limit} mm
          {' to '}
          {entry.nominal_value + entry.upper_limit} mm (+{entry.upper_limit} mm / -{entry.lower_limit} mm){' '}
          <button type="button" onClick={startEditing}>
            Edit
          </button>
        </p>
        <p className="form-hint">
          Created by {entry.created_by_name} &middot; Last modified by {entry.updated_by_name}
        </p>
        {entry.notes && (
          // Safe to render as markup only because the backend sanitises
          // it on write (core/html_sanitize.py) -- never render a value
          // here that hasn't been through that.
          <div className="entry-notes" dangerouslySetInnerHTML={{ __html: entry.notes }} />
        )}
        {entry.direction === 'OTHER' ? (
          <AngledInterfaceSection
            projectId={projectId}
            entryId={entry.entry_id}
            interfaceAngle={entry.interface_angle}
            calculationMethod={entry.calculation_method}
            onEntryChanged={onEntryChanged}
          />
        ) : (
          <ToleranceChainSection
            projectId={projectId}
            entryId={entry.entry_id}
            nominal={entry.nominal_value}
            upperLimit={entry.upper_limit}
            lowerLimit={entry.lower_limit}
          />
        )}
      </div>
    )
  }

  return (
    <div>
      <h3>{heading}</h3>
      {!entry && <p>Not attached yet.</p>}
      {/* entry-form adds wrapping to .inline-form's single row -- the
          notes editor needs a line of its own, and .inline-form is used
          by every other form in the app so it can't wrap globally. */}
      <form onSubmit={handleSubmit} className="inline-form entry-form">
        <label>
          Direction{' '}
          <select value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="">Direction...</option>
            <option value="X">X</option>
            <option value="Y">Y</option>
            <option value="Z">Z</option>
            <option value="OTHER">Other</option>
          </select>
        </label>
        <label>
          Nominal (mm){' '}
          <NumberInput
            placeholder="Nominal"
            value={nominalValue}
            onChange={setNominalValue}
            required
          />
        </label>
        <label>
          Upper limit + (mm){' '}
          <NumberInput
            min="0"
            placeholder="Upper limit (+)"
            value={upperLimit}
            onChange={setUpperLimit}
            required
          />
        </label>
        <label>
          Lower limit - (mm){' '}
          <NumberInput
            min="0"
            placeholder="Lower limit (-)"
            value={lowerLimit}
            onChange={setLowerLimit}
            required
          />
        </label>
        {/* Outside the inline row: the editor is far taller than the
            numeric inputs and would wreck the single-line layout. Saved
            by the same Save button, through the same endpoint. */}
        <div className="entry-notes-field">
          <label>Notes</label>
          <RichTextEditor value={notes} onChange={setNotes} />
        </div>
        <button type="submit">{entry ? 'Save' : `Add ${title}`}</button>
        {entry && (
          <button type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        )}
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

function AnalysisDetailPage() {
  const { projectId, analysisId } = useParams()
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    getAnalysis(projectId, analysisId).then(setAnalysis).catch((err) => setError(err.message))
  }

  useEffect(refresh, [projectId, analysisId])

  if (error) {
    return <p className="form-error">{error}</p>
  }
  if (!analysis) {
    return <p>Loading...</p>
  }

  return (
    <div>
      <h2>Analysis Page: {analysis.analysis_code}</h2>
      <EntrySection
        projectId={projectId}
        title="Gap"
        entry={analysis.gap}
        onCreate={async (body) => {
          await createGapEntry(projectId, analysisId, body)
          refresh()
        }}
        onUpdate={async (body) => {
          await updateGapEntry(projectId, analysisId, body)
          refresh()
        }}
        onEntryChanged={refresh}
      />
      <EntrySection
        projectId={projectId}
        title="Flush"
        entry={analysis.flush}
        onCreate={async (body) => {
          await createFlushEntry(projectId, analysisId, body)
          refresh()
        }}
        onUpdate={async (body) => {
          await updateFlushEntry(projectId, analysisId, body)
          refresh()
        }}
        onEntryChanged={refresh}
      />
      <AnalysisImageGallery projectId={projectId} analysisId={analysisId} />
    </div>
  )
}

export default AnalysisDetailPage
