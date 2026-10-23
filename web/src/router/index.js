import { route } from 'quasar/wrappers';
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router';
import { api } from '@/boot/api';
import routes from './routes';

export default route(function (/* ctx */) {
  const createHistory = import.meta.env.QUASAR_SERVER
    ? createMemoryHistory
    : import.meta.env.QUASAR_VUE_ROUTER_MODE === 'history'
      ? createWebHistory
      : createWebHashHistory;

  const Router = createRouter({
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes,
    history: createHistory(import.meta.env.QUASAR_VUE_ROUTER_BASE),
  });

  Router.beforeEach(async (to) => {
    const token = localStorage.getItem('sw_access_token')
    const publicRoutes = ['/login', '/setup']

    if (publicRoutes.includes(to.path)) {
      return true
    }

    if (!token) {
      try {
        const { data } = await api.get('/auth/bootstrap-status')
        if (data.setup_needed) {
          return { path: '/setup' }
        }
      } catch {
        /* backend unreachable; send to login */
      }
      return { path: '/login' }
    }

    if (to.path === '/') {
      try {
        const { data } = await api.get('/auth/bootstrap-status')
        if (data.setup_needed) {
          return { path: '/setup' }
        }
      } catch {
        /* backend unreachable; allow through */
      }
    }

    return true
  });

  return Router;
});
