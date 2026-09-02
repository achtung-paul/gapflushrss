import { useEffect, useState } from 'react'
import {
  analysisImageFileUrl,
  deleteAnalysisImage,
  listAnalysisImages,
  updateAnalysisImageTag,
  uploadAnalysisImage,
} from '../api/client.js'

// Matches ImageTag in models/analysis_image.py -- Sketch Agreed always
// sorts first in the list the backend returns (list_analysis_images),
// so no client-side reordering is needed here.
const IMAGE_TAG_OPTIONS = [
  { value: 'sketch_proposal', label: 'Sketch Proposal' },
  { value: 'sketch_agreed', label: 'Sketch Agreed' },
  { value: 'other', label: 'Other' },
]

// A plain photo gallery attached to one Gap or Flush entry -- distinct
// from the Commodity's single annotated assembly image with markers
// (see ImageAnnotator.jsx). Gap and Flush each get their own separate
// gallery (see models/analysis_image.py), so this is mounted once per
// entry, not once per Analysis. Thumbnails in a 3-wide grid; click one
// to expand it full-width in an overlay, click the overlay (or its
// close button) to collapse back to the grid.
function AnalysisImageGallery({ projectId, entryId }) {
  const [images, setImages] = useState([])
  const [expandedId, setExpandedId] = useState(null)
  // Delete doesn't happen immediately -- it opens a small confirm/cancel
  // popup first, so an image can't be lost to a stray click. Holds the
  // analysis_image_id awaiting confirmation, or null.
  const [pendingDeleteId, setPendingDeleteId] = useState(null)
  // Tag applied to every file in the next upload -- multiple files
  // selected at once all get this same tag (changeable per-image
  // afterwards via the dropdown under each thumbnail).
  const [uploadTag, setUploadTag] = useState('other')
  const [error, setError] = useState(null)

  function refresh() {
    listAnalysisImages(projectId, entryId).then(setImages).catch((err) => setError(err.message))
  }

  useEffect(refresh, [projectId, entryId])

  async function handleUpload(event) {
    event.preventDefault()
    setError(null)
    const files = Array.from(event.target.elements.files.files)
    if (files.length === 0) return
    try {
      // The backend takes one file per request (same as the Commodity
      // image upload endpoint) -- multiple selection just means looping.
      for (const file of files) {
        await uploadAnalysisImage(projectId, entryId, file, uploadTag)
      }
      event.target.reset()
      setUploadTag('other')
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

  async function handleTagChange(imageId, tag) {
    setError(null)
    try {
      await updateAnalysisImageTag(projectId, imageId, tag)
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
        <label>
          Image files{' '}
          <input type="file" name="files" accept="image/*" multiple required />
        </label>
        <label>
          Tag{' '}
          <select value={uploadTag} onChange={(e) => setUploadTag(e.target.value)}>
            {IMAGE_TAG_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
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
                    <button type="button" className="link-button" onClick={() => handleDelete(image.analysis_image_id)}>
                      Yes
                    </button>{' '}
                    <button type="button" className="link-button" onClick={() => setPendingDeleteId(null)}>
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
              <select
                className="analysis-gallery-tag-select"
                value={image.tag}
                onClick={(e) => e.stopPropagation()}
                onChange={(e) => handleTagChange(image.analysis_image_id, e.target.value)}
              >
                {IMAGE_TAG_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
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
