import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getBanner, updateBanner } from '../api/client.js'

// Root-admin screen for the site-wide notice (components/Banner.jsx
// renders it). Saving anything here makes the banner reappear for every
// user who had dismissed the previous version -- see that component for
// why.
const COLOURS = [
  { value: 'blue', label: 'Blue (information)' },
  { value: 'green', label: 'Green (all clear)' },
  { value: 'amber', label: 'Amber (warning)' },
  { value: 'red', label: 'Red (urgent)' },
]

function BannerPage() {
  const [message, setMessage] = useState('')
  const [colour, setColour] = useState('blue')
  const [isActive, setIsActive] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    getBanner()
      .then((banner) => {
        setMessage(banner.message)
        setColour(banner.colour)
        setIsActive(banner.is_active)
      })
      .catch((err) => setError(err.message))
  }, [])

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSaved(false)
    try {
      await updateBanner(message, colour, isActive)
      setSaved(true)
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div>
      <p>
        <Link to="/admin">&larr; Admin</Link>
      </p>
      <h2>Site banner</h2>
      <p className="form-hint">
        Shown at the top of every page to all logged-in users. Each user can dismiss it; saving any
        change here makes it reappear for everyone.
      </p>

      <form onSubmit={handleSubmit} className="banner-form">
        <label>
          Message
          <textarea
            rows={3}
            maxLength={500}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="e.g. Planned maintenance Friday 18:00-20:00"
          />
        </label>
        <label>
          Colour{' '}
          <select value={colour} onChange={(e) => setColour(e.target.value)}>
            {COLOURS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="banner-form-check">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
          />{' '}
          Show this banner
        </label>
        <button type="submit">Save banner</button>
      </form>

      {/* Live preview, so the colour choice is a decision rather than a
          guess -- uses the same classes the real banner does. */}
      {message.trim() && (
        <>
          <h3>Preview</h3>
          <div className={`banner banner-${colour}`}>
            <span className="banner-message">{message}</span>
            <button type="button" className="banner-close" title="Dismiss">
              &times;
            </button>
          </div>
        </>
      )}

      {saved && <p className="form-hint">Saved.</p>}
      {error && <p className="form-error">{error}</p>}
    </div>
  )
}

export default BannerPage
