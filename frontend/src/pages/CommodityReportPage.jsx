import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  getSimulation,
  imageFileUrl,
  listAnalyses,
  listCommodities,
  listImages,
  listMarkers,
  listProjects,
  listStatisticalModelSettings,
} from '../api/client.js'

const DIRECTION_LABELS = { X: 'X', Y: 'Y', Z: 'Z', OTHER: 'Other' }
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
// Read-only counterpart to AnalysisListPage.jsx's EntryTableRow -- same
// per-row simulation fetch (there's no bulk "simulation for every entry"
// endpoint), just without the Edit/Delete/Add columns.
function ReportEntryRow({ projectId, analysisCode, analysisDescription, entryType, entry, sigmaColumns }) {
  const [simulation, setSimulation] = useState(null)

  useEffect(() => {
    if (!entry) {
      setSimulation(null)
      return
    }
    getSimulation(projectId, entry.entry_id).then(setSimulation).catch(() => setSimulation(null))
  }, [projectId, entry?.entry_id])

  return (
    <tr>
      <td>{analysisCode}</td>
      <td>{analysisDescription || '--'}</td>
      <td>{entryType === 'GAP' ? 'Gap' : 'Flush'}</td>
      <td>{(entry?.direction && DIRECTION_LABELS[entry.direction]) || '--'}</td>
      <td>{entry ? `${entry.nominal_value} mm` : '--'}</td>
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
      <td>{entry?.updated_by_name ?? '--'}</td>
    </tr>
  )
}

// Static (non-interactive) version of ImageAnnotator.jsx's balloon
// overlay -- a print report has no business pulling in Annotorious's
// drawing surface, it just needs to show where the markers already are.
function ReportAssemblyImage({ projectId, image, markers }) {
  return (
    <div className="annotator-wrap">
      <div className="annotator-image-container">
        <img src={imageFileUrl(projectId, image.image_id)} alt={image.original_filename} />
      </div>
      {markers.map((marker) => (
        <div
          key={marker.marker_id}
          className="marker-wrap"
          style={{ left: `${marker.x * 100}%`, top: `${marker.y * 100}%` }}
        >
          <span className="balloon-marker">{marker.sequence_number}</span>
        </div>
      ))}
    </div>
  )
}

// A printable summary of every analysis under one Commodity -- reachable
// from AnalysisListPage.jsx's "Print report" link, opened in a new tab.
// Everything here except the report content itself (Print button,
// back-link) is hidden by index.css's @media print block.
function CommodityReportPage() {
  const { projectId, commodityId } = useParams()
  const [project, setProject] = useState(null)
  const [commodity, setCommodity] = useState(null)
  const [analyses, setAnalyses] = useState([])
  const [images, setImages] = useState([])
  const [markersByImage, setMarkersByImage] = useState({})
  const [sigmaColumns, setSigmaColumns] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    listStatisticalModelSettings()
      .then((settings) => setSigmaColumns(settings.filter((s) => s.visible)))
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    listProjects()
      .then((projects) => setProject(projects.find((p) => p.project_id === Number(projectId))))
      .catch((err) => setError(err.message))
    listCommodities(projectId)
      .then((commodities) => setCommodity(commodities.find((c) => c.commodity_id === Number(commodityId))))
      .catch((err) => setError(err.message))
    listAnalyses(projectId, commodityId).then(setAnalyses).catch((err) => setError(err.message))
    listImages(projectId, commodityId).then(setImages).catch((err) => setError(err.message))
  }, [projectId, commodityId])

  useEffect(() => {
    images.forEach((image) => {
      listMarkers(projectId, image.image_id)
        .then((markers) => setMarkersByImage((prev) => ({ ...prev, [image.image_id]: markers })))
        .catch((err) => setError(err.message))
    })
  }, [projectId, images])

  if (error) {
    return <p className="form-error">{error}</p>
  }

  const rows = analyses.flatMap((analysis) => [
    { analysis, entryType: 'GAP', entry: analysis.gap },
    { analysis, entryType: 'FLUSH', entry: analysis.flush },
  ])

  return (
    <div>
      <p className="no-print">
        <Link to={`/projects/${projectId}/commodities/${commodityId}/analyses`}>&larr; Back to analyses</Link>
      </p>
      <button type="button" className="no-print" onClick={() => window.print()}>
        Print
      </button>

      <h2>
        {commodity?.name} ({commodity?.code})
      </h2>
      <p className="form-hint">{project?.project_name}</p>

      {images.length > 0 && (
        <>
          <div className="section-divider" />
          <h4>Assembly</h4>
          {images.map((image) => (
            <ReportAssemblyImage
              key={image.image_id}
              projectId={projectId}
              image={image}
              markers={markersByImage[image.image_id] ?? []}
            />
          ))}
        </>
      )}

      <div className="section-divider" />

      <h4>All analyses</h4>
      <table className="analysis-table contributor-table">
        <thead>
          <tr>
            <th>Analysis</th>
            <th>Description</th>
            <th>Gap/Flush</th>
            <th>Direction</th>
            <th>Nominal (mm)</th>
            {sigmaColumns.map((column) => (
              <th key={column.sigma_level}>{column.sigma_level}σ</th>
            ))}
            <th>Last modified by</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(({ analysis, entryType, entry }) => (
            <ReportEntryRow
              key={`${analysis.analysis_id}-${entryType}`}
              projectId={projectId}
              analysisCode={analysis.analysis_code}
              analysisDescription={analysis.description}
              entryType={entryType}
              entry={entry}
              sigmaColumns={sigmaColumns}
            />
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6 + sigmaColumns.length}>No analyses yet.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

export default CommodityReportPage
