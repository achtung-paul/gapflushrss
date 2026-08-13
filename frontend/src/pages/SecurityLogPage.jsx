import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listSecurityEvents } from '../api/client.js'

// Root-admin view of the security_events audit trail (backend
// api/security_events.py) -- login/logout/failed-login, permission
// changes, user/client lifecycle, data deletion, and Excel exports, kept
// for 360 days (models/security_event.py). See that model's header
// comment for why root_admin reading this is a deliberate, narrow
// exception to the app's usual tenancy boundary: it's the one place
// root_admin can see across every client, built specifically so a
// security incident can actually be traced (who logged in, from where,
// what they touched).
//
// Unlike LogsPage.jsx (which tails plain files and polls every 5s),
// this is a real database table with real pagination -- so this page is
// a manual-refresh investigation tool, not a live tail.

const CATEGORIES = [
  { value: 'all', label: 'All categories' },
  { value: 'auth', label: 'Authentication' },
  { value: 'user', label: 'Users' },
  { value: 'client', label: 'Clients' },
  { value: 'project', label: 'Projects' },
  { value: 'system', label: 'System' },
  { value: 'data', label: 'Data deletion' },
  { value: 'export', label: 'Exports' },
]

const OUTCOMES = [
  { value: 'all', label: 'All outcomes' },
  { value: 'failure', label: 'Failures only' },
  { value: 'success', label: 'Successes only' },
]

const PAGE_SIZE = 50

function SecurityLogPage() {
  const [entries, setEntries] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [category, setCategory] = useState('all')
  const [outcome, setOutcome] = useState('all')
  const [actorEmailInput, setActorEmailInput] = useState('')
  const [actorEmail, setActorEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  function refresh() {
    setLoading(true)
    setError(null)
    listSecurityEvents({ category, outcome, actorEmail, page, pageSize: PAGE_SIZE })
      .then((result) => {
        setEntries(result.entries)
        setTotal(result.total)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }

  useEffect(refresh, [category, outcome, actorEmail, page])

  // Debounce the email search box, same pattern as AdminPage.jsx's user
  // search -- wait for a pause before querying, and reset to page 1
  // since the old page number may no longer make sense.
  useEffect(() => {
    const timeoutId = setTimeout(() => {
      setActorEmail(actorEmailInput)
      setPage(1)
    }, 300)
    return () => clearTimeout(timeoutId)
  }, [actorEmailInput])

  function handleCategoryChange(value) {
    setCategory(value)
    setPage(1)
  }

  function handleOutcomeChange(value) {
    setOutcome(value)
    setPage(1)
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div>
      <p>
        <Link to="/admin">&larr; Admin</Link>
      </p>
      <h2>Security log</h2>
      <p className="form-hint">
        Logins, permission changes, user and client lifecycle, data deletion, and exports across every
        client -- kept for 360 days. Root admin only; see CLAUDE.md's tenancy-boundary gotcha for why this
        page is the one deliberate exception.
      </p>

      <div className="inline-form">
        <label>
          Category{' '}
          <select value={category} onChange={(e) => handleCategoryChange(e.target.value)}>
            {CATEGORIES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Outcome{' '}
          <select value={outcome} onChange={(e) => handleOutcomeChange(e.target.value)}>
            {OUTCOMES.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Actor email{' '}
          <input
            type="search"
            placeholder="Search by email..."
            value={actorEmailInput}
            onChange={(e) => setActorEmailInput(e.target.value)}
          />
        </label>
        <button type="button" onClick={refresh} disabled={loading}>
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="section-divider" />

      <div className="analysis-table-scroll">
        <table className="analysis-table log-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Event</th>
              <th>Outcome</th>
              <th>Actor</th>
              <th>Client</th>
              <th>Source IP</th>
              <th>Target</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.event_id}>
                <td className="log-time">{new Date(entry.occurred_at).toLocaleString()}</td>
                <td>{entry.event_type}</td>
                <td>
                  <span className={`rag-badge ${entry.outcome === 'failure' ? 'rag-red' : ''}`}>
                    {entry.outcome}
                  </span>
                </td>
                <td>
                  {entry.actor_name || entry.actor_email ? (
                    <>
                      {entry.actor_name}
                      {entry.actor_name && entry.actor_email ? ' · ' : ''}
                      {entry.actor_email}
                    </>
                  ) : (
                    '—'
                  )}
                </td>
                <td>{entry.client_name || '—'}</td>
                <td>{entry.source_ip || '—'}</td>
                <td>
                  {entry.target_type ? `${entry.target_type}: ${entry.target_name || entry.target_id}` : '—'}
                </td>
                <td>{entry.detail || '—'}</td>
              </tr>
            ))}
            {entries.length === 0 && !loading && (
              <tr>
                <td colSpan={8}>No events matching this filter.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {total > PAGE_SIZE && (
        <nav className="pagination-breadcrumb">
          <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>
            &larr; Prev
          </button>
          <span className="form-hint">
            Page {page} of {totalPages} ({total} events)
          </span>
          <button type="button" disabled={page >= totalPages} onClick={() => setPage(page + 1)}>
            Next &rarr;
          </button>
        </nav>
      )}
    </div>
  )
}

export default SecurityLogPage
