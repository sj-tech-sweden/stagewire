import { defineStore } from 'pinia';
import { api } from '@/boot/api';

export const useJobsStore = defineStore('jobs', {
  state: () => ({
    jobs: [],
    loading: false,
    error: null,
  }),
  actions: {
    async fetchJobs() {
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get('/jobs');
        this.jobs = data;
      } catch (err) {
        this.error = err.message || 'Failed to load jobs';
      } finally {
        this.loading = false;
      }
    },
    async createJob(payload) {
      const { data } = await api.post('/jobs', payload);
      this.jobs.push(data);
      return data;
    },
  },
});
