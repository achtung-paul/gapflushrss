import { useEffect, useState } from 'react'
import {
  analysisImageFileUrl,
  deleteAnalysisImage,
  listAnalysisImages,
  uploadAnalysisImage,
} from '../api/client.js'

// A plain photo gallery attached to one Analysis -- distinct from the
// Commodity's single annotated assembly image with markers (see
// ImageAnnotator.jsx). Thumbnails in a 3-wide grid; click one to expand
// it full-width in an overlay, click the overlay (or its close button)
// to collapse back to the grid.
function AnalysisImageGallery({ projectId, analysisId }) {
  const [images, setImages] = useState([])
  const [expandedId, setExpandedId] = useState(null)
  // Delete doesn't happen immediately -- it opens a small confirm/cancel
  // popup first, so an image can't be lost to a stray click. Holds the
  // analysis_image_id awaiting confirmation, or null.
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  const [error, setError] = useState(null)

  function refresh() {
    listAnalysisImages(projectId, analysisId).then(setImages).catch((err) => setError(err.message))
  }

  useEffect(refresh, [projectId, analysisId])

  async function handleUpload(event) {
    event.preventDefault()
    setError(null)
    const files = Array.from(event.target.elements.files.files)
    if (files.length === 0) return
    try {
      // The backend takes one file per request (same as the Commodity
      // image upload endpoint) -- multiple selection just means looping.
      for (const file of files) {
        await uploadAnalysisImage(projectId, analysisId, file)
      }
      event.target.reset()
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDelete(imageId) {
    setError(null)
    try {
      await deleteAnalysisImage(projectId, imageId)
      setPendingDeleteId(null)
      if (expandedId === imageId) {
        setExpandedId(null)
      }
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  const expandedImage = images.find((image) => image.analysis_image_id === expandedId)

  return (
    <div className="analysis-gallery">
      <h4>Images</h4>
      {error && <p className="form-error">{error}</p>}

      <form onSubmit={handleUpload} className="inline-form">
        <input type="file" name="files" accept="image/*" multiple required />
        <button type="submit">Upload</button>
      </form>

      {images.length === 0 ? (
        <p>No images uploaded yet.</p>
      ) : (
        <div className="analysis-gallery-grid">
          {images.map((image) => (
            <div key={image.analysis_image_id} className="analysis-gallery-thumb-wrap">
              <img
                src={analysisImageFileUrl(projectId, image.analysis_image_id)}
                alt={image.original_filename}
                className="analysis-gallery-thumb"
                onClick={() => setExpandedId(image.analysis_image_id)}
              />
              {pendingDeleteId === image.analysis_image_id ? (
                <div className="analysis-gallery-confirm">
                  <p>Delete this image?</p>
                  <div>
                    <button type="button" onClick={() => handleDelete(image.analysis_image_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" onClick={() => setPendingDeleteId(null)}>
                      No
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="analysis-gallery-delete-btn"
                  title="Delete image"
                  onClick={() => setPendingDeleteId(image.analysis_image_id)}
                >
                  &times;
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {expandedImage && (
        <div className="analysis-gallery-lightbox" onClick={() => setExpandedId(null)}>
          <img
            src={analysisImageFileUrl(projectId, expandedImage.analysis_image_id)}
            alt={expandedImage.original_filename}
          />
        </div>
      )}
    </div>
  )
}

export default AnalysisImageGallery
