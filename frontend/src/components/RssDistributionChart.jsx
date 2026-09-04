// Draws the predicted gap/flush distribution as a normal curve, plus
// the target's tolerance band and the 3/4/5 sigma bounds from the RSS
// simulation. Hand-drawn as inline SVG rather than pulling in a
// charting library -- this is one curve and a few vertical lines, which
// doesn't justify a new dependency in a codebase that doesn't have one
// already.

const WIDTH = 600
const HEIGHT = 220
const CURVE_TOP = 20
const BASELINE_Y = HEIGHT - 40
const CURVE_HEIGHT = BASELINE_Y - CURVE_TOP
const SAMPLE_COUNT = 100

const RAG_COLORS = {
  green: '#2e7d32',
  amber: '#b8860b',
  red: '#d32f2f',
  // Empty chain -- no verdict to colour (see core/simulation.py). The
  // curve itself is already suppressed in this case via hasChainData
  // below; this keeps the sigma marker lines a neutral grey rather than
  // falling through to SVG's default black.
  not_evaluated: '#999999',
}
// A result the client has marked info_only (StatisticalModelSetting)
// never gets a RAG colour here either, regardless of what its rag value
// actually computed to -- same blue as index.css's .rag-info, so the
// chart and the results table agree on which levels are "no verdict".
const INFO_ONLY_COLOR = '#1c4870'

// Standard normal PDF, shifted/scaled to mean 0 -- we only need the
// *shape* of the curve (its peak is rescaled to fit the chart), not the
// true probability density values.
function normalPdf(x, sigma) {
  return Math.exp(-(x * x) / (2 * sigma * sigma)) / (sigma * Math.sqrt(2 * Math.PI))
}

// Legend entries shown under the chart, in the order they should read.
// The RAG/info-only swatches use the same colours as the sigma-level
// lines above (RAG_COLORS/INFO_ONLY_COLOR), not .rag-badge's pill
// colours, so the legend always matches what's actually drawn.
const LEGEND_ITEMS = [
  { key: 'band', label: 'Tolerance band (LL-UL)', swatch: 'swatch-band' },
  { key: 'nominal', label: 'Nominal', swatch: 'swatch-nominal' },
  { key: 'curve', label: 'Predicted distribution', swatch: 'swatch-curve' },
  { key: 'green', label: 'Within band', color: RAG_COLORS.green },
  { key: 'amber', label: 'Minor breach (≤5% over limit)', color: RAG_COLORS.amber },
  { key: 'red', label: 'Major breach (>5% over limit)', color: RAG_COLORS.red },
]

function RssDistributionChart({ nominal, upperLimit, lowerLimit, sigma1, results }) {
  const largestSpread = results.length > 0 ? results[results.length - 1].spread : 0
  const halfWidth = Math.max(largestSpread, upperLimit, lowerLimit, 0.1) * 1.2
  const domainMin = nominal - halfWidth
  const domainMax = nominal + halfWidth

  function xToPixel(value) {
    return ((value - domainMin) / (domainMax - domainMin)) * WIDTH
  }

  const bandLower = nominal - lowerLimit
  const bandUpper = nominal + upperLimit

  const hasChainData = sigma1 > 0
  const hasInfoOnly = results.some((result) => result.info_only)

  let curvePoints = ''
  if (hasChainData) {
    const peak = normalPdf(0, sigma1)
    const points = []
    for (let i = 0; i <= SAMPLE_COUNT; i += 1) {
      const value = domainMin + ((domainMax - domainMin) * i) / SAMPLE_COUNT
      const height = (normalPdf(value - nominal, sigma1) / peak) * CURVE_HEIGHT
      points.push(`${xToPixel(value)},${BASELINE_Y - height}`)
    }
    curvePoints = points.join(' ')
  }

  return (
    <>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        width="100%"
        className="rss-chart"
        role="img"
        aria-label="Predicted distribution against the tolerance band"
      >
        {/* Tolerance band: the "safe zone" the predicted spread should stay inside. */}
        <rect
          x={xToPixel(bandLower)}
          y={CURVE_TOP}
          width={xToPixel(bandUpper) - xToPixel(bandLower)}
          height={CURVE_HEIGHT}
          className="rss-chart-band"
        />

        {hasChainData ? (
          <polyline points={curvePoints} className="rss-chart-curve" />
        ) : (
          <line
            x1={xToPixel(nominal)}
            x2={xToPixel(nominal)}
            y1={BASELINE_Y}
            y2={CURVE_TOP}
            className="rss-chart-curve"
          />
        )}

        {/* Nominal: the target value the band and curve are both centred on. */}
        <line
          x1={xToPixel(nominal)}
          x2={xToPixel(nominal)}
          y1={BASELINE_Y}
          y2={CURVE_TOP}
          className="rss-chart-nominal-line"
        />

        {results.map((result, index) => (
          <g key={result.sigma_level} stroke={result.info_only ? INFO_ONLY_COLOR : RAG_COLORS[result.rag]}>
            <line
              x1={xToPixel(nominal - result.spread)}
              x2={xToPixel(nominal - result.spread)}
              y1={BASELINE_Y}
              y2={CURVE_TOP}
              strokeDasharray="4 3"
            />
            <line
              x1={xToPixel(nominal + result.spread)}
              x2={xToPixel(nominal + result.spread)}
              y1={BASELINE_Y}
              y2={CURVE_TOP}
              strokeDasharray="4 3"
            />
            {/* Staggered vertically by sigma level -- otherwise the 3/4/5
                sigma labels overlap when their bounds land close together. */}
            <text
              x={xToPixel(nominal + result.spread) + 3}
              y={CURVE_TOP + 10 + index * 13}
              fill={result.info_only ? INFO_ONLY_COLOR : RAG_COLORS[result.rag]}
            >
              {result.sigma_level}σ
            </text>
          </g>
        ))}

        <line x1={0} x2={WIDTH} y1={BASELINE_Y} y2={BASELINE_Y} className="rss-chart-axis" />
        <text x={xToPixel(nominal)} y={HEIGHT - 20} textAnchor="middle" className="rss-chart-label">
          nominal {nominal}
        </text>
        <text x={xToPixel(bandLower)} y={HEIGHT - 5} textAnchor="middle" className="rss-chart-label">
          LL {bandLower.toFixed(2)}
        </text>
        <text x={xToPixel(bandUpper)} y={HEIGHT - 5} textAnchor="middle" className="rss-chart-label">
          UL {bandUpper.toFixed(2)}
        </text>
      </svg>

      <ul className="rss-chart-legend">
        {LEGEND_ITEMS.map((item) => (
          <li key={item.key}>
            <span
              className={`rss-chart-legend-swatch${item.swatch ? ` ${item.swatch}` : ''}`}
              style={item.color ? { background: item.color } : undefined}
            />
            {item.label}
          </li>
        ))}
        {hasInfoOnly && (
          <li>
            <span className="rss-chart-legend-swatch" style={{ background: INFO_ONLY_COLOR }} />
            Shown for reference only (not a pass/fail level)
          </li>
        )}
      </ul>
    </>
  )
}

export default RssDistributionChart
