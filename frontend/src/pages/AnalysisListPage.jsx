import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  commodityExportUrl,
  createFlushEntry,
  createGapEntry,
  createMarker,
  deleteEntry,
  deleteImage,
  deleteMarker,
  getSimulation,
  imageFileUrl,
  listAnalyses,
  listImages,
  listMarkers,
  listStatisticalModelSettings,
  updateFlushEntry,
  updateGapEntry,
  uploadImage,
} from '../api/client.js'
import ImageAnnotator from '../components/ImageAnnotator.jsx'
import NumberInput from '../components/NumberInput.jsx'

const DIRECTION_LABELS = { X: 'X', Y: 'Y', Z: 'Z', OTHER: 'Other' }
const RAG_CLASS = {
  green: 'rag-green',
  amber: 'rag-amber',
  red: 'rag-red',
  not_evaluated: 'rag-not-evaluated',
}
// Same pass/caution/fail wording as ToleranceChainSection.jsx's sigma
// table -- this column is a quick pass/fail glance across the whole
// list, not the detail page's own numeric spread (still shown there).
const RAG_LABELS = {
  green: 'Pass',
  amber: 'Caution',
  red: 'Fail',
  not_evaluated: 'Not evaluated',
}

// Renders the Max/Min band as two stacked lines, or '--' if any of the
// three inputs isn't a usable number yet -- shared between the read-only
// row (always nominal +/- magnitude, since that's the one stored
// representation -- see schemas/analysis_entry.py) and the live preview
// shown while editing, which also has to handle limitMode === 'absolute'
// (upperLimit/lowerLimit are themselves the band edges already, not
// offsets from nominal).
function formatBand(nominal, upperLimit, lowerLimit, limitMode = 'magnitude') {
  const n = Number(nominal)
  const u = Number(upperLimit)
  const l = Number(lowerLimit)
  if (nominal === '' || upperLimit === '' || lowerLimit === '' || [n, u, l].some(Number.isNaN)) {
    return '--'
  }
  const upperBound = limitMode === 'absolute' ? u : n + u
  const lowerBound = limitMode === 'absolute' ? l : n - l
  return (
    <>
      {upperBound.toFixed(2)} mm
      <br />
      {lowerBound.toFixed(2)} mm
    </>
  )
}

