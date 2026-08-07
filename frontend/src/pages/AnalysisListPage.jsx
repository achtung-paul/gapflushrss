import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
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
  updateFlushEntry,
  updateGapEntry,
  uploadImage,
} from '../api/client.js'
import ImageAnnotator from '../components/ImageAnnotator.jsx'

const DIRECTION_LABELS = { X: 'X', Y: 'Y', Z: 'Z', OTHER: 'Other' }
const RAG_CLASS = { green: 'rag-green', amber: 'rag-amber', red: 'rag-red' }
const SIGMA_LEVELS = [3, 4, 5]

// Renders the Max/Min band (nominal + upper limit, over nominal - lower
// limit) as two stacked lines, or '--' if any of the three inputs isn't
// a usable number yet -- shared between the read-only row and the live
// preview shown while editing.
function formatBand(nominal, upperLimit, lowerLimit) {
  const n = Number(nominal)
  const u = Number(upperLimit)
  const l = Number(lowerLimit)
  if (nominal === '' || upperLimit === '' || lowerLimit === '' || [n, u, l].some(Number.isNaN)) {
    return '--'
  }
  return (
    <>
      {(n + u).toFixed(2)}
      <br />
      {(n - l).toFixed(2)}
    </>
  )
}

// One row of the analysis table -- either a Gap or a Flush entry for one
// Analysis. `entry` is null for a placeholder row (that Gap/Flush isn't
// attached to this analysis yet), which renders '--' throughout with
// just an Add button. Direction lives on the entry itself, not the
// Analysis, since Gap and Flush can be measured along different axes.
function EntryTableRow({ analysisId, analysisCode, entryType, entry, onChanged }) {
  const [editing, setEditing] = useState(false)
  const [pendingDelete, setPendingDelete] = useState(false)
  const [direction, setDirection] = useState('')
  const [nominalValue, setNominalValue] = useState('')
  const [upperLimit, setUpperLimit] = useState('')
  const [lowerLimit, setLowerLimit] = useState('')
  const [simulation, setSimulation] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!entry) {
      setSimulation(null)
      return
    }
    getSimulation(entry.entry_id).then(setSimulation).catch((err) => setError(err.message))
  }, [entry?.entry_id])

  function startEditing() {
    setDirection(entry?.direction ?? '')
    setNominalValue(entry ? String(entry.nominal_value) : '')
    setUpperLimit(entry ? String(entry.upper_limit) : '')
    setLowerLimit(entry ? String(entry.lower_limit) : '')
    setError(null)
    setEditing(true)
  }

  async function handleSave() {
    setError(null)
    const body = {
      nominal_value: Number(nominalValue),
      upper_limit: Number(upperLimit),
      lower_limit: Number(lowerLimit),
      direction: direction || null,
    }
    try {
      if (entry) {
        await (entryType === 'GAP' ? updateGapEntry(analysisId, body) : updateFlushEntry(analysisId, body))
      } else {
        await (entryType === 'GAP' ? createGapEntry(analysisId, body) : createFlushEntry(analysisId, body))
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
      await deleteEntry(entry.entry_id)
      setPendingDelete(false)
      onChanged()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <tr>
      <td>
        <Link to={`/analyses/${analysisId}`}>{analysisCode}</Link>
      </td>
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
          <input
            type="number"
            step="any"
            value={nominalValue}
            onChange={(e) => setNominalValue(e.target.value)}
            required
          />
        ) : entry ? (
          entry.nominal_value
        ) : (
          '--'
        )}
      </td>
      <td>{editing ? formatBand(nominalValue, upperLimit, lowerLimit) : entry ? formatBand(entry.nominal_value, entry.upper_limit, entry.lower_limit) : '--'}</td>
      <td>
        {editing ? (
          <>
            <input
              type="number"
              step="any"
              min="0"
              placeholder="+"
              value={upperLimit}
              onChange={(e) => setUpperLimit(e.target.value)}
              required
            />
            <br />
            <input
              type="number"
              step="any"
              min="0"
              placeholder="-"
              value={lowerLimit}
              onChange={(e) => setLowerLimit(e.target.value)}
              required
            />
          </>
        ) : entry ? (
          <>
            +{entry.upper_limit}
            <br />-{entry.lower_limit}
          </>
        ) : (
          '--'
        )}
      </td>
      {SIGMA_LEVELS.map((sigmaLevel) => {
        const result = simulation?.results.find((r) => r.sigma_level === sigmaLevel)
        return (
          <td key={sigmaLevel} className={result ? RAG_CLASS[result.rag] : undefined}>
            {result ? `±${result.spread.toFixed(2)}` : ''}
          </td>
        )
      })}
      <td>
        {editing ? (
          <button type="button" onClick={handleSave}>
            Save
          </button>
        ) : (
          <button type="button" onClick={startEditing}>
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
            <button type="button" onClick={() => setPendingDelete(true)}>
              Delete
            </button>
          ))
        )}
      </td>
    </tr>
  )
}

