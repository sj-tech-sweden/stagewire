import { defineStore } from 'pinia';
import { api } from '@/boot/api';

export const useStockwireStore = defineStore('stockwire', {
  state: () => ({
    categoryMap: {},
    gearTypes: [],
    categories: [],
    integration: { enabled: false, base_url: '', has_api_key: false },
    // Availability per job, keyed by jobId. Populated on demand by the availability panel
    // and reused inline by the device dialog so the Stockwire call happens once per job.
    jobAvailability: {},
  }),
  actions: {
    async loadCategoryMap() {
      const { data } = await api.get('/settings/stockwire/category-map');
      this.categoryMap = data.mapping || {};
      this.gearTypes = data.gear_types || [];
    },
    async loadCategories() {
      const { data } = await api.get('/stockwire/categories');
      this.categories = data.categories || [];
    },
    categoryPath(id) {
      const found = this.categories.find((c) => c.id === id);
      return found ? found.path : '';
    },
    async loadIntegration() {
      const { data } = await api.get('/settings/stockwire');
      this.integration = data;
    },
    categoriesForGearType(gearType) {
      if (!gearType) return [];
      return Object.keys(this.categoryMap)
        .filter((cat) => this.categoryMap[cat] === gearType)
        .map(Number);
    },
    async searchProducts(params = {}) {
      const { data } = await api.get('/stockwire/products', { params });
      return data;
    },
    // Own equipment: products that have devices, with the device count as quantity.
    async searchOwnProducts(params = {}) {
      const { data } = await api.get('/stockwire/own-products', {
        params,
        paramsSerializer: { indexes: null },
      });
      return data;
    },
    async jobDeeplink(jobId) {
      const { data } = await api.get(`/stockwire/jobs/${jobId}/deeplink`);
      return data.url;
    },
    async getProduct(productId) {
      const { data } = await api.get(`/stockwire/products/${productId}`);
      return data;
    },
    // Minimum Stockwire stock per product across the job's date range vs what the job needs.
    async getJobAvailability(jobId) {
      const { data } = await api.get(`/stockwire/jobs/${jobId}/availability`);
      this.jobAvailability = { ...this.jobAvailability, [jobId]: data };
      return data;
    },
    // Fetch availability for a job only if we don't already have it, so inline and panel
    // views share one request.
    async ensureJobAvailability(jobId) {
      if (this.jobAvailability[jobId]) return this.jobAvailability[jobId];
      return this.getJobAvailability(jobId);
    },
  },
});
