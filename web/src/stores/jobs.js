import { defineStore } from 'pinia';
import { api } from '@/boot/api';

export const PAGE_SIZE = 50;

export const useJobsStore = defineStore('jobs', {
  state: () => ({
    jobs: [],
    total: 0,
    search: '',
    loading: false,
    error: null,
  }),
  getters: {
    hasMore: (state) => state.jobs.length < state.total,
  },
  actions: {
    // The newest jobs first, a page at a time; `search` filters on title, venue and Stockwire id on
    // the server, so the list stays quick with thousands of jobs.
    async fetchJobs({ search = this.search, more = false } = {}) {
      this.loading = true;
      this.error = null;
      try {
        const { data, headers } = await api.get('/jobs', {
          params: {
            search: search || undefined,
            newest_first: true,
            skip: more ? this.jobs.length : 0,
            limit: PAGE_SIZE,
          },
        });
        this.search = search;
        this.jobs = more ? [...this.jobs, ...data] : data;
        this.total = Number(headers['x-total-count'] ?? this.jobs.length);
      } catch (err) {
        this.error = err.message || 'Failed to load jobs';
      } finally {
        this.loading = false;
      }
    },
    loadMore() {
      return this.fetchJobs({ more: true });
    },
    async createJob(payload) {
      const { data } = await api.post('/jobs', payload);
      return data;
    },
  },
});
