import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { createCommodity, listCommodities } from '../api/client.js'

function CommodityListPage() {
  const { projectId } = useParams()
  const [commodities, setCommodities] = useState([])
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState(null)

  function refresh() {
    listCommodities(projectId).then(setCommodities).catch((err) => setError(err.message))
  }

  useEffect(refresh, [projectId])

  async function handleCreate(event) {
    event.preventDefault()
    setError(null)
    try {
      await createCommodity(projectId, name, code)
      setName('')
      setCode('')
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
      <div className="section-header-row">
        <h2>Commodities</h2>
        <Link className="btn-primary" to={`/projects/${projectId}/standard-tolerances`}>
          Add Standard Tolerance
        </Link>
      </div>
      <ul className="link-list">
        {commodities.map((commodity) => (
          <li key={commodity.commodity_id}>
            <Link to={`/projects/${projectId}/commodities/${commodity.commodity_id}/analyses`}>
              {commodity.name} ({commodity.code})
            </Link>
          </li>
        ))}
      </ul>

      <div className="section-divider" />

      <form onSubmit={handleCreate} className="inline-form">
        <label>
          Name{' '}
          <input type="text" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Code (2 letters){' '}
          <input
            type="text"
            placeholder="Code (2 letters)"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={2}
            required
          />
        </label>
        <button type="submit">Create commodity</button>
      </form>
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default CommodityListPage
