function trimTrailingSlash(value) {
  return String(value || '').replace(/\/$/, '')
}

export function getRuntimeConfig() {
  return window.__APP_CONFIG__ || {}
}

export function getApiBaseUrl() {
  const runtimeConfig = getRuntimeConfig()
  const runtimeValue = trimTrailingSlash(
    runtimeConfig.API_BASE_URL || runtimeConfig.apiBaseUrl,
  )
  if (runtimeValue) return runtimeValue

  const builtValue = trimTrailingSlash(process.env.API_BASE_URL || '')
  if (builtValue) return builtValue

  return trimTrailingSlash(window.location.origin)
}
