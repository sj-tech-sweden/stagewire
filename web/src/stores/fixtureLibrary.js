import { defineStore } from 'pinia';
import { api } from '@/boot/api';

const base = (jobId) => `/jobs/${jobId}/fixture-types`;

export const useFixtureLibraryStore = defineStore('fixtureLibrary', {
  state: () => ({ jobId: null, types: [], loading: false }),
  actions: {
    async fetch(jobId) {
      if (this.jobId !== jobId) this.types = [];
      this.jobId = jobId;
      this.loading = true;
      try {
        const { data } = await api.get(base(jobId));
        this.types = data;
      } finally {
        this.loading = false;
      }
    },
    async createType(jobId, payload) {
      const { data } = await api.post(base(jobId), payload);
      await this.fetch(jobId);
      return data;
    },
    async updateType(jobId, typeId, payload) {
      await api.patch(`${base(jobId)}/${typeId}`, payload);
      await this.fetch(jobId);
    },
    async deleteType(jobId, typeId) {
      await api.delete(`${base(jobId)}/${typeId}`);
      await this.fetch(jobId);
    },
    async createMode(jobId, typeId, payload) {
      await api.post(`${base(jobId)}/${typeId}/modes`, payload);
      await this.fetch(jobId);
    },
    async updateMode(jobId, typeId, modeId, payload) {
      await api.patch(`${base(jobId)}/${typeId}/modes/${modeId}`, payload);
      await this.fetch(jobId);
    },
    async deleteMode(jobId, typeId, modeId) {
      await api.delete(`${base(jobId)}/${typeId}/modes/${modeId}`);
      await this.fetch(jobId);
    },
    async importFromStockwire(jobId, productId) {
      const { data } = await api.post(`${base(jobId)}/from-stockwire`, {
        product_id: String(productId),
      });
      await this.fetch(jobId);
      return data;
    },
  },
});
