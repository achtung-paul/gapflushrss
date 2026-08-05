import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import {
  createFlushEntry,
  createGapEntry,
  createMarker,
  deleteImage,
  deleteMarker,
  getAnalysis,
  imageFileUrl,
  listImages,
  listMarkers,
  uploadImage,
} from '../api/client.js'
import ImageAnnotator from '../components/ImageAnnotator.jsx'

// Shows an existing Gap or Flush entry, or a small form to create one if
// it's not attached yet -- an Analysis can be a placeholder with neither
// (see the brief), so both start out missing.
function EntrySection({ title, entry, onCreate }) {
  const [nominalValue, setNominalValue] = useState('')
  const [upperLimit, setUpperLimit] = useState('')
  const [lowerLimit, setLowerLimit] = useState('')
  const [error, setError] = useState(null)

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    try {
      await onCreate({
        nominal_value: Number(nominalValue),
        upper_limit: Number(upperLimit),
        lower_limit: Number(lowerLimit),
      })
    } catch (err) {
      setError(err.message)
    }
  }

  if (entry) {
    return (
      <div>
        <h3>{title}</h3>
        <p>
          {entry.entry_code}: nominal {entry.nominal_value}, band {entry.nominal_value - entry.lower_limit}
          {' to '}
          {entry.nominal_value + entry.upper_limit} (+{entry.upper_limit} / -{entry.lower_limit})
        </p>
      </div>
    )
  }

  return (
    <div>
      <h3>{title}</h3>
      <p>Not attached yet.</p>
      <form onSubmit={handleSubmit} className="inline-form">
        <input
          type="number"
          step="any"
          placeholder="Nominal"
          value={nominalValue}
          onChange={(e) => setNominalValue(e.target.value)}
          required
        />
        <input
          type="number"
          step="any"
          min="0"
          placeholder="Upper limit (+)"
          value={upperLimit}
          onChange={(e) => setUpperLimit(e.target.value)}
          required
        />
        <input
          type="number"
          step="any"
          min="0"
          placeholder="Lower limit (-)"
          value={lowerLimit}
          onChange={(e) => setLowerLimit(e.target.value)}
          required
        />
        <button type="submit">Add {title}</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

// Image upload + the annotation canvas for whichever image is selected.
function ImagesSection({ analysisId }) {
  const [images, setImages] = useState([])
  const [selectedImageId, setSelectedImageId] = useState(null)
  const [markers, setMarkers] = useState([])
  const [error, setError] = useState(null)

  function refreshImages() {
    listImages(analysisId).then(setImages).catch((err) => setError(err.message))
  }

  useEffect(refreshImages, [analysisId])

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
      await uploadImage(analysisId, file)
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
      if (selectedImageId === imageId) {
        setSelectedImageId(null)
      }
      refreshImages()
    } catch (err) {
      setError(err.message)
    }
  }

  const handleCreateMarker = useCallback(
    async (x, y) => {
      if (selectedImageId === null) return
      try {
        await createMarker(selectedImageId, x, y)
        refreshMarkers()
      } catch (err) {
        setError(err.message)
      }
    },
    [selectedImageId],
  )

  const handleDeleteMarker = useCallback(async (markerId) => {
    try {
      await deleteMarker(markerId)
      refreshMarkers()
    } catch (err) {
      setError(err.message)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div>
      <h3>Images</h3>
      {error && <p className="form-error">{error}</p>}

      <ul>
        {images.map((image) => (
          <li key={image.image_id}>
            <button type="button" onClick={() => setSelectedImageId(image.image_id)}>
              {image.original_filename}
            </button>{' '}
            <button type="button" onClick={() => handleDeleteImage(image.image_id)}>
              Delete
            </button>
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
            Drag a small box on the image to drop a numbered marker at its center; click a
            marker to remove it.
          </p>
          <ImageAnnotator
            imageUrl={imageFileUrl(selectedImageId)}
            markers={markers}
            onCreateMarker={handleCreateMarker}
            onDeleteMarker={handleDeleteMarker}
          />
        </div>
      )}
    </div>
  )
}

function AnalysisDetailPage() {
  const { analysisId } = useParams()
  const [analysis, setAnalysis] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    getAnalysis(analysisId).then(setAnalysis).catch((err) => setError(err.message))
  }

  useEffect(refresh, [analysisId])

  if (error) {
    return <p className="form-error">{error}</p>
  }
  if (!analysis) {
    return <p>Loading...</p>
  }

  return (
    <div>
      <h2>{analysis.analysis_code}</h2>
      <EntrySection
        title="Gap"
        entry={analysis.gap}
        onCreate={async (body) => {
          await createGapEntry(analysisId, body)
          refresh()
        }}
      />
      <EntrySection
        title="Flush"
        entry={analysis.flush}
        onCreate={async (body) => {
          await createFlushEntry(analysisId, body)
          refresh()
        }}
      />
      <ImagesSection analysisId={analysisId} />
    </div>
  )
}

export default AnalysisDetailPage
