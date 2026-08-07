import { useEffect, useState } from 'react'
import { getBanner } from '../api/client.js'
import { useAuth } from '../auth/AuthContext.jsx'

// The admin-set site-wide notice, shown above every page.
//
// Dismissal is stored in localStorage against the banner's updated_at
// rather than server-side. That keeps it to zero extra requests and no
// schema, and it makes the important behaviour fall out for free: any
// change an admin makes moves updated_at, so the stored value no longer
// matches and the banner reappears for everyone who had closed the old
// one. The trade-off is that dismissal is per browser, so the same person
// sees it again on another device -- acceptable for a notice.
const DISMISSED_KEY = 'gapflush_banner_dismissed'

function Banner() {
  const { user } = useAuth()
  const [banner, setBanner] = useState(null)
  const [dismissedAt, setDismissedAt] = useState(() => localStorage.getItem(DISMISSED_KEY))

  useEffect(() => {
    // Only logged-in users see it, and /banner requires authentication --
    // fetching while logged out would just 401 on every page load.
    if (!user) {
      setBanner(null)
      return
    }
    getBanner()
      .then(setBanner)
      // A failure here must not break the page it sits above; the banner
      // is the least important thing on screen.
      .catch(() => setBanner(null))
  }, [user])

  if (!user || !banner || !banner.is_active || !banner.message) {
    return null
  }
  if (dismissedAt === banner.updated_at) {
    return null
  }

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, banner.updated_at)
    setDismissedAt(banner.updated_at)
  }

  return (
    <div className={`banner banner-${banner.colour}`} role="status">
      <span className="banner-message">{banner.message}</span>
      <button type="button" className="banner-close" title="Dismiss" onClick={dismiss}>
        &times;
      </button>
    </div>
  )
}

export default Banner
