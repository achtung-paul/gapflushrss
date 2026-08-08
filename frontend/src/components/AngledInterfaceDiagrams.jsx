// Two conceptual diagrams for the angled-interface help page
// (pages/AngledInterfaceHelpPage.jsx). Hand-drawn inline SVG, following
// RssDistributionChart.jsx's convention exactly: fixed pixel design grid
// as module constants, geometry computed with real trig rather than
// hand-picked pixel coordinates, colours/fonts via CSS classes. These are
// conceptual, not data-driven, so there's no RAG_COLORS-style map --
// var(--color-heading) plus greys cover it.

const RESOLUTION_WIDTH = 520
const RESOLUTION_HEIGHT = 290
// 45 degrees, matching the worked example used throughout the help page
// -- not the user's actual saved angle, which is why this is a fixed
// illustrative constant, not a prop.
const DIAGRAM_ANGLE_DEGREES = 45
const ARC_SAMPLE_COUNT = 20

// Two faces meeting at an angle, with a horizontal tolerance (Tx) and a
// vertical one (Ty) each shown next to their shorter, resolved
// counterpart (Vx, Vy) -- scaled by real cos/sin of the diagram angle, so
// the shortening is genuinely proportional, not just illustrative.
export function AngleResolutionDiagram() {
  const angleRadians = (DIAGRAM_ANGLE_DEGREES * Math.PI) / 180
  const vertex = { x: 70, y: 210 }
  const faceALength = 190
  const faceBLength = 150

  const faceAEnd = { x: vertex.x + faceALength, y: vertex.y }
  const faceBEnd = {
    x: vertex.x + faceBLength * Math.cos(angleRadians),
    y: vertex.y - faceBLength * Math.sin(angleRadians),
  }

  const arcRadius = 34
  const arcPoints = []
  for (let i = 0; i <= ARC_SAMPLE_COUNT; i += 1) {
    const a = (angleRadians * i) / ARC_SAMPLE_COUNT
    arcPoints.push(`${vertex.x + arcRadius * Math.cos(a)},${vertex.y - arcRadius * Math.sin(a)}`)
  }

  // X row: a horizontal Tx arrow, then a shorter Vx arrow scaled by
  // cos(theta), stacked with generous vertical spacing so the two labels
  // (each wider than the arrow itself) don't collide.
  const txStart = { x: 330, y: 50 }
  const txLength = 110
  const txEnd = { x: txStart.x + txLength, y: txStart.y }
  const vxStart = { x: 330, y: 95 }
  const vxLength = txLength * Math.cos(angleRadians)
  const vxEnd = { x: vxStart.x + vxLength, y: vxStart.y }

  // Y row: a vertical Ty arrow, then a shorter Vy arrow scaled by
  // sin(theta), placed well clear of the X row above (y >= 140) and
  // spaced from Ty horizontally so the two arrows and labels don't overlap.
  const tyStart = { x: 340, y: 250 }
  const tyLength = 100
  const tyEnd = { x: tyStart.x, y: tyStart.y - tyLength }
  const vyStart = { x: 430, y: 250 }
  const vyLength = tyLength * Math.sin(angleRadians)
  const vyEnd = { x: vyStart.x, y: vyStart.y - vyLength }

  return (
    <svg
      viewBox={`0 0 ${RESOLUTION_WIDTH} ${RESOLUTION_HEIGHT}`}
      width="100%"
      className="angled-diagram"
      role="img"
      aria-label="Diagram showing an X tolerance and a Y tolerance each resolved onto an interface angled at theta"
    >
      {/* The two faces meeting at the interface angle. */}
      <line
        x1={vertex.x}
        y1={vertex.y}
        x2={faceAEnd.x}
        y2={faceAEnd.y}
        className="angled-diagram-face"
      />
      <line
        x1={vertex.x}
        y1={vertex.y}
        x2={faceBEnd.x}
        y2={faceBEnd.y}
        className="angled-diagram-face"
      />
      <polyline points={arcPoints.join(' ')} className="angled-diagram-arc" />
      <text x={vertex.x + 44} y={vertex.y - 14} className="angled-diagram-label">
        θ = 45°
      </text>
      <text x={faceAEnd.x - 40} y={faceAEnd.y + 16} className="angled-diagram-label">
        Face A
      </text>
      <text x={faceBEnd.x + 6} y={faceBEnd.y} className="angled-diagram-label">
        Face B (interface)
      </text>

      {/* X row: Tx before resolution, Vx after. */}
      <g className="angled-diagram-vector">
        <line x1={txStart.x} y1={txStart.y} x2={txEnd.x} y2={txEnd.y} markerEnd="url(#angled-arrowhead)" />
      </g>
      <text x={txStart.x} y={txStart.y - 8} className="angled-diagram-label">
        Tx
      </text>
      <g className="angled-diagram-projection">
        <line x1={vxStart.x} y1={vxStart.y} x2={vxEnd.x} y2={vxEnd.y} markerEnd="url(#angled-arrowhead)" />
      </g>
      <text x={vxStart.x} y={vxStart.y + 16} className="angled-diagram-label">
        Vx = Tx · cos θ
      </text>

      {/* Y row: Ty before resolution, Vy after. */}
      <g className="angled-diagram-vector">
        <line x1={tyStart.x} y1={tyStart.y} x2={tyEnd.x} y2={tyEnd.y} markerEnd="url(#angled-arrowhead)" />
      </g>
      <text x={tyStart.x - 24} y={tyEnd.y - 6} className="angled-diagram-label">
        Ty
      </text>
      <g className="angled-diagram-projection">
        <line x1={vyStart.x} y1={vyStart.y} x2={vyEnd.x} y2={vyEnd.y} markerEnd="url(#angled-arrowhead)" />
      </g>
      <text x={vyStart.x + 6} y={vyEnd.y} className="angled-diagram-label">
        Vy = Ty · sin θ
      </text>

      <defs>
        <marker id="angled-arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" className="angled-diagram-arrowhead" />
        </marker>
      </defs>
    </svg>
  )
}

