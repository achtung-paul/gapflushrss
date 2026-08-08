import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { listLogs } from '../api/client.js'

// Root-admin view of recent errors from the backend, Postgres and MinIO
// together (see backend api/logs.py for how the three sources are
// collected and normalised).
//
// Refreshes every 5 seconds. The interval is cleared both when polling is
// paused and when the component unmounts -- no other page here polls, and
// an interval left running keeps hitting the API after you navigate away,
// which is invisible until it isn't.
const REFRESH_MS = 5000

const SERVICES = [
  { value: 'all', label: 'All services' },
  { value: 'backend', label: 'Backend' },
  { value: 'postgres', label: 'Postgres' },
  { value: 'minio', label: 'MinIO' },
]

const LEVELS = [
  { value: 'error', label: 'Errors only' },
  { value: 'warning', label: 'Warnings and errors' },
  { value: 'all', label: 'Everything' },
]

// Reuses the existing RAG badge colours rather than introducing a second
// severity palette (see index.css).
const LEVEL_CLASS = {
  ERROR: 'rag-red',
  CRITICAL: 'rag-red',
  FATAL: 'rag-red',
  PANIC: 'rag-red',
  WARNING: 'rag-amber',
}

function LogsPage() {
  const [entries, setEntries] = useState([])
  const [availableServices, setAvailableServices] = useState([])
  const [service, setService] = useState('all')
  const [level, setLevel] = useState('error')
  const [paused, setPaused] = useState(false)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  // Held in a ref so the polling effect doesn't need it as a dependency --
  // otherwise every fetch would tear down and rebuild the interval.
  const inFlight = useRef(false)

  const refresh = useCallback(async () => {
    if (inFlight.current) return // a slow response shouldn't stack up requests
    inFlight.current = true
    try {
      const data = await listLogs(service, level, 200)
      setEntries(data.entries)
      setAvailableServices(data.available_services)
      setLastUpdated(new Date())
      setError(null)
    } catch (err) {
      setError(err.message)
    } finally {
      inFlight.current = false
    }
  }, [service, level])

  // Fetch immediately on mount and whenever the filters change, so
  // changing a filter doesn't leave stale rows on screen until the next tick.
  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (paused) return undefined
    const id = setInterval(refresh, REFRESH_MS)
    return () => clearInterval(id)
  }, [paused, refresh])

  function togglePaused() {
    const resuming = paused
    setPaused(!paused)
    // Resuming fetches straight away rather than making the user wait out
    // the remainder of the interval.
    if (resuming) refresh()
  }

  const missingServices = SERVICES.filter(
    (option) =>
      option.value !== 'all' &&
      !availableServices.includes(option.value) &&
      (service === 'all' || service === option.value),
  )

  return (
    <div>
      <p>
        <Link to="/admin">&larr; Admin</Link>
      </p>
      <h2>Service logs</h2>

      <div className="inline-form">
        <label>
          Service{' '}
          <select value={service} onChange={(e) => setService(e.target.value)}>
            {SERVICES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Level{' '}
          <select value={level} onChange={(e) => setLevel(e.target.value)}>
            {LEVELS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={togglePaused}>
          {paused ? 'Resume' : 'Pause'}
        </button>
        <span className="form-hint">
          {paused
            ? 'Paused'
            : `Refreshing every ${REFRESH_MS / 1000}s${
                lastUpdated ? ` · updated ${lastUpdated.toLocaleTimeString()}` : ''
              }`}
        </span>
      </div>

      {error && <p className="form-error">{error}</p>}

      {missingServices.length > 0 && (
        // Distinguishes "this service has logged nothing" from "this
        // service is fine" -- an empty table looks the same either way.
        <p className="form-hint">
          No log file yet for: {missingServices.map((option) => option.label).join(', ')}.
        </p>
      )}

      <div className="section-divider" />

      <div className="analysis-table-scroll">
        <table className="analysis-table log-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Service</th>
              <th>Level</th>
              <th>Message</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry, index) => (
              // No stable id from the backend (these are log lines, not
              // rows), so index is combined with the timestamp to keep
              // keys stable for as long as the list is.
              <tr key={`${entry.timestamp}-${index}`}>
                <td className="log-time">{new Date(entry.timestamp).toLocaleString()}</td>
                <td>{entry.service}</td>
                <td>
                  <span className={`rag-badge ${LEVEL_CLASS[entry.level] ?? ''}`}>{entry.level}</span>
                </td>
                <td>
                  <pre className="log-message">{entry.message}</pre>
                </td>
              </tr>
            ))}
            {entries.length === 0 && (
              <tr>
                <td colSpan={4}>Nothing logged matching this filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default LogsPage
