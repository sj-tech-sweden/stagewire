import { defineStore } from 'pinia';
import { api } from '@/boot/api';

export const useStagePlotStore = defineStore('stageplot', {
  state: () => ({
    elements: [],
    loading: false,
    error: null,
  }),
  actions: {
    async fetchElements(jobId) {
      this.loading = true;
      this.error = null;
      try {
        const { data } = await api.get(`/jobs/${jobId}/plot-elements`);
        this.elements = data;
      } catch (err) {
        this.error = err.message || 'Failed to load stage plot';
      } finally {
        this.loading = false;
      }
    },
    async createElement(jobId, payload) {
      const { data } = await api.post(`/jobs/${jobId}/plot-elements`, payload);
      this.elements.push(data);
      return data;
    },
    async updateElement(jobId, id, payload) {
      const { data } = await api.patch(`/jobs/${jobId}/plot-elements/${id}`, payload);
      const i = this.elements.findIndex((e) => e.id === id);
      if (i !== -1) this.elements[i] = data;
      return data;
    },
    async deleteElement(jobId, id) {
      await api.delete(`/jobs/${jobId}/plot-elements/${id}`);
      this.elements = this.elements.filter((e) => e.id !== id);
    },
  },
});
