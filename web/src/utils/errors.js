// Text for an error from the API, for a notification. The API answers with `detail` as a string,
// as an object ({ message } or { issues: [...] } for connection checks), or, for a request the
// validation refused (422), as a list of { msg, loc } entries; anything else (offline, a crash)
// falls back to the error's own message or the given text, never an object dump.
export function apiErrorText(err, fallback = 'Something went wrong') {
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((d) => d?.msg || d?.message).filter(Boolean);
    if (parts.length) return parts.join('; ');
  }
  if (detail && typeof detail === 'object') {
    if (detail.message) return detail.message;
    if (Array.isArray(detail.issues)) {
      const parts = detail.issues.map((i) => i.message).filter(Boolean);
      if (parts.length) return parts.join('; ');
    }
  }
  if (err?.response?.status === 502) return 'Stockwire could not be reached right now';
  return err?.message || fallback;
}
