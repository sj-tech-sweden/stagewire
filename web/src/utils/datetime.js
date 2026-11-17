// Fixed, locale-independent date/time formatting for read-only displays.
//
// The date picker edits values as local time ('YYYY-MM-DDTHH:mm', no zone), so we format
// read-only views the same way (local components) rather than letting Intl pick the browser
// locale. That keeps the rendered date identical to what was entered and avoids the day
// shifting in another timezone. It also honours the product decision to show dates as
// YYYY-MM-DD (HH:mm, 24h) everywhere except the picker itself.

function pad(n) {
  return String(n).padStart(2, '0')
}

export function formatDateTime(value) {
  if (!value) return ''
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return ''
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())} ${pad(dt.getHours())}:${pad(dt.getMinutes())}`
}

export function formatDateOnly(value) {
  if (!value) return ''
  const dt = new Date(value)
  if (Number.isNaN(dt.getTime())) return ''
  return `${dt.getFullYear()}-${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`
}
