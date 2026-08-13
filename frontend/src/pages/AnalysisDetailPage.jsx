import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  createFlushEntry,
  createGapEntry,
  entryExportUrl,
  getAnalysis,
  updateAnalysisDescription,
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
function EntrySection({ projectId, analysisId, title, entry, onCreate, onUpdate, onEntryChanged, showOwnHeading }) {
  const [editing, setEditing] = useState(false)
  const [direction, setDirection] = useState('')
  const [nominalValue, setNominalValue] = useState('')
  // Two numbers whose meaning depends on limitMode: tolerance magnitudes
  // (offsets from nominal, always >= 0 -- the original convention) or
  // the absolute signed band edges directly (for compressible-material
  // targets where the whole band can be negative). Storage only ever
  // has one representation (magnitudes); see
  // schemas/analysis_entry.py's resolve_limits, which converts absolute
  // bounds server-side. Same toggle as AnalysisListPage.jsx's inline row
  // editor -- kept in sync by hand since the two forms don't share state.
  const [limitMode, setLimitMode] = useState('magnitude')
  const [upperLimit, setUpperLimit] = useState('')
  const [lowerLimit, setLowerLimit] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState(null)
  // Notes get their own small edit toggle, separate from `editing` above
  // -- they're shown under the chart, not inside the direction/nominal/
  // limits form, so editing one shouldn't require opening the other.
  const [editingNotes, setEditingNotes] = useState(false)
  const [notesInput, setNotesInput] = useState('')
  const [notesError, setNotesError] = useState(null)

  // e.g. "GAP-X" once a direction is set, or just "GAP" until it is --
  // direction lives on the entry (see api/analyses.py), not the analysis,
  // since Gap and Flush can be measured along different axes.
  const heading = title.toUpperCase() + (entry?.direction ? `-${entry.direction}` : '')

  function startEditing() {
    setDirection(entry?.direction ?? '')
    setNominalValue(entry ? String(entry.nominal_value) : '')
    setLimitMode('magnitude')
    setUpperLimit(entry ? String(entry.upper_limit) : '')
    setLowerLimit(entry ? String(entry.lower_limit) : '')
    setNotes(entry?.notes ?? '')
    setError(null)
    setEditing(true)
  }

  // Re-expresses whatever's currently typed in the *other* mode's terms,
  // using the nominal value on screen right now -- so toggling never
  // silently discards a number already entered. Same logic as
  // AnalysisListPage.jsx's inline row editor.
  function handleLimitModeChange(nextMode) {
    if (nextMode === limitMode) return
    const n = Number(nominalValue)
    const a = Number(upperLimit)
    const b = Number(lowerLimit)
    if (!Number.isNaN(n) && !Number.isNaN(a) && !Number.isNaN(b)) {
      if (nextMode === 'absolute') {
        setUpperLimit(String(n + a))
        setLowerLimit(String(n - b))
      } else {
        setUpperLimit(String(a - n))
        setLowerLimit(String(n - b))
      }
    }
    setLimitMode(nextMode)
  }

  function startEditingNotes() {
    setNotesInput(entry?.notes ?? '')
    setNotesError(null)
    setEditingNotes(true)
  }

  // Reuses the same full-replace onUpdate as the direction/nominal/limits
  // form (there's no narrower "just update notes" endpoint -- see
  // AnalysisEntryCreate), carrying the entry's other fields forward
  // unchanged so this really only ever touches notes.
  async function handleSaveNotes() {
    setNotesError(null)
    try {
      await onUpdate({
        nominal_value: entry.nominal_value,
        upper_limit: entry.upper_limit,
        lower_limit: entry.lower_limit,
        direction: entry.direction,
        notes: notesInput,
      })
      setEditingNotes(false)
    } catch (err) {
      setNotesError(err.message)
    }
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    const body = {
      nominal_value: Number(nominalValue),
      direction: direction || null,
      notes,
      ...(limitMode === 'absolute'
        ? { upper_bound: Number(upperLimit), lower_bound: Number(lowerLimit) }
        : { upper_limit: Number(upperLimit), lower_limit: Number(lowerLimit) }),
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
    // api/analyses.py's _entry_out) -- append it here, so e.g.
    // "IP-001-GAP" becomes "IP-001-GAP-X" once a direction is set.
    const displayCode = entry.entry_code + (entry.direction ? `-${entry.direction}` : '')
    return (
      <div>
        {/* Whichever entry the page heading above already identifies
            (see AnalysisDetailPage's primaryEntry) skips repeating its
            own code -- and its own Print report button, which lives on
            the page heading instead (see AnalysisDetailPage) -- here;
            the other entry, if any, still needs both. */}
        {showOwnHeading && (
          <div className="section-header-row">
            <h3>{displayCode}</h3>
            <div className="section-header-actions">
              <Link
                className="btn-primary"
                to={`/projects/${projectId}/analyses/${analysisId}/report/${title.toLowerCase()}`}
                target="_blank"
              >
                Print report
              </Link>
              <a className="btn-primary" href={entryExportUrl(projectId, entry.entry_id)}>
                Export to Excel
              </a>
            </div>
          </div>
        )}
        <p className="entry-band">
          {/* toFixed(3) matches the Numeric(10,3) column these come from --
              plain subtraction/addition on the floats the API returns can
              produce binary floating-point noise (e.g. 0.10000000000000009)
              that was never actually stored. */}
          Nominal {entry.nominal_value} mm, Band{' '}
          {(entry.nominal_value - entry.lower_limit).toFixed(3)} mm{' '}
          to {(entry.nominal_value + entry.upper_limit).toFixed(3)} mm (+{entry.upper_limit} mm{' '}
          / -{entry.lower_limit} mm){' '}
          <button type="button" className="link-button" onClick={startEditing}>
            Edit
          </button>
        </p>
        <p className="form-hint">
          Created by {entry.created_by_name} &middot; Last modified by {entry.updated_by_name}
        </p>
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

        <div className="section-divider" />

        <h4>Notes</h4>
        {editingNotes ? (
          <div>
            <RichTextEditor value={notesInput} onChange={setNotesInput} />
            <button type="button" onClick={handleSaveNotes}>
              Save
            </button>{' '}
            <button type="button" onClick={() => setEditingNotes(false)}>
              Cancel
            </button>
            {notesError && <p className="form-error">{notesError}</p>}
          </div>
        ) : (
          <div>
            {entry.notes && (
              // Safe to render as markup only because the backend
              // sanitises it on write (core/html_sanitize.py) -- never
              // render a value here that hasn't been through that.
              <div className="entry-notes" dangerouslySetInnerHTML={{ __html: entry.notes }} />
            )}
            <button type="button" className="link-button" onClick={startEditingNotes}>
              {entry.notes ? 'Edit' : 'Add notes'}
            </button>
          </div>
        )}

        <div className="section-divider" />

        {/* This entry's own photo gallery -- Gap and Flush each get a
            separate one (see AnalysisImageGallery.jsx), not one shared
            gallery duplicated under both. */}
        <AnalysisImageGallery projectId={projectId} entryId={entry.entry_id} />
      </div>
    )
  }

  return (
    <div>
      {showOwnHeading && <h3>{heading}</h3>}
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
          <input
            type="checkbox"
            checked={limitMode === 'absolute'}
            onChange={(e) => handleLimitModeChange(e.target.checked ? 'absolute' : 'magnitude')}
          />{' '}
          Absolute limits
        </label>
        <label>
          {limitMode === 'magnitude' ? 'Upper limit + (mm)' : 'Upper limit (mm)'}{' '}
          {/* Compressible-material targets can have a negative whole
              band (nominal included) -- min="0" only makes sense for
              the tolerance-magnitude convention, not for entering the
              signed band edges directly. */}
          <NumberInput
            min={limitMode === 'magnitude' ? '0' : undefined}
            placeholder={limitMode === 'magnitude' ? 'Upper limit (+)' : 'Upper limit'}
            value={upperLimit}
            onChange={setUpperLimit}
            required
          />
        </label>
        <label>
          {limitMode === 'magnitude' ? 'Lower limit - (mm)' : 'Lower limit (mm)'}{' '}
          <NumberInput
            min={limitMode === 'magnitude' ? '0' : undefined}
            placeholder={limitMode === 'magnitude' ? 'Lower limit (-)' : 'Lower limit'}
            value={lowerLimit}
            onChange={setLowerLimit}
            required
          />
        </label>
        {/* Only for the create flow -- an existing entry's notes have
            their own editor under the graph below (see handleSaveNotes),
            so this field would just be a confusing second place to edit
            the same thing. Outside the inline row: the editor is far
            taller than the numeric inputs and would wreck the
            single-line layout. */}
        {!entry && (
          <div className="entry-notes-field">
            <label>Notes</label>
            <RichTextEditor value={notes} onChange={setNotes} />
          </div>
        )}
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
  const [editingDescription, setEditingDescription] = useState(false)
  const [descriptionInput, setDescriptionInput] = useState('')
  const [descriptionError, setDescriptionError] = useState(null)

  function refresh() {
    getAnalysis(projectId, analysisId).then(setAnalysis).catch((err) => setError(err.message))
  }

  useEffect(refresh, [projectId, analysisId])

  function startEditingDescription() {
    setDescriptionInput(analysis.description)
    setDescriptionError(null)
    setEditingDescription(true)
  }

  async function handleSaveDescription() {
    setDescriptionError(null)
    try {
      await updateAnalysisDescription(projectId, analysisId, descriptionInput)
      setEditingDescription(false)
      refresh()
    } catch (err) {
      setDescriptionError(err.message)
    }
  }

  if (error) {
    return <p className="form-error">{error}</p>
  }
  if (!analysis) {
    return <p>Loading...</p>
  }

  // Whichever of Gap/Flush exists takes over the page heading (e.g.
  // "DR-001-GAP-X" instead of the bare "DR-001") so that code doesn't
  // also need its own separate heading line lower down -- see
  // EntrySection's showOwnHeading. Gap wins if an analysis somehow has
  // both; a placeholder analysis with neither falls back to the bare code.
  const primaryEntry = analysis.gap ?? analysis.flush
  const primaryEntryType = analysis.gap ? 'gap' : analysis.flush ? 'flush' : null
  const primaryCode = primaryEntry
    ? primaryEntry.entry_code + (primaryEntry.direction ? `-${primaryEntry.direction}` : '')
    : analysis.analysis_code

  return (
    <div>
      <p>
        <Link to={`/projects/${projectId}/commodities/${analysis.commodity_id}/analyses`}>
          &larr; Analyses
        </Link>
      </p>
      <div className="section-header-row">
        <h2>
          {primaryCode}
          {editingDescription ? (
            <>
              {' - '}
              <input
                type="text"
                value={descriptionInput}
                onChange={(e) => setDescriptionInput(e.target.value)}
                placeholder="e.g. IP to Console"
                autoFocus
              />{' '}
              <button type="button" onClick={handleSaveDescription}>
                Save
              </button>{' '}
              <button type="button" onClick={() => setEditingDescription(false)}>
                Cancel
              </button>
            </>
          ) : (
            <>
              {analysis.description && ` - ${analysis.description}`}{' '}
              <button type="button" className="link-button" onClick={startEditingDescription}>
                {analysis.description ? 'Edit' : 'Add description'}
              </button>
            </>
          )}
        </h2>
        {primaryEntryType && (
          <div className="section-header-actions">
            <Link
              className="btn-primary"
              to={`/projects/${projectId}/analyses/${analysisId}/report/${primaryEntryType}`}
              target="_blank"
            >
              Print report
            </Link>
            <a className="btn-primary" href={entryExportUrl(projectId, primaryEntry.entry_id)}>
              Export to Excel
            </a>
          </div>
        )}
      </div>
      {descriptionError && <p className="form-error">{descriptionError}</p>}
      <EntrySection
        projectId={projectId}
        analysisId={analysisId}
        title="Gap"
        entry={analysis.gap}
        showOwnHeading={analysis.gap ? analysis.gap !== primaryEntry : true}
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

      <div className="section-divider" />

      <EntrySection
        projectId={projectId}
        analysisId={analysisId}
        title="Flush"
        entry={analysis.flush}
        showOwnHeading={analysis.flush ? analysis.flush !== primaryEntry : true}
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
    </div>
  )
}

export default AnalysisDetailPage
