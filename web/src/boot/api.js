import axios from 'axios'
import { getApiBaseUrl } from '../utils/runtime-config'
import { useAuthStore } from '../stores/auth'

const baseURL = getApiBaseUrl() + '/api/v1'

const api = axios.create({
  baseURL,
  headers: { Accept: 'application/json' },
})

let isRefreshing = false
let refreshPromise = null
let proactiveRefreshTimer = null

// Refresh the access token this many seconds before it actually expires, so a
// request is never sent with a token the backend has already rejected.
const REFRESH_BUFFER_SECONDS = 60

function decodeJwtPayload(token) {
  if (!token) return null
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const json = atob(base64)
    return JSON.parse(json)
  } catch {
    return null
  }
}

function getAccessTokenExpiry(token) {
  const payload = decodeJwtPayload(token)
  if (!payload || !payload.exp) return null
  return payload.exp * 1000
}

function msUntilExpiry(expiryMs) {
  if (!expiryMs) return null
  return expiryMs - Date.now()
}

function clearSession() {
  const auth = useAuthStore()
  auth.logout()
}

function redirectToLogin() {
  const hash = window.location.hash || ''
  // Avoid bouncing if we are already on an auth screen.
  if (hash.startsWith('#/login') || hash.startsWith('#/setup')) return
  const currentPath = window.location.pathname + window.location.search + hash
  window.location.assign(`/#/login?reason=expired&redirect=${encodeURIComponent(currentPath)}`)
}

async function refreshAccessToken() {
  // The refresh token lives in the httpOnly cookie the backend sets (path
  // /api/v1/auth). We just send the request with credentials so the browser
  // attaches it; it is never read from JS or localStorage.
  if (isRefreshing && refreshPromise) {
    return refreshPromise
  }
  isRefreshing = true
  refreshPromise = api
    .post('/auth/refresh', null, { withCredentials: true })
    .then(({ data }) => {
      const auth = useAuthStore()
      auth.setRefreshedTokens(data)
      api.defaults.headers.common['Authorization'] = `Bearer ${data.access_token}`
      return data.access_token
    })
    .catch((refreshError) => {
      clearSession()
      if (typeof window !== 'undefined') redirectToLogin()
      throw refreshError
    })
    .finally(() => {
      isRefreshing = false
      refreshPromise = null
    })
  return refreshPromise
}

function scheduleProactiveRefresh() {
  if (proactiveRefreshTimer) {
    clearTimeout(proactiveRefreshTimer)
    proactiveRefreshTimer = null
  }
  const token = localStorage.getItem('sw_access_token')
  if (!token) return
  const msLeft = msUntilExpiry(getAccessTokenExpiry(token))
  if (msLeft == null) return
  // Refresh just before expiry so the next request already has a fresh token.
  const refreshIn = Math.max(1000, msLeft - REFRESH_BUFFER_SECONDS * 1000)
  proactiveRefreshTimer = setTimeout(() => {
    refreshAccessToken().catch(() => {})
  }, refreshIn)
}

function setupProactiveRefresh() {
  if (typeof window === 'undefined') return

  // On startup, refresh immediately if the access token is already expired or
  // about to be; otherwise schedule a proactive refresh before it lapses.
  const token = localStorage.getItem('sw_access_token')
  if (token) {
    const msLeft = msUntilExpiry(getAccessTokenExpiry(token))
    if (msLeft == null || msLeft <= REFRESH_BUFFER_SECONDS * 1000) {
      refreshAccessToken().catch(() => {})
    } else {
      scheduleProactiveRefresh()
    }
  }

  // When the PWA/tab is brought back to the foreground after being backgrounded
  // (common on mobile), the access token may have expired silently — refresh it
  // then too, which is what keeps users from having to log in all the time.
  const onVisible = () => {
    if (document.visibilityState !== 'visible') return
    const t = localStorage.getItem('sw_access_token')
    if (!t) return
    const msLeft = msUntilExpiry(getAccessTokenExpiry(t))
    if (msLeft == null || msLeft <= REFRESH_BUFFER_SECONDS * 1000) {
      refreshAccessToken().catch(() => {})
    }
  }
  document.addEventListener('visibilitychange', onVisible)
}

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('sw_access_token')
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error.response?.status
    const url = String(error?.config?.url || '')
    // Never auto-refresh on auth endpoints: a 401 there means bad credentials or
    // an already-expired session, not a stale access token we can refresh.
    if (status === 401 && !url.startsWith('/auth/')) {
      const original = error.config
      if (original._retry) {
        clearSession()
        if (typeof window !== 'undefined') redirectToLogin()
        return Promise.reject(error)
      }
      original._retry = true
      try {
        const newToken = await refreshAccessToken()
        original.headers.Authorization = `Bearer ${newToken}`
        return api(original)
      } catch {
        return Promise.reject(error)
      }
    }
    return Promise.reject(error)
  },
)

export { api, refreshAccessToken, scheduleProactiveRefresh }

export default ({ app }) => {
  setupProactiveRefresh()
  app.config.globalProperties.$api = api
}
