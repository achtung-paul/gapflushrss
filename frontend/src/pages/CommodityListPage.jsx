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
        {' | '}
        <Link to={`/projects/${projectId}/standard-tolerances`}>Standard tolerances</Link>
      </p>
      <h2>Commodities</h2>
      <ul>
        {commodities.map((commodity) => (
          <li key={commodity.commodity_id}>
            <Link to={`/projects/${projectId}/commodities/${commodity.commodity_id}/analyses`}>
              {commodity.name} ({commodity.code})
            </Link>
          </li>
        ))}
      </ul>

      <form onSubmit={handleCreate} className="inline-form">
        <label>
          Name{' '}
          <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        </label>
        <label>
          Code (2 letters){' '}
          <input
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
