import { useAuthStore } from '../stores/auth'
import { scheduleProactiveRefresh } from './api'

// The SAML ACS endpoint (`/api/v1/auth/sso/saml/acs`) finishes the IdP POST and
// then 302-redirects back to the frontend with the issued tokens in the URL
// fragment, e.g. `/#access_token=...&refresh_token=...`. The refresh token is also
// delivered as an httpOnly cookie (the source of truth), so we only need the access
// token here. The history-mode router would otherwise treat the fragment as a route
// and render nothing, so consume it, hydrate the user via /auth/me, then clear the
// fragment so a real route is resolved.
export default async function ({ app }) {
  const hash = window.location.hash || ''
  if (!hash.includes('access_token=')) return

  const params = new URLSearchParams(hash.slice(1))
  const accessToken = params.get('access_token')
  if (!accessToken) return

  const auth = useAuthStore()
  auth.setRefreshedTokens({ access_token: accessToken })
  try {
    await auth.fetchMe()
  } catch {
    // Token already consumed the fragment; bail to the login screen.
    auth.logout()
    window.history.replaceState(null, '', window.location.pathname + window.location.search)
    return
  }

  // Drop the tokens from the URL bar. The route is already the intended page (the
  // backend defaults the post-login path to "/"), so nothing else needs to change.
  window.history.replaceState(null, '', window.location.pathname + window.location.search)
  // Mirror the proactive-refresh schedule the api boot set up at startup (it ran
  // before this token existed, so re-arm it now that we have a valid session).
  scheduleProactiveRefresh()
}
