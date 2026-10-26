const routes = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      { path: '', component: () => import('@/pages/IndexPage.vue') },
      { path: 'jobs/:jobId', component: () => import('@/pages/JobDetailPage.vue') },
      { path: 'jobs/:jobId/patch-sheets', component: () => import('@/pages/PatchSheetsPage.vue') },
      { path: 'jobs/:jobId/stage-plot', component: () => import('@/pages/StagePlotPage.vue') },
      { path: 'jobs/:jobId/devices', component: () => import('@/pages/DevicesPage.vue') },
      { path: 'jobs/:jobId/video', component: () => import('@/pages/VideoPage.vue') },
      { path: 'reports', component: () => import('@/pages/ReportsPage.vue') },
      { path: 'venues', component: () => import('@/pages/VenuesPage.vue') },
      { path: 'settings', component: () => import('@/pages/SettingsPage.vue') },
    ],
  },
  { path: '/login', component: () => import('@/pages/LoginPage.vue') },
  { path: '/setup', component: () => import('@/pages/SetupPage.vue') },
  { path: '/:catchAll(.*)*', component: () => import('@/pages/ErrorNotFound.vue') },
];

export default routes;
