import { defineStore } from 'pinia';
import { api } from '@/boot/api';

// A fixture type library is owned by exactly one context: a job or a venue. The same store serves
// both by switching the base path, so the venue Standard Base Rig reuses the job's library UI without
// duplicating it (see docs/venues-as-template-jobs.md, Phase 1).
const base = (ctx) =>
  ctx.kind === 'venue'
    ? `/venues/${ctx.id}/fixture-types`
    : `/jobs/${ctx.id}/fixture-types`;

export const useFixtureLibraryStore = defineStore('fixtureLibrary', {
  state: () => ({ ctx: null, types: [], loading: false }),
  actions: {
    async fetch(ctx) {
      if (!this.ctx || this.ctx.kind !== ctx.kind || this.ctx.id !== ctx.id) {
        this.types = [];
      }
      this.ctx = ctx;
      this.loading = true;
      try {
        const { data } = await api.get(base(ctx));
        this.types = data;
      } finally {
        this.loading = false;
      }
    },
    async createType(ctx, payload) {
      const { data } = await api.post(base(ctx), payload);
      await this.fetch(ctx);
      return data;
    },
    async updateType(ctx, typeId, payload) {
      await api.patch(`${base(ctx)}/${typeId}`, payload);
      await this.fetch(ctx);
    },
    async deleteType(ctx, typeId) {
      await api.delete(`${base(ctx)}/${typeId}`);
      await this.fetch(ctx);
    },
    async createMode(ctx, typeId, payload) {
      await api.post(`${base(ctx)}/${typeId}/modes`, payload);
      await this.fetch(ctx);
    },
    async updateMode(ctx, typeId, modeId, payload) {
      await api.patch(`${base(ctx)}/${typeId}/modes/${modeId}`, payload);
      await this.fetch(ctx);
    },
    async deleteMode(ctx, typeId, modeId) {
      await api.delete(`${base(ctx)}/${typeId}/modes/${modeId}`);
      await this.fetch(ctx);
    },
    async importFromStockwire(ctx, productId) {
      const { data } = await api.post(`${base(ctx)}/from-stockwire`, {
        product_id: String(productId),
      });
      await this.fetch(ctx);
      return data;
    },
  },
});
