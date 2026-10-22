import { defineStore } from 'pinia'
import { api } from 'boot/api'
import { setLocale, setUserLocalePreference } from '../i18n'

const TOKEN_KEY = 'sw_access_token'
const REFRESH_KEY = 'sw_refresh_token'
const USER_KEY = 'sw_user'

function readUser() {
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || null,
    refreshToken: localStorage.getItem(REFRESH_KEY) || null,
    user: readUser(),
    loading: false,
    error: null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
  },
  actions: {
    persist() {
      if (this.token) localStorage.setItem(TOKEN_KEY, this.token)
      else localStorage.removeItem(TOKEN_KEY)
      if (this.refreshToken) localStorage.setItem(REFRESH_KEY, this.refreshToken)
      else localStorage.removeItem(REFRESH_KEY)
      if (this.user) localStorage.setItem(USER_KEY, JSON.stringify(this.user))
      else localStorage.removeItem(USER_KEY)
    },
    async login(email, password) {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.post('/auth/login', { email, password })
        this.token = data.access_token
        this.refreshToken = data.refresh_token
        this.user = data.user
        this.persist()
        return data
      } catch (err) {
        this.error = err.response?.data?.detail || 'Login failed'
        throw err
      } finally {
        this.loading = false
      }
    },
    async setup(payload) {
      this.loading = true
      this.error = null
      try {
        const { data } = await api.post('/auth/setup', payload)
        this.token = data.access_token
        this.refreshToken = data.refresh_token
        this.user = data.user
        this.persist()
        return data
      } catch (err) {
        this.error = err.response?.data?.detail || 'Setup failed'
        throw err
      } finally {
        this.loading = false
      }
    },
    setSession(data) {
      this.token = data.access_token
      this.refreshToken = data.refresh_token
      this.user = data.user
      this.persist()
      const lang = data.user?.preferred_language
      if (lang) {
        setUserLocalePreference(this.user.id, lang)
        setLocale(lang)
      }
      return data
    },
    async setLanguage(lang) {
      const normalized = setUserLocalePreference(this.user?.id, lang)
      setLocale(normalized)
      if (this.user) this.user.preferred_language = normalized
      if (this.user?.id) {
        try {
          await api.put(`/auth/users/${this.user.id}`, {
            preferred_language: normalized,
          })
        } catch {
          /* ignore */
        }
      }
    },
    async fetchMe() {
      if (!this.token) return null
      try {
        const { data } = await api.get('/auth/me')
        this.user = data
        this.persist()
        const lang = data.preferred_language
        if (lang) {
          setUserLocalePreference(data.id, lang)
          setLocale(lang)
        }
        return data
      } catch {
        return null
      }
    },
    async refresh() {
      if (!this.refreshToken) return false
      try {
        const resp = await api.post('/auth/refresh', null, {
          headers: { 'X-Refresh-Token': this.refreshToken },
        })
        this.token = resp.data.access_token
        this.refreshToken = resp.data.refresh_token
        this.user = resp.data.user
        this.persist()
        return true
      } catch {
        this.logout()
        return false
      }
    },
    logout() {
      this.token = null
      this.refreshToken = null
      this.user = null
      this.persist()
    },
  },
})
