import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { init as initAnnotoriousLib } from '@recogito/annotorious'
import '@recogito/annotorious/dist/annotorious.min.css'

// Reads the clicked vertices out of an Annotorious polygon annotation.
// Annotorious's core library (no plugin) has no dedicated "polyline"
// drawing tool, so we drive its 'polygon' tool instead -- click to add
// a vertex, double-click to finish -- and read the vertices back out
// ourselves rather than keeping Annotorious's own closed/filled shape
// on screen (see handleCreateAnnotation below). Verified directly
// against the installed package's SvgSelector format: selector.value =
// '<svg><polygon points="x1,y1 x2,y2 ...">...</polygon></svg>'.
function extractPointsFromAnnotation(annotation) {
  const selector = annotation?.target?.selector
  if (typeof selector?.value !== 'string') {
    throw new Error('Annotation has no usable target selector')
  }
  const match = selector.value.match(/<polygon points="([^"]+)"/)
  if (!match) {
    throw new Error(`Unrecognized selector value: ${selector.value}`)
  }
  return match[1]
    .trim()
    .split(/\s+/)
    .map((pair) => {
      const [x, y] = pair.split(',').map(Number)
      return { x, y }
    })
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
function ImageAnnotator({ projectId, imageUrl, markers, onCreateMarker, onDeleteMarker }) {
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
      // We render the finished polyline ourselves (below, from the
      // marker data the backend hands back), so remove Annotorious's
      // own closed/filled copy of the shape immediately -- it was only
      // needed to capture where the user clicked.
      anno.removeAnnotation(annotation)

      try {
        const points = extractPointsFromAnnotation(annotation)
        const fractions = points.map((p) => ({
          x: p.x / imageEl.naturalWidth,
          y: p.y / imageEl.naturalHeight,
        }))
        onCreateMarker(fractions)
      } catch (err) {
        console.error('Could not read polyline points from Annotorious', err)
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
      // Swap the default 'rect' (drag-a-box) tool for 'polygon': click
      // to place a vertex, click again for the next one, double-click
      // to finish -- the closest built-in tool to drawing a polyline.
      anno.setDrawingTool('polygon')
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
      {/* Persisted polylines, drawn behind the balloons. viewBox 0-100
          on both axes maps directly onto the marker fraction
          coordinates below (left/top as %), independent of the image's
          own aspect ratio -- pointer-events: none so it never steals
          clicks from Annotorious's drawing surface underneath. */}
      <svg className="marker-polylines" viewBox="0 0 100 100" preserveAspectRatio="none">
        {markers.map((marker) => (
          <polyline
            key={marker.marker_id}
            points={marker.points.map((p) => `${p.x * 100},${p.y * 100}`).join(' ')}
          />
        ))}
      </svg>
      {markers.map((marker) => (
        <div
          key={marker.marker_id}
          className="marker-wrap"
          style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }}
        >
          <Link
            to={`/projects/${projectId}/analyses/${marker.analysis_id}`}
            className="balloon-marker"
            title={marker.analysis_code}
          >
            {marker.sequence_number}
          </Link>
          <button
            type="button"
            className="marker-delete-btn"
            title={`Delete ${marker.analysis_code} and its marker`}
            onClick={() => setPendingDeleteId(marker.marker_id)}
          >
            &times;
          </button>
          {pendingDeleteId === marker.marker_id && (
            <div className="marker-confirm-popup">
              <p>
                Delete marker {marker.sequence_number} ({marker.analysis_code})? This also removes
                its Gap/Flush and tolerance chain data.
              </p>
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
