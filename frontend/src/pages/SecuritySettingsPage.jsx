import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getSecuritySettings, updateSecuritySettings } from '../api/client.js'

// Root-admin screen for the one system-wide 2FA toggle (see
// models/security_setting.py). Off by default; turning it on demands
// enrollment from every user (including root_admin) at their next
// login -- no grace period. Turning it off is the direction that needs
// a stronger confirmation (it silently drops every account to
// single-factor), same reasoning as ClientsPage.jsx's typed-name purge
// confirm -- but turning it *on* locks nobody out, so it saves
// immediately with no extra step.
function SecuritySettingsPage() {
  const [require2fa, setRequire2fa] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  const [pendingDisable, setPendingDisable] = useState(false)

  function refresh() {
    getSecuritySettings()
      .then((row) => {
        setRequire2fa(row.require_2fa)
        setLoaded(true)
      })
      .catch((err) => setError(err.message))
  }

  useEffect(refresh, [])

  async function save(nextValue) {
    setError(null)
    setSaved(false)
    try {
      await updateSecuritySettings(nextValue)
      setRequire2fa(nextValue)
      setSaved(true)
      setPendingDisable(false)
    } catch (err) {
      setError(err.message)
    }
  }

  function handleToggle(event) {
    const nextValue = event.target.checked
    if (!nextValue) {
      // Turning it off -- confirm first (see file comment above).
      setPendingDisable(true)
      return
    }
    save(true)
  }

  if (!loaded) {
    return <p>Loading...</p>
  }

  return (
    <div>
      <p>
        <Link to="/admin">&larr; Admin</Link>
      </p>
      <h2>Two-factor authentication</h2>
      <p className="form-hint">
        When required, every user (including root admins) must set up an authenticator app the
        next time they log in, and enter a code from it on every login after that. There is no
        per-client exemption.
      </p>

      <label className="banner-form-check">
        <input type="checkbox" checked={require2fa} onChange={handleToggle} disabled={pendingDisable} />{' '}
        Require two-factor authentication for every user
      </label>

      {pendingDisable && (
        <p>
          Turning this off removes the 2FA requirement for every user immediately. Already-enrolled
          accounts keep their authenticator but won&apos;t be asked for a code until it&apos;s
          turned back on.{' '}
          <button type="button" onClick={() => save(false)}>
            Yes, turn off
          </button>{' '}
          <button type="button" onClick={() => setPendingDisable(false)}>
            Cancel
          </button>
        </p>
      )}

      {saved && <p className="form-hint">Saved.</p>}
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default SecuritySettingsPage
