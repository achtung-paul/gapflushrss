import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { createAnalysis, listAnalyses } from '../api/client.js'

function AnalysisListPage() {
  const { commodityId } = useParams()
  const [analyses, setAnalyses] = useState([])
  const [error, setError] = useState(null)

  function refresh() {
    listAnalyses(commodityId).then(setAnalyses).catch((err) => setError(err.message))
  }

  useEffect(refresh, [commodityId])

  async function handleCreate() {
    setError(null)
    try {
      await createAnalysis(commodityId)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <p>
        <Link to="/projects">&larr; Projects</Link>
      </p>
      <h2>Analyses</h2>
      <ul>
        {analyses.map((analysis) => (
          <li key={analysis.analysis_id}>
            <Link to={`/analyses/${analysis.analysis_id}`}>{analysis.analysis_code}</Link>
          </li>
        ))}
      </ul>

      <button onClick={handleCreate}>Create analysis</button>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default AnalysisListPage