// The commodity's shared assembly image, annotated with numbered
// markers -- each marker IS an Analysis (dropping one creates the next
// one in sequence; deleting one deletes that Analysis and everything
// under it). See api/images.py's create_marker/delete_marker.
function AnalysisListPage() {
  const { commodityId } = useParams()
  const [analyses, setAnalyses] = useState([])
  const [images, setImages] = useState([])
  const [selectedImageId, setSelectedImageId] = useState(null)
  const [markers, setMarkers] = useState([])
  const [pendingDeleteImageId, setPendingDeleteImageId] = useState(null)
  const [error, setError] = useState(null)

  function refreshAnalyses() {
    listAnalyses(commodityId).then(setAnalyses).catch((err) => setError(err.message))
  }

  function refreshImages() {
    listImages(commodityId).then(setImages).catch((err) => setError(err.message))
  }

  useEffect(refreshAnalyses, [commodityId])
  useEffect(refreshImages, [commodityId])

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
    listMarkers(selectedImageId).then(setMarkers).catch((err) => setError(err.message))
  }

  useEffect(refreshMarkers, [selectedImageId])

  async function handleUpload(event) {
    event.preventDefault()
    setError(null)
    const file = event.target.elements.file.files[0]
    if (!file) return
    try {
      await uploadImage(commodityId, file)
      event.target.reset()
      refreshImages()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteImage(imageId) {
    setError(null)
    try {
      await deleteImage(imageId)
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
        await createMarker(selectedImageId, points)
        refreshMarkers()
        refreshAnalyses()
      } catch (err) {
        setError(err.message)
      }
    },
    [selectedImageId],
  )

  const handleDeleteMarker = useCallback(
    async (markerId) => {
      try {
        await deleteMarker(markerId)
        refreshMarkers()
        refreshAnalyses()
      } catch (err) {
        setError(err.message)
      }
    },
    [selectedImageId],
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
      <h2>Analyses</h2>
      {error && <p className="form-error">{error}</p>}

      <h3>Images</h3>
      <ul>
        {images.map((image) => (
          <li key={image.image_id}>
            <button type="button" onClick={() => setSelectedImageId(image.image_id)}>
              {image.original_filename}
            </button>{' '}
            {pendingDeleteImageId === image.image_id ? (
              <>
                <span>Delete this image?</span>{' '}
                <button type="button" onClick={() => handleDeleteImage(image.image_id)}>
                  Yes
                </button>{' '}
                <button type="button" onClick={() => setPendingDeleteImageId(null)}>
                  No
                </button>
              </>
            ) : (
              <button type="button" onClick={() => setPendingDeleteImageId(image.image_id)}>
                Delete
              </button>
            )}
          </li>
        ))}
      </ul>

      <form onSubmit={handleUpload} className="inline-form">
        <input type="file" name="file" accept="image/*" required />
        <button type="submit">Upload image</button>
      </form>

      {selectedImageId !== null && (
        <div>
          <p>
            Click the image to place points along a line, double-click to finish -- this drops a
            numbered marker at the last point (with the line left in place) and creates the next
            analysis in sequence. Click a marker to open its analysis, or use its delete button to
            remove the marker, its line, and its analysis.
          </p>
          <ImageAnnotator
            imageUrl={imageFileUrl(selectedImageId)}
            markers={markers}
            onCreateMarker={handleCreateMarker}
            onDeleteMarker={handleDeleteMarker}
          />
        </div>
      )}

      <h3>All analyses</h3>
      <div className="analysis-table-scroll">
        <table className="analysis-table">
          <thead>
            <tr>
              <th>Analysis</th>
              <th>Gap/Flush</th>
              <th>Direction</th>
              <th>Nominal</th>
              <th>Max/Min</th>
              <th>Tolerance</th>
              <th>3σ</th>
              <th>4σ</th>
              <th>5σ</th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ analysis, entryType, entry }) => (
              <EntryTableRow
                key={`${analysis.analysis_id}-${entryType}`}
                analysisId={analysis.analysis_id}
                analysisCode={analysis.analysis_code}
                entryType={entryType}
                entry={entry}
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
