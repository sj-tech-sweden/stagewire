import axios from 'axios'
import { getApiBaseUrl } from '../utils/runtime-config'

const baseURL = getApiBaseUrl() + '/api/v1'

const api = axios.create({
  baseURL,
  headers: { Accept: 'application/json' },
})

let isRefreshing = false
let pendingSubscribers = []

function subscribeTokenRefresh(cb) {
  pendingSubscribers.push(cb)
}

function onRefreshed(token) {
  pendingSubscribers.forEach((cb) => cb(token))
  pendingSubscribers = []
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
    const original = error.config
    const status = error.response?.status

    if (status === 401 && !original._retry) {
      const refreshToken = localStorage.getItem('sw_refresh_token')
      if (refreshToken && !isRefreshing) {
        original._retry = true
        isRefreshing = true
        try {
          const resp = await axios.post(
            `${baseURL}/auth/refresh`,
            null,
            { headers: { 'X-Refresh-Token': refreshToken } },
          )
          const { access_token: access, refresh_token: refresh, user } = resp.data
          localStorage.setItem('sw_access_token', access)
          localStorage.setItem('sw_refresh_token', refresh)
          if (user) localStorage.setItem('sw_user', JSON.stringify(user))
          isRefreshing = false
          onRefreshed(access)
          original.headers.Authorization = `Bearer ${access}`
          return api(original)
        } catch {
          isRefreshing = false
          onRefreshed(null)
          localStorage.removeItem('sw_access_token')
          localStorage.removeItem('sw_refresh_token')
          localStorage.removeItem('sw_user')
          if (typeof window !== 'undefined') window.location.assign('/#/login')
          return Promise.reject(error)
        }
      }
    }

    if (status === 401 && original._retry) {
      localStorage.removeItem('sw_access_token')
      localStorage.removeItem('sw_refresh_token')
      localStorage.removeItem('sw_user')
      if (typeof window !== 'undefined') window.location.assign('/#/login')
    }

    return Promise.reject(error)
  },
)

export { api }

export default ({ app }) => {
  app.config.globalProperties.$api = api
}
