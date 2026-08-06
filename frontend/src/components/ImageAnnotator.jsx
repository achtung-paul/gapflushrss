import { useEffect, useRef, useState } from 'react'
import { init as initAnnotoriousLib } from '@recogito/annotorious'
import '@recogito/annotorious/dist/annotorious.min.css'

// Reads the drawn shape's center out of an Annotorious annotation.
// Annotorious's core library (no plugin) only ships rect/polygon drawing
// tools -- there's no single-click "point" tool -- so we use the default
// 'rect' tool and take the center of the small box the user drags as the
// marker position. Verified directly against the installed package's
// FragmentSelector format: selector.value = "xywh=pixel:x,y,w,h".
function extractCenterFromAnnotation(annotation) {
  const selector = annotation?.target?.selector
  if (typeof selector?.value !== 'string') {
    throw new Error('Annotation has no usable target selector')
  }
  const match = selector.value.match(/xywh=pixel:([\d.]+),([\d.]+),([\d.]+),([\d.]+)/)
  if (!match) {
    throw new Error(`Unrecognized selector value: ${selector.value}`)
  }
  const [, x, y, w, h] = match.map(Number)
  return { x: x + w / 2, y: y + h / 2 }
}

// Wraps an image with Annotorious for placing markers, plus our own
// permanently-rendered numbered "balloon" overlay -- see the brief's
// reference image (red circle containing a number).
//
// Annotorious manipulates the DOM around the <img> itself (wrapping it,
// injecting an SVG overlay) outside of React's knowledge. Letting React
// also manage that same <img> as JSX is what broke the drawing
// interaction: React re-renders (e.g. once the marker list loads) and
// reconciles the tree it thinks exists, colliding with whatever
// Annotorious rearranged -- worse under React 18 StrictMode, which
// deliberately mounts/cleans up/re-mounts effects once in dev.
//
// The fix is to give Annotorious a plain container div that React
// renders once and never looks inside again; the <img> and everything
// Annotorious does to it are created and torn down with plain DOM calls
// in the effect below, entirely outside React's reconciliation.
function ImageAnnotator({ imageUrl, markers, onCreateMarker, onDeleteMarker }) {
  const containerRef = useRef(null)
  // Clicking a marker doesn't delete it immediately -- it opens a small
  // confirm/cancel popup first, so a marker can't be lost to a stray
  // click. Holds the marker_id awaiting confirmation, or null.
  const [pendingDeleteId, setPendingDeleteId] = useState(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) {
      return undefined
    }

    // Always start from an empty container -- this also makes the setup
    // safe to run twice in a row (React 18 StrictMode's dev-mode
    // double-invoke), since there's nothing left over from a previous
    // run for Annotorious to get confused by.
    container.innerHTML = ''

    const imageEl = document.createElement('img')
    imageEl.src = imageUrl
    imageEl.alt = 'Analysis reference'
    imageEl.draggable = false
    container.appendChild(imageEl)

    let anno = null

    function handleCreateAnnotation(annotation) {
      // We render markers ourselves (below), so remove Annotorious's own
      // copy of the shape immediately -- it was only needed to capture
      // where the user dragged.
      anno.removeAnnotation(annotation)

      try {
        const { x, y } = extractCenterFromAnnotation(annotation)
        onCreateMarker(x / imageEl.naturalWidth, y / imageEl.naturalHeight)
      } catch (err) {
        console.error('Could not read marker position from Annotorious', err)
      }
    }

    // Annotorious reads the image's natural width/height when it
    // initializes, to size its SVG overlay -- if the image hasn't
    // finished loading yet, that would be 0x0. `complete` covers the
    // already-loaded/cached case; `load` covers the still-loading case.
    function initAnnotorious() {
      // allowEmpty is required alongside disableEditor: true -- without
      // it, Annotorious treats a shape with no tags/comments as
      // incomplete and silently discards it on deselect instead of
      // firing createAnnotation.
      anno = initAnnotoriousLib({ image: imageEl, disableEditor: true, allowEmpty: true })
      anno.on('createAnnotation', handleCreateAnnotation)
    }

    if (imageEl.complete) {
      initAnnotorious()
    } else {
      imageEl.addEventListener('load', initAnnotorious)
    }

    return () => {
      imageEl.removeEventListener('load', initAnnotorious)
      if (anno) anno.destroy()
      container.innerHTML = ''
    }
  }, [imageUrl, onCreateMarker])

  return (
    <div className="annotator-wrap">
      <div ref={containerRef} className="annotator-image-container" />
      {markers.map((marker) => (
        <div
          key={marker.marker_id}
          className="marker-wrap"
          style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }}
        >
          <button
            type="button"
            className="balloon-marker"
            title={`Marker ${marker.sequence_number} (click to remove)`}
            onClick={() => setPendingDeleteId(marker.marker_id)}
          >
            {marker.sequence_number}
          </button>
          {pendingDeleteId === marker.marker_id && (
            <div className="marker-confirm-popup">
              <p>Delete marker {marker.sequence_number}?</p>
              <div className="marker-confirm-buttons">
                <button
                  type="button"
                  className="marker-confirm-delete"
                  onClick={() => {
                    setPendingDeleteId(null)
                    onDeleteMarker(marker.marker_id)
                  }}
                >
                  Delete
                </button>
                <button type="button" onClick={() => setPendingDeleteId(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

export default ImageAnnotator
