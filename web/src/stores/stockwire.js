import { defineStore } from 'pinia';
import { api } from 'boot/api';

export const useStockwireStore = defineStore('stockwire', {
  state: () => ({
    categoryMap: {},
    gearTypes: [],
    categories: [],
    integration: { enabled: false, base_url: '', has_api_key: false },
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
    async jobDeeplink(jobId) {
      const { data } = await api.get(`/stockwire/jobs/${jobId}/deeplink`);
      return data.url;
    },
    async getProduct(productId) {
      const { data } = await api.get(`/stockwire/products/${productId}`);
      return data;
    },
  },
});
