import { defineStore } from 'pinia';
import { api } from '@/boot/api';
import { isScopedWrite, nextRedo, nextUndo } from '@/utils/history';

// Undo / redo / version history of the job or venue that is open. The server records every write;
// this store keeps the list in step: after every successful write the user makes (seen through an
// axios interceptor, so every editor is covered without wiring) and after realtime
// `history.restore` events from other tabs / users.
let interceptor = null;
let timer = null;

export const useHistoryStore = defineStore('history', {
  state: () => ({
    kind: 'job',
    scopeId: null,
    cursor: 0,
    canUndo: false,
    canRedo: false,
    entries: [],
    loading: false,
    busy: false,
  }),
  getters: {
    undoEntry: (s) => nextUndo(s.entries),
    redoEntry: (s) => nextRedo(s.entries),
    base: (s) => `/${s.kind === 'venue' ? 'venues' : 'jobs'}/${s.scopeId}/history`,
  },
  actions: {
    setScope(kind, id) {
      if (this.kind === kind && this.scopeId === id) return;
      Object.assign(this, { kind, scopeId: id, cursor: 0, canUndo: false, canRedo: false, entries: [] });
      this.watchWrites();
    },
    // one interceptor for the app: a successful write inside the open scope refreshes the list
    watchWrites() {
      if (interceptor !== null) return;
      interceptor = api.interceptors.response.use((res) => {
        if (this.scopeId && isScopedWrite(res.config, res.status, this.kind, this.scopeId)) this.scheduleRefresh();
        return res;
      });
    },
    scheduleRefresh(delay = 500) {
      clearTimeout(timer);
      timer = setTimeout(() => this.refresh(), delay);
    },
    apply(data) {
      this.cursor = data.cursor;
      this.canUndo = data.can_undo;
      this.canRedo = data.can_redo;
      this.entries = data.entries;
    },
    async refresh() {
      if (!this.scopeId) return;
      this.loading = true;
      try {
        const { data } = await api.get(this.base, { params: { limit: 100 } });
        this.apply(data);
      } catch {
        /* the controls simply stay as they were */
      } finally {
        this.loading = false;
      }
    },
    async step(direction, force = false) {
      this.busy = true;
      try {
        const { data } = await api.post(`${this.base}/${direction}`, null, { params: force ? { force: true } : {} });
        this.apply(data);
        return data;
      } finally {
        this.busy = false;
      }
    },
    undo(force = false) {
      return this.step('undo', force);
    },
    redo(force = false) {
      return this.step('redo', force);
    },
    async restore(seq, force = false) {
      this.busy = true;
      try {
        const { data } = await api.post(`${this.base}/restore`, { seq }, { params: force ? { force: true } : {} });
        this.apply(data);
        return data;
      } finally {
        this.busy = false;
      }
    },
  },
});