// One row of the analysis table -- either a Gap or a Flush entry for one
// Analysis. `entry` is null for a placeholder row (that Gap/Flush isn't
// attached to this analysis yet), which renders '--' throughout with
// just an Add button. Direction lives on the entry itself, not the
// Analysis, since Gap and Flush can be measured along different axes.
function EntryTableRow({
  projectId,
  analysisId,
  analysisCode,
  analysisDescription,
  entryType,
  entry,
  sigmaColumns,
  onChanged,
}) {
  const [editing, setEditing] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(false)
  const [direction, setDirection] = useState('')
  const [nominalValue, setNominalValue] = useState('')
  // Two numbers whose meaning depends on limitMode: tolerance magnitudes
  // (offsets from nominal, always >= 0 -- the original convention) or
  // the absolute signed band edges directly (for compressible-material
  // targets where the whole band can be negative, e.g. -1.0 to -0.1
  // around a nominal of -0.5 -- typing that directly is the natural way
  // to think about it, versus first hand-computing magnitudes of 0.4/0.5).
  // Storage only ever has one representation (magnitudes); see
  // schemas/analysis_entry.py's resolve_limits, which converts absolute
  // bounds server-side before anything else sees them.
  const [limitMode, setLimitMode] = useState('magnitude')
  const [upperLimit, setUpperLimit] = useState('')
  const [lowerLimit, setLowerLimit] = useState('')
  const [simulation, setSimulation] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!entry) {
      setSimulation(null)
      return
    }
    getSimulation(projectId, entry.entry_id).then(setSimulation).catch((err) => setError(err.message))
  }, [projectId, entry?.entry_id])

  function startEditing() {
    setDirection(entry?.direction ?? '')
    setNominalValue(entry ? String(entry.nominal_value) : '')
    setLimitMode('magnitude')
    setUpperLimit(entry ? String(entry.upper_limit) : '')
    setLowerLimit(entry ? String(entry.lower_limit) : '')
    setError(null)
    setEditing(true)
  }

  // Re-expresses whatever's currently typed in the *other* mode's terms,
  // using the nominal value on screen right now -- so toggling never
  // silently discards a number the user already entered.
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

  async function handleSave() {
    setError(null)
    const body = {
      nominal_value: Number(nominalValue),
      direction: direction || null,
      ...(limitMode === 'absolute'
        ? { upper_bound: Number(upperLimit), lower_bound: Number(lowerLimit) }
        : { upper_limit: Number(upperLimit), lower_limit: Number(lowerLimit) }),
    }
    try {
      if (entry) {
        await (entryType === 'GAP'
          ? updateGapEntry(projectId, analysisId, body)
          : updateFlushEntry(projectId, analysisId, body))
      } else {
        await (entryType === 'GAP'
          ? createGapEntry(projectId, analysisId, body)
          : createFlushEntry(projectId, analysisId, body))
      }
      setEditing(false)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete() {
    setError(null)
    try {
      await deleteEntry(projectId, entry.entry_id)
      setPendingDelete(false)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <tr>
      <td>
        <Link to={`/projects/${projectId}/analyses/${analysisId}`}>{analysisCode}</Link>
      </td>
      <td>{analysisDescription || '--'}</td>
      <td>{entryType === 'GAP' ? 'Gap' : 'Flush'}</td>
      <td>
        {editing ? (
          <select value={direction} onChange={(e) => setDirection(e.target.value)}>
            <option value="">--</option>
            <option value="X">X</option>
            <option value="Y">Y</option>
            <option value="Z">Z</option>
            <option value="OTHER">Other</option>
          </select>
        ) : (
          (entry?.direction && DIRECTION_LABELS[entry.direction]) || '--'
        )}
      </td>
      <td>
        {editing ? (
          <NumberInput value={nominalValue} onChange={setNominalValue} required />
        ) : entry ? (
          `${entry.nominal_value} mm`
        ) : (
          '--'
        )}
      </td>
      <td>
        {editing
          ? formatBand(nominalValue, upperLimit, lowerLimit, limitMode)
          : entry
            ? formatBand(entry.nominal_value, entry.upper_limit, entry.lower_limit)
            : '--'}
      </td>
      <td>
        {editing ? (
          <>
            <label>
              <input
                type="checkbox"
                checked={limitMode === 'absolute'}
                onChange={(e) => handleLimitModeChange(e.target.checked ? 'absolute' : 'magnitude')}
              />{' '}
              Absolute limits
            </label>
            {/* Compressible-material targets can have a negative whole
                band (nominal included) -- min="0" only makes sense for
                the original tolerance-magnitude convention, not for
                entering the signed band edges directly. */}
            <NumberInput
              min={limitMode === 'magnitude' ? '0' : undefined}
              placeholder={limitMode === 'magnitude' ? '+' : 'Upper limit'}
              value={upperLimit}
              onChange={setUpperLimit}
              required
            />
            <br />
            <NumberInput
              min={limitMode === 'magnitude' ? '0' : undefined}
              placeholder={limitMode === 'magnitude' ? '-' : 'Lower limit'}
              value={lowerLimit}
              onChange={setLowerLimit}
              required
            />
          </>
        ) : entry ? (
          <>
            +{entry.upper_limit} mm
            <br />-{entry.lower_limit} mm
          </>
        ) : (
          '--'
        )}
      </td>
      {sigmaColumns.map((column) => {
        const result = simulation?.results.find((r) => r.sigma_level === column.sigma_level)
        return (
          <td key={column.sigma_level}>
            {result && (
              <span
                className={`rag-badge ${result.info_only ? 'rag-info' : RAG_CLASS[result.rag] ?? ''}`}
                title={`±${result.spread.toFixed(2)} mm`}
              >
                {result.info_only ? 'Info' : RAG_LABELS[result.rag] ?? result.rag}
              </span>
            )}
          </td>
        )
      })}
      <td>
        {editing ? (
          <button type="button" onClick={handleSave}>
            Save
          </button>
        ) : (
          <button type="button" className="link-button" onClick={startEditing}>
            {entry ? 'Edit' : 'Add'}
          </button>
        )}
        {error && <div className="form-error">{error}</div>}
      </td>
      <td>
        {editing ? (
          <button type="button" onClick={() => setEditing(false)}>
            Cancel
          </button>
        ) : (
          entry &&
          (pendingDelete ? (
            <>
              <button type="button" onClick={handleDelete}>
                Yes
              </button>{' '}
              <button type="button" onClick={() => setPendingDelete(false)}>
                No
              </button>
            </>
          ) : (
            <button type="button" className="link-button" onClick={() => setPendingDelete(true)}>
              Delete
            </button>
          ))
        )}
      </td>
      <td>{entry?.updated_by_name ?? '--'}</td>
    </tr>
  )
}

// The commodity's shared assembly image, annotated with numbered
// markers -- each marker IS an Analysis (dropping one creates the next
// one in sequence; deleting one deletes that Analysis and everything
// under it). See api/images.py's create_marker/delete_marker.
function AnalysisListPage() {
  const { projectId, commodityId } = useParams()
  const [analyses, setAnalyses] = useState([])
  const [images, setImages] = useState([])
  const [selectedImageId, setSelectedImageId] = useState(null)
  const [markers, setMarkers] = useState([])
  const [pendingDeleteImageId, setPendingDeleteImageId] = useState(null)
  const [error, setError] = useState(null)
  // Which sigma columns to render, and whether each is info-only -- this
  // client's own StatisticalModelSetting rows, not the fixed 3/4/5 every
  // client used to get (see core/simulation.py). Fetched once, since it's
  // the same for every entry on this page; each row's own getSimulation
  // call already returns exactly these levels in this order, so there's
  // nothing to keep in sync beyond fetching it once here for the header.
  const [sigmaColumns, setSigmaColumns] = useState([])

  function refreshAnalyses() {
    listAnalyses(projectId, commodityId).then(setAnalyses).catch((err) => setError(err.message))
  }

  useEffect(() => {
    listStatisticalModelSettings()
      .then((settings) => setSigmaColumns(settings.filter((s) => s.visible)))
      .catch((err) => setError(err.message))
  }, [])

  function refreshImages() {
    listImages(projectId, commodityId).then(setImages).catch((err) => setError(err.message))
  }

  useEffect(refreshAnalyses, [projectId, commodityId])
  useEffect(refreshImages, [projectId, commodityId])

  useEffect(() => {
    if (images.length > 0 && selectedImageId === null) {
      setSelectedImageId(images[0].image_id)
    }
  }, [images, selectedImageId])

  function refreshMarkers() {
    if (selectedImageId === null) {
      setMarkers([])
      return
    }
    listMarkers(projectId, selectedImageId).then(setMarkers).catch((err) => setError(err.message))
  }

  useEffect(refreshMarkers, [projectId, selectedImageId])

  async function handleUpload(event) {
    event.preventDefault()
    setError(null)
    const file = event.target.elements.file.files[0]
    if (!file) return
    try {
      await uploadImage(projectId, commodityId, file)
      event.target.reset()
      refreshImages()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteImage(imageId) {
    setError(null)
    try {
      await deleteImage(projectId, imageId)
      setPendingDeleteImageId(null)
      if (selectedImageId === imageId) {
        setSelectedImageId(null)
      }
      refreshImages()
      // The image's markers are gone, but their analyses survive as
      // placeholders (see api/images.py) -- nothing to refresh there.
    } catch (err) {
      setError(err.message)
    }
  }

  const handleCreateMarker = useCallback(
    async (points) => {
      if (selectedImageId === null) return
      try {
        await createMarker(projectId, selectedImageId, points)
        refreshMarkers()
        refreshAnalyses()
      } catch (err) {
        setError(err.message)
      }
    },
    [projectId, selectedImageId],
  )

  const handleDeleteMarker = useCallback(
    async (markerId) => {
      try {
        await deleteMarker(projectId, markerId)
        refreshMarkers()
        refreshAnalyses()
      } catch (err) {
        setError(err.message)
      }
    },
    [projectId, selectedImageId],
  )

  // One row per Gap and one per Flush for every analysis, whether or not
  // that entry has been added yet -- see EntryTableRow for the
  // placeholder ('--') rendering when entry is null.
  const rows = analyses.flatMap((analysis) => [
    { analysis, entryType: 'GAP', entry: analysis.gap },
    { analysis, entryType: 'FLUSH', entry: analysis.flush },
  ])

  return (
    <div>
      <p>
        <Link to="/projects">&larr; Projects</Link>
      </p>
      <div className="section-header-row">
        <h2>Analyses</h2>
        <div className="section-header-actions">
          <Link className="btn-primary" to={`/projects/${projectId}/commodities/${commodityId}/report`} target="_blank">
            Print report
          </Link>
          <a className="btn-primary" href={commodityExportUrl(projectId, commodityId)}>
            Export to Excel
          </a>
        </div>
      </div>
      {error && <p className="form-error">{error}</p>}

      <h3 className="section-label">Images</h3>
      {images.length === 0 ? (
        <p>No images uploaded yet.</p>
      ) : (
        <div className="analysis-gallery-grid">
          {images.map((image) => (
            <div key={image.image_id} className="analysis-gallery-thumb-wrap">
              <img
                src={imageFileUrl(projectId, image.image_id)}
                alt={image.original_filename}
                className={
                  image.image_id === selectedImageId
                    ? 'analysis-gallery-thumb image-thumb-selected'
                    : 'analysis-gallery-thumb'
                }
                onClick={() => setSelectedImageId(image.image_id)}
              />
              {pendingDeleteImageId === image.image_id ? (
                <div className="analysis-gallery-confirm">
                  <p>Delete this image?</p>
                  <div>
                    <button type="button" className="link-button" onClick={() => handleDeleteImage(image.image_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" className="link-button" onClick={() => setPendingDeleteImageId(null)}>
                      No
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="analysis-gallery-delete-btn"
                  title="Delete image"
                  onClick={() => setPendingDeleteImageId(image.image_id)}
                >
                  &times;
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="section-divider" />

      <form onSubmit={handleUpload} className="inline-form">
        <label>
          Image file{' '}
          <input type="file" name="file" accept="image/*" required />
        </label>
        <button type="submit">Upload image</button>
      </form>

      <div className="section-divider" />

      {selectedImageId !== null && (
        <div>
          <h3 className="section-label">Assembly diagram &mdash; click a marker to open its analysis</h3>
          <p>
            Click the image to place points along a line, double-click to finish -- this drops a
            numbered marker at the last point (with the line left in place) and creates the next
            analysis in sequence. Click a marker to open its analysis, or use its delete button to
            remove the marker, its line, and its analysis.
          </p>
          <ImageAnnotator
            projectId={projectId}
            imageUrl={imageFileUrl(projectId, selectedImageId)}
            markers={markers}
            onCreateMarker={handleCreateMarker}
            onDeleteMarker={handleDeleteMarker}
          />
        </div>
      )}

      <div className="section-divider" />

      <h3 className="section-label">All analyses</h3>
      <div className="analysis-table-scroll">
        <table className="analysis-table">
          <thead>
            <tr>
              <th>Analysis</th>
              <th>Description</th>
              <th>Gap/Flush</th>
              <th>Direction</th>
              <th>Nominal (mm)</th>
              <th>Max/Min (mm)</th>
              <th>Tolerance (mm)</th>
              {sigmaColumns.map((column) => (
                <th key={column.sigma_level}>{column.sigma_level}σ (mm)</th>
              ))}
              <th></th>
              <th></th>
              <th>Last modified by</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ analysis, entryType, entry }) => (
              <EntryTableRow
                key={`${analysis.analysis_id}-${entryType}`}
                projectId={projectId}
                analysisId={analysis.analysis_id}
                analysisCode={analysis.analysis_code}
                analysisDescription={analysis.description}
                entryType={entryType}
                entry={entry}
                sigmaColumns={sigmaColumns}
                onChanged={refreshAnalyses}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default AnalysisListPage
