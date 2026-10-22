import { createI18n } from 'vue-i18n'
import en from './locales/en.js'
import sv from './locales/sv.js'

const messages = { en, sv }
const SUPPORTED_LOCALES = ['en', 'sv']

function normalizeLocale(raw) {
  const value = String(raw || '').trim().toLowerCase()
  if (!value) return 'en'
  const base = value.split(/[-_]/)[0]
  if (SUPPORTED_LOCALES.includes(base)) return base
  if (SUPPORTED_LOCALES.includes(value)) return value
  return 'en'
}

export function getBrowserLocale() {
  const lang = navigator?.language || navigator?.languages?.[0] || ''
  const value = String(lang || '').trim().toLowerCase()
  if (!value) return null
  const base = value.split(/[-_]/)[0]
  return SUPPORTED_LOCALES.includes(base) ? base : null
}

export function getCompanyDefaultLocale() {
  const stored = localStorage.getItem('sw_company_default_language') || ''
  return normalizeLocale(stored)
}

export function getUserLocalePreference(userId) {
  if (!userId) return null
  const key = `sw_user_locale_${userId}`
  const stored = String(localStorage.getItem(key) || '').trim().toLowerCase()
  if (!stored) return null
  const base = stored.split(/[-_]/)[0]
  return SUPPORTED_LOCALES.includes(base) ? base : null
}

export function setUserLocalePreference(userId, locale) {
  const normalized = normalizeLocale(locale)
  const key = userId ? `sw_user_locale_${userId}` : 'sw_user_locale'
  localStorage.setItem(key, normalized)
  localStorage.setItem('sw_locale', normalized)
  return normalized
}

export function resolveAppLocale(userId) {
  return getUserLocalePreference(userId) || getBrowserLocale() || getCompanyDefaultLocale() || 'en'
}

export function resolveLoginLocale(companyDefault) {
  const browser = getBrowserLocale()
  if (browser) return browser
  return normalizeLocale(companyDefault)
}

export const i18n = createI18n({
  legacy: false,
  locale: normalizeLocale(localStorage.getItem('sw_locale') || 'en'),
  fallbackLocale: 'en',
  messages,
})

const localeChangeListeners = new Set()

export function onLocaleChange(listener) {
  localeChangeListeners.add(listener)
  return () => localeChangeListeners.delete(listener)
}

export function setLocale(locale) {
  const normalized = normalizeLocale(locale)
  i18n.global.locale.value = normalized
  localStorage.setItem('sw_locale', normalized)
  if (typeof document !== 'undefined') {
    document.documentElement.lang = normalized
  }
  localeChangeListeners.forEach(fn => fn(normalized))
  return normalized
}

export function applyLocale(locale) {
  const normalized = normalizeLocale(locale)
  if (i18n.global.locale.value !== normalized) {
    i18n.global.locale.value = normalized
  }
  if (typeof document !== 'undefined') {
    document.documentElement.lang = normalized
  }
  localeChangeListeners.forEach(fn => fn(normalized))
  return normalized
}

export { SUPPORTED_LOCALES, messages }