const STACKING_WIDTH = 600
const STACKING_HEIGHT = 200

// Four equal illustrative magnitudes (0.7071 each, matching the 45 degree
// worked example) shown two ways: laid end-to-end (worst case) versus
// combined in quadrature (RSS) -- deliberately a length comparison, not a
// right-triangle drawing. A right triangle is only geometrically exact
// for exactly two magnitudes; the model used here root-sum-squares every
// individual resolved value from every row, which for more than two
// values has no single 2D triangle picture -- drawing one anyway would
// misrepresent the maths it's meant to explain.
export function StackingComparisonDiagram() {
  const magnitude = 0.70710678
  const count = 4
  const pxPerUnit = 70
  const segmentWidth = magnitude * pxPerUnit
  const worstCaseTotal = count * magnitude
  const rssTotal = magnitude * Math.sqrt(count)
  const rssWidth = rssTotal * pxPerUnit

  const barX = 40
  const worstCaseY = 60
  const rssY = 140
  const barHeight = 22

  return (
    <svg
      viewBox={`0 0 ${STACKING_WIDTH} ${STACKING_HEIGHT}`}
      width="100%"
      className="angled-diagram"
      role="img"
      aria-label="Diagram comparing worst-case linear stacking against RSS combination of the same four tolerances"
    >
      {/* Worst case: four equal segments laid end to end. */}
      {Array.from({ length: count }, (_, index) => (
        <rect
          key={index}
          x={barX + index * segmentWidth}
          y={worstCaseY}
          width={segmentWidth}
          height={barHeight}
          className={index % 2 === 0 ? 'angled-diagram-bar' : 'angled-diagram-bar-alt'}
        />
      ))}
      <text x={barX} y={worstCaseY - 10} className="angled-diagram-label">
        Worst case = 4 × 0.707 = {worstCaseTotal.toFixed(3)}
      </text>

      {/* RSS: the same four magnitudes, combined in quadrature -- a
          single shorter bar, not a concatenation of the same segments. */}
      <rect x={barX} y={rssY} width={rssWidth} height={barHeight} className="angled-diagram-bar-rss" />
      <text x={barX} y={rssY - 10} className="angled-diagram-label">
        RSS = √4 × 0.707 = {rssTotal.toFixed(3)}
      </text>
    </svg>
  )
}
