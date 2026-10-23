import { Quasar } from 'quasar'
import quasarEn from 'quasar/lang/en-GB'
import quasarSv from 'quasar/lang/sv'
import { i18n, onLocaleChange, resolveAppLocale, setLocale, applyLocale } from '../i18n'
import { api } from './api'
import { useAuthStore } from '@/stores/auth'

// Pre-load Quasar language packs for the supported locales so component strings
// (e.g. q-table footer) are available synchronously and update immediately when
// the locale changes.
const QUASAR_LANGS = {
  en: quasarEn,
  sv: quasarSv,
}

function applyQuasarLang(locale) {
  const base = String(locale || 'en').toLowerCase().split(/[-_]/)[0]
  const lang = QUASAR_LANGS[base] || QUASAR_LANGS.en
  Quasar.lang.set(lang)
}

export default async ({ app }) => {
  app.use(i18n)
  const initial = localStorage.getItem('sw_locale') || resolveAppLocale(null)
  setLocale(initial)
  applyQuasarLang(initial)
  onLocaleChange(applyQuasarLang)

  const auth = useAuthStore()
  await auth.fetchMe()
  if (auth.user) setLocale(resolveAppLocale(auth.user.id))

  try {
    const { data } = await api.get('/settings/company')
    if (data && data.default_language) {
      localStorage.setItem('sw_company_default_language', String(data.default_language))
      if (!localStorage.getItem('sw_locale')) setLocale(resolveAppLocale(auth.user?.id ?? null))
    }
  } catch {
    /* company settings are optional */
  }

  window.addEventListener('storage', (e) => {
    if (e.key === 'sw_locale' && e.newValue) applyLocale(e.newValue)
  })
}
