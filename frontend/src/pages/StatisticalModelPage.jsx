import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listStatisticalModelSettings, updateStatisticalModelSettings } from '../api/client.js'

// Only reachable via <ProtectedRoute requireClientAdmin> (see App.jsx).
// Lets a client admin pick which RSS confidence levels (1-5 sigma, see
// core/simulation.py) their analysis pages show, and mark any shown
// level as info-only -- displayed with its predicted spread but no
// pass/fail verdict. Every client always has exactly one row per level
// (models/statistical_model_setting.py), so this is always editing 5
// existing rows, never adding/removing one.
function StatisticalModelPage() {
  const [settings, setSettings] = useState([])
  const [error, setError] = useState(null)
  const [saved, setSaved] = useState(false)

  function refresh() {
    listStatisticalModelSettings().then(setSettings).catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  function updateRow(sigmaLevel, changes) {
    setSaved(false)
    setSettings((current) =>
      current.map((row) => (row.sigma_level === sigmaLevel ? { ...row, ...changes } : row)),
    )
  }

  async function handleSave(event) {
    event.preventDefault()
    setError(null)
    try {
      const result = await updateStatisticalModelSettings(settings)
      setSettings(result)
      setSaved(true)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <p>
        <Link to="/client-admin">&larr; Client admin</Link>
      </p>
      <h2>Statistical model</h2>
      <p>
        Choose which sigma levels appear on this client&apos;s analysis pages, and mark any of them
        as info-only to show the predicted spread without a pass/fail verdict.{' '}
        <Link to="/help/statistical-model">Help</Link>
      </p>
      {error && <p className="form-error">{error}</p>}

      <form onSubmit={handleSave}>
        <table>
          <thead>
            <tr>
              <th>Sigma level</th>
              <th>Visible</th>
              <th>Info only</th>
            </tr>
          </thead>
          <tbody>
            {settings.map((row) => (
              <tr key={row.sigma_level}>
                <td>{row.sigma_level}σ</td>
                <td>
                  <input
                    type="checkbox"
                    checked={row.visible}
                    onChange={(e) => updateRow(row.sigma_level, { visible: e.target.checked })}
                  />
                </td>
                <td>
                  <input
                    type="checkbox"
                    checked={row.info_only}
                    disabled={!row.visible}
                    onChange={(e) => updateRow(row.sigma_level, { info_only: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="submit">Save</button>
        {saved && <span> Saved.</span>}
      </form>
    </div>
  )
}

export default StatisticalModelPage
