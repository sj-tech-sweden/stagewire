const routes = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('@/pages/IndexPage.vue') },
      // The workspace is the job page. /workspace is kept as an alias, and the URLs of the old
      // pages (stage plot, patch sheets, devices, lights, video) open the matching workspace mode,
      // so bookmarks and links in exported reports keep working.
      {
        path: 'jobs/:jobId',
        alias: 'jobs/:jobId/workspace',
        component: () => import('@/pages/JobWorkspacePage.vue'),
      },
      ...Object.entries({
        'stage-plot': 'canvas',
        'patch-sheets': 'lists',
        devices: 'devices',
        lights: 'lights',
        video: 'video',
      }).map(([segment, view]) => ({
        path: `jobs/:jobId/${segment}`,
        redirect: (to) => ({ path: `/jobs/${to.params.jobId}`, query: { view } }),
      })),
      { path: 'reports', component: () => import('@/pages/ReportsPage.vue') },
      { path: 'venues', component: () => import('@/pages/VenuesPage.vue') },
      {
        path: 'venues/:venueId/base-rig',
        component: () => import('@/pages/VenueBaseRigPage.vue'),
      },
      { path: 'settings', component: () => import('@/pages/SettingsPage.vue') },
    ],
  },
  { path: '/login', component: () => import('@/pages/LoginPage.vue') },
  { path: '/setup', component: () => import('@/pages/SetupPage.vue') },
  // Read-only, login-free day-of-show crew view. Lives outside MainLayout on purpose: it
  // carries no user session and must never trigger the "redirect to login" guard.
  { path: '/jobs/:jobId/view', component: () => import('@/pages/JobShareViewPage.vue') },
  { path: '/:catchAll(.*)*', component: () => import('@/pages/ErrorNotFound.vue') },
];

export default routes;
