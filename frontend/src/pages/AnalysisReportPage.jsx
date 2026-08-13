import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  analysisImageFileUrl,
  getAnalysis,
  getAngledSimulation,
  getSimulation,
  listAnalysisImages,
  listAngledComponents,
  listChainComponents,
  listCommodities,
  listProjects,
} from '../api/client.js'
import RssDistributionChart from '../components/RssDistributionChart.jsx'

const CONTRIBUTOR_TYPE_LABELS = {
  COMPONENT: 'Component tolerance',
  PROCESS: 'Assembly process variation',
}

// Same pass/caution/fail wording as ToleranceChainSection.jsx/
// AnalysisListPage.jsx's sigma tables -- kept as its own copy here
// rather than a shared import, matching how those two already each
// have their own copy (identical shape, no third home worth adding).
const RAG_LABELS = {
  green: 'Pass',
  amber: 'Caution',
  red: 'Fail',
  not_evaluated: 'Not evaluated',
}
const RAG_CLASS = {
  green: 'rag-green',
  amber: 'rag-amber',
  red: 'rag-red',
  not_evaluated: 'rag-not-evaluated',
}

const METHOD_LABELS = {
  WORST_CASE: 'Worst case',
  RSS: 'Statistical (RSS)',
}

// A printable report for one Gap or Flush entry -- reachable from
// AnalysisDetailPage.jsx's "Print report" link, opened in a new tab so
// the interactive page underneath isn't lost. No edit controls, no nav
// beyond a single back-link -- everything here (including the Print
// button) is hidden by index.css's @media print block, since it exists
// only to let the browser's own Print -> Save as PDF produce the actual
// report.
function AnalysisReportPage() {
  const { projectId, analysisId, entryType } = useParams()
  const [analysis, setAnalysis] = useState(null)
  const [project, setProject] = useState(null)
  const [commodity, setCommodity] = useState(null)
  const [chainComponents, setChainComponents] = useState([])
  const [simulation, setSimulation] = useState(null)
  const [angledComponents, setAngledComponents] = useState([])
  const [angledSimulation, setAngledSimulation] = useState(null)
  const [images, setImages] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    getAnalysis(projectId, analysisId).then(setAnalysis).catch((err) => setError(err.message))
    listProjects()
      .then((projects) => setProject(projects.find((p) => p.project_id === Number(projectId))))
      .catch((err) => setError(err.message))
  }, [projectId, analysisId])

  useEffect(() => {
    if (!analysis) return
    listCommodities(projectId)
      .then((commodities) => setCommodity(commodities.find((c) => c.commodity_id === analysis.commodity_id)))
      .catch((err) => setError(err.message))
  }, [projectId, analysis])

  const entry = entryType === 'gap' ? analysis?.gap : analysis?.flush

  useEffect(() => {
    if (!entry) return
    // This entry's own gallery, not the whole Analysis's -- Gap and
    // Flush each have their own (see AnalysisImageGallery.jsx).
    listAnalysisImages(projectId, entry.entry_id).then(setImages).catch((err) => setError(err.message))
    if (entry.direction === 'OTHER') {
      listAngledComponents(projectId, entry.entry_id).then(setAngledComponents).catch((err) => setError(err.message))
      getAngledSimulation(projectId, entry.entry_id).then(setAngledSimulation).catch((err) => setError(err.message))
    } else {
      listChainComponents(projectId, entry.entry_id).then(setChainComponents).catch((err) => setError(err.message))
      getSimulation(projectId, entry.entry_id).then(setSimulation).catch((err) => setError(err.message))
    }
  }, [projectId, entry?.entry_id, entry?.direction])

  if (error) {
    return <p className="form-error">{error}</p>
  }
  if (!analysis) {
    return <p>Loading...</p>
  }

  const title = entryType === 'gap' ? 'Gap' : 'Flush'
  const displayCode = entry
    ? entry.entry_code + (entry.direction ? `-${entry.direction}` : '')
    : `${analysis.analysis_code}-${title.toUpperCase()}`

  return (
    <div>
      <p className="no-print">
        <Link to={`/projects/${projectId}/analyses/${analysisId}`}>&larr; Back to analysis</Link>
      </p>
      <button type="button" className="no-print" onClick={() => window.print()}>
        Print
      </button>

      <h2>
        {displayCode}
        {analysis.description && ` - ${analysis.description}`}
      </h2>
      <p className="form-hint">
        {project?.project_name} / {commodity?.name} ({commodity?.code})
      </p>

      {!entry ? (
        <p>This {title} entry hasn&apos;t been created yet.</p>
      ) : (
        <>
          <p className="entry-band">
            Nominal {entry.nominal_value} mm, Band{' '}
            {(entry.nominal_value - entry.lower_limit).toFixed(3)} mm to{' '}
            {(entry.nominal_value + entry.upper_limit).toFixed(3)} mm (+{entry.upper_limit} mm /{' '}
            -{entry.lower_limit} mm)
          </p>
          <p className="form-hint">
            Created by {entry.created_by_name} &middot; Last modified by {entry.updated_by_name}
          </p>

          {entry.notes && (
            // Already sanitised on write (core/html_sanitize.py) -- same
            // value AnalysisDetailPage.jsx renders the same way.
            <div className="entry-notes" dangerouslySetInnerHTML={{ __html: entry.notes }} />
          )}

          <div className="section-divider" />

          {entry.direction === 'OTHER' ? (
            <>
              <h4>Angled interface</h4>
              <p className="form-hint">
                Interface angle {entry.interface_angle}&deg; &middot;{' '}
                {METHOD_LABELS[entry.calculation_method] ?? entry.calculation_method}
              </p>
              {angledComponents.length === 0 ? (
                <p>No angled components recorded.</p>
              ) : (
                <table className="rss-results contributor-table">
                  <thead>
                    <tr>
                      <th>Component</th>
                      <th>X tolerance (± mm)</th>
                      <th>Y tolerance (± mm)</th>
                      <th>Vx (mm)</th>
                      <th>Vy (mm)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {angledComponents.map((component) => {
                      const row = angledSimulation?.rows.find(
                        (r) => r.angled_component_id === component.angled_component_id,
                      )
                      return (
                        <tr key={component.angled_component_id}>
                          <td>{component.component_name}</td>
                          <td>±{component.x_tolerance} mm</td>
                          <td>±{component.y_tolerance} mm</td>
                          <td>{row ? row.vx.toFixed(3) : '--'}</td>
                          <td>{row ? row.vy.toFixed(3) : '--'}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
              {angledSimulation && (
                <div className="angled-total">
                  <div className="angled-total-label">Total angled variation</div>
                  <div className="angled-total-value">
                    ±{angledSimulation.total_variation.toFixed(3)} mm{' '}
                    <span className={`rag-badge ${RAG_CLASS[angledSimulation.rag] ?? ''}`}>
                      {RAG_LABELS[angledSimulation.rag] ?? angledSimulation.rag}
                    </span>
                  </div>
                  <div className="angled-total-detail">
                    Predicted {angledSimulation.lower_bound.toFixed(3)} to{' '}
                    {angledSimulation.upper_bound.toFixed(3)} mm
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <h4>Tolerance chain</h4>
              {chainComponents.length === 0 ? (
                <p>No chain components recorded.</p>
              ) : (
                <table className="rss-results contributor-table">
                  <thead>
                    <tr>
                      <th>Type</th>
                      <th>Description</th>
                      <th>Tolerance (± mm)</th>
                      <th>Measured (mm)</th>
                      <th>Material</th>
                      <th>Tolerance group</th>
                      <th>Note</th>
                    </tr>
                  </thead>
                  <tbody>
                    {chainComponents.map((component) => (
                      <tr key={component.chain_component_id}>
                        <td>{CONTRIBUTOR_TYPE_LABELS[component.contributor_type] ?? component.contributor_type}</td>
                        <td>{component.description}</td>
                        <td>±{component.tolerance_value} mm</td>
                        <td>{component.measured_value !== null ? `${component.measured_value} mm` : '--'}</td>
                        <td>{component.material || '--'}</td>
                        <td>{component.tolerance_group_name || '--'}</td>
                        <td>{component.note || '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}

              {simulation && (
                <>
                  <table className="rss-results">
                    <thead>
                      <tr>
                        <th>Sigma level</th>
                        <th>Spread (± mm)</th>
                        <th>Predicted range (mm)</th>
                        <th>RAG</th>
                      </tr>
                    </thead>
                    <tbody>
                      {simulation.results.map((result) => (
                        <tr key={result.sigma_level}>
                          <td>{result.sigma_level}σ</td>
                          <td>{result.spread.toFixed(3)} mm</td>
                          <td>
                            {result.lower_bound.toFixed(3)} to {result.upper_bound.toFixed(3)} mm
                          </td>
                          <td>
                            <span className={`rag-badge ${result.info_only ? 'rag-info' : RAG_CLASS[result.rag] ?? ''}`}>
                              {result.info_only ? 'Info' : RAG_LABELS[result.rag] ?? result.rag}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="form-hint no-print">
                    <Link to="/help/statistical-model">About the statistical model</Link>
                  </p>
                  <RssDistributionChart
                    nominal={entry.nominal_value}
                    upperLimit={entry.upper_limit}
                    lowerLimit={entry.lower_limit}
                    sigma1={simulation.sigma_1}
                    results={simulation.results}
                  />
                </>
              )}
            </>
          )}

          {images.length > 0 && (
            <>
              <div className="section-divider" />
              <h4>Images</h4>
              <div className="analysis-gallery-grid report-gallery-grid">
                {images.map((image) => (
                  <img
                    key={image.analysis_image_id}
                    src={analysisImageFileUrl(projectId, image.analysis_image_id)}
                    alt={image.original_filename}
                    className="analysis-gallery-thumb report-gallery-thumb"
                  />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

export default AnalysisReportPage
