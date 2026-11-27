// The read-only crew view (/jobs/:id/view) is authenticated by a share token in the URL, never
// by a user session. Both the router guard and the api boot's "session expired -> go to login"
// redirect must agree on what counts as that view, otherwise a stale user session left in
// localStorage (expired access token + dead refresh cookie) makes the startup refresh fail and
// bounce a crew member to /login the first time they open the link.
export function isShareViewPath(path) {
  return typeof path === 'string' && path.startsWith('/jobs/') && path.endsWith('/view')
}

// The app may run in hash mode (`/#/jobs/1/view?token=…`) or history mode (`/jobs/1/view?…`),
// so resolve the route path from the hash when it carries one, else from the pathname.
export function isShareViewLocation(loc) {
  const hash = loc.hash || ''
  const route = hash.startsWith('#/') ? hash.slice(1) : loc.pathname || ''
  return isShareViewPath(route.split('?')[0])
}
